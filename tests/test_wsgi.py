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


if __name__ == "__main__":
    unittest.main()
