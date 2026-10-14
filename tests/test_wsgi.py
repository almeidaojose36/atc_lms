"""Adaptador WSGI (alojamento cPanel/Passenger): o mesmo LMS, servido sem socket próprio."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from wsgiref.util import setup_testing_defaults

RAIZ = Path(__file__).resolve().parents[1]
_dados = tempfile.TemporaryDirectory()
os.environ["ATC_DADOS"] = _dados.name
sys.path.insert(0, str(RAIZ))
import passenger_wsgi  # noqa: E402


def pedido(path, method="GET", body=b"", headers=None, https=False):
    env = {"REQUEST_METHOD": method, "PATH_INFO": path.split("?")[0],
           "QUERY_STRING": path.partition("?")[2], "wsgi.input": io.BytesIO(body),
           "CONTENT_LENGTH": str(len(body)), "wsgi.url_scheme": "https" if https else "http"}
    if body:
        env["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
    for k, v in (headers or {}).items():
        env["HTTP_" + k.upper().replace("-", "_")] = v
    setup_testing_defaults(env)
    out = {}

    def start_response(status, hdrs):
        out["status"], out["headers"] = status, hdrs
    out["body"] = b"".join(passenger_wsgi.application(env, start_response))
    out["h"] = {k.lower(): v for k, v in out["headers"]}
    return out


class WsgiTests(unittest.TestCase):
    def entrar(self, https=False):
        r = pedido("/entrar", "POST", b"email=formando%40atc.ao&pw=formando123", https=https)
        self.assertTrue(r["status"].startswith("303"), r["status"])
        return r

    def test_login_page_and_session(self):
        self.assertTrue(pedido("/entrar")["status"].startswith("200"))
        self.assertTrue(pedido("/")["status"].startswith("303"))      # sem sessão: vai para /entrar
        r = self.entrar()
        cookie = r["h"]["set-cookie"].split(";")[0]
        self.assertNotIn("Secure", r["h"]["set-cookie"])
        self.assertEqual(pedido("/", headers={"Cookie": cookie})["h"]["location"], "/comecar")   # primeira visita
        r = pedido("/comecar/guia", headers={"Cookie": cookie})
        self.assertTrue(r["status"].startswith("200"))
        self.assertIn("Helena".encode(), r["body"])

    def test_cookie_is_secure_over_https(self):
        self.assertIn("Secure", self.entrar(https=True)["h"]["set-cookie"])

    def test_cookie_is_secure_behind_https_proxy(self):
        r = pedido("/entrar", "POST", b"email=formando%40atc.ao&pw=formando123",
                   headers={"X-Forwarded-Proto": "https"})
        self.assertEqual(r["h"]["set-cookie"].count("Secure"), 1)

    def test_no_hop_by_hop_headers(self):
        for k in pedido("/entrar")["h"]:
            self.assertNotIn(k, passenger_wsgi.HOP_BY_HOP)

    def test_static_file_streamed_with_ranges(self):
        f = next(p for p in (RAIZ / "static").rglob("*") if p.is_file() and p.stat().st_size > 100)
        url = "/static/" + f.relative_to(RAIZ / "static").as_posix()
        dados = f.read_bytes()
        self.assertEqual(pedido(url)["body"], dados)
        r = pedido(url, headers={"Range": "bytes=10-49"})
        self.assertTrue(r["status"].startswith("206"))
        self.assertEqual(r["body"], dados[10:50])
        self.assertEqual(pedido(url, "HEAD")["body"], b"")
        self.assertTrue(pedido("/static/../atc_lms.py")["status"].startswith("404"))


class IntroNextStepTests(unittest.TestCase):
    """Introdução do curso: vídeos por ordem e um próximo passo sempre visível."""

    def setUp(self):
        app = passenger_wsgi.atc_lms
        with app.db() as con:
            self.uid = con.execute("SELECT id FROM users WHERE email='formando@atc.ao'").fetchone()[0]
            con.execute("INSERT OR REPLACE INTO learner_presenter VALUES(?,?,?)", (self.uid, "helena", "2026"))
            con.execute("DELETE FROM lesson_progress WHERE user_id=?", (self.uid,))
        r = pedido("/entrar", "POST", b"email=formando%40atc.ao&pw=formando123")
        self.cookie = r["h"]["set-cookie"].split(";")[0]

    def tearDown(self):
        with passenger_wsgi.atc_lms.db() as con:
            con.execute("DELETE FROM learner_presenter WHERE user_id=?", (self.uid,))
            con.execute("DELETE FROM lesson_progress WHERE user_id=?", (self.uid,))

    def intro(self):
        r = pedido("/cursos/informatica/introducao", headers={"Cookie": self.cookie})
        self.assertTrue(r["status"].startswith("200"), r["status"])
        return r["body"].decode()

    def test_new_learner_is_told_to_start_the_first_lesson(self):
        html = self.intro()
        self.assertIn('class="guide-clips" data-ordem', html)
        self.assertIn('data-proximo href="/cursos/informatica/aula/aula-1-1"', html)
        self.assertIn("Começar:", html)
        self.assertIn('data-u="%d"' % self.uid, html)

    def test_learner_who_finished_is_offered_to_review_not_stranded(self):
        app = passenger_wsgi.atc_lms
        with app.db() as con:
            for (lid,) in con.execute("SELECT id FROM lessons WHERE course_id=(SELECT id FROM courses WHERE slug='informatica')").fetchall():
                con.execute("INSERT OR REPLACE INTO lesson_progress(user_id,lesson_id,completed) VALUES(?,?,?)", (self.uid, lid, "2026"))
        html = self.intro()
        self.assertIn('data-proximo href="/cursos/informatica/aula/aula-1-1"', html)
        self.assertIn("Rever:", html)
        self.assertIn("Já concluiu as aulas", html)


if __name__ == "__main__":
    unittest.main()
