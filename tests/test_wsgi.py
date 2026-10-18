"""Adaptador WSGI (alojamento cPanel/Passenger): o mesmo LMS, servido sem socket próprio."""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from wsgiref.util import setup_testing_defaults

RAIZ = Path(__file__).resolve().parents[1]
_dados = tempfile.TemporaryDirectory()
os.environ["ATC_DADOS"] = _dados.name
sys.path.insert(0, str(RAIZ))
import passenger_wsgi  # noqa: E402


def pedido(path, method="GET", body=b"", headers=None, https=False, ctype="application/x-www-form-urlencoded"):
    env = {"REQUEST_METHOD": method, "PATH_INFO": path.split("?")[0],
           "QUERY_STRING": path.partition("?")[2], "wsgi.input": io.BytesIO(body),
           "CONTENT_LENGTH": str(len(body)), "wsgi.url_scheme": "https" if https else "http"}
    if body:
        env["CONTENT_TYPE"] = ctype
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
        r = pedido("/entrar")
        self.assertTrue(r["status"].startswith("200"))
        self.assertNotIn(b"admin123", r["body"])                       # contas de demonstração fora da página pública
        self.assertNotIn(b"formando123", r["body"])
        r = pedido("/")                                                # sem sessão: página inicial pública
        self.assertTrue(r["status"].startswith("200"), r["status"])
        self.assertIn("abrem portas".encode(), r["body"])
        self.assertIn(b'id="feature"', r["body"])
        self.assertIn(b'href="/entrar"', r["body"])
        self.assertTrue(pedido("/conta")["status"].startswith("303"))  # páginas privadas continuam a pedir sessão
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
        self.assertIn('data-seguinte href="/cursos/informatica/aula/aula-1-1"', html)
        self.assertIn("Passo 1 de 5", html)
        self.assertIn('data-u="%d"' % self.uid, html)

    def test_learner_who_finished_is_offered_to_review_not_stranded(self):
        app = passenger_wsgi.atc_lms
        with app.db() as con:
            for (lid,) in con.execute("SELECT id FROM lessons WHERE course_id=(SELECT id FROM courses WHERE slug='informatica')").fetchall():
                con.execute("INSERT OR REPLACE INTO lesson_progress(user_id,lesson_id,completed) VALUES(?,?,?)", (self.uid, lid, "2026"))
        html = self.intro()
        self.assertIn('data-seguinte href="/cursos/informatica/aula/aula-1-1"', html)
        self.assertNotIn('aria-disabled', html)


class BeginnerPathTests(unittest.TestCase):
    """Percurso de quem está a começar: um ecrã de entrada e passos que abrem pela ordem."""

    def setUp(self):
        self.app = passenger_wsgi.atc_lms
        with self.app.db() as con:
            self.uid = con.execute("SELECT id FROM users WHERE email='formando@atc.ao'").fetchone()[0]
            for t in ("learner_presenter", "lesson_progress", "onboarding", "course_presenters"):
                con.execute(f"DELETE FROM {t} WHERE user_id=?", (self.uid,))
        self.cookie = pedido("/entrar", "POST", b"email=formando%40atc.ao&pw=formando123")["h"]["set-cookie"].split(";")[0]

    tearDown = setUp

    def get(self, path):
        return pedido(path, headers={"Cookie": self.cookie})

    def test_first_visit_is_one_screen_then_the_course(self):
        self.assertEqual(self.get("/comecar")["h"]["location"], "/comecar/guia")
        r = self.get("/comecar/guia")
        html = r["body"].decode()
        self.assertIn("Começar o meu curso", html)
        self.assertIn('class="app foco"', html)          # sem menu lateral
        self.assertNotIn('class="sidebar"', html)
        self.assertIn("/plataforma/helena/boas-vindas.mp4", html)
        csrf = html.split('name="csrf" content="')[1].split('"')[0]
        r = pedido("/comecar/guia", "POST", ("presenter=helena&csrf=" + csrf).encode(), headers={"Cookie": self.cookie})
        self.assertEqual(r["h"]["location"], "/cursos/informatica")
        self.assertEqual(self.get("/comecar/perfil")["h"]["location"], "/comecar")   # passos antigos já não existem

    def test_course_path_opens_one_step_at_a_time(self):
        with self.app.db() as con:
            con.execute("INSERT INTO learner_presenter VALUES(?,?,?)", (self.uid, "miguel", "2026"))
        html = self.get("/cursos/informatica")["body"].decode()
        self.assertIn("Começar: Conheça o Miguel", html)
        self.assertEqual(html.count('class="percurso-passo seguinte"'), 1)
        self.assertEqual(html.count('class="percurso-passo trancado"'), 4)
        self.assertNotIn("Primeiros passos no Windows", html)      # a demonstração passou para dentro da aula 1.1
        self.get("/cursos/informatica/introducao")                 # ver a introdução abre a aula 1.1
        html = self.get("/cursos/informatica")["body"].decode()
        self.assertIn("Continuar: Aula 1.1", html)
        aula = self.get("/cursos/informatica/aula/aula-1-1")["body"].decode()
        self.assertIn('data-seguinte href="/cursos/informatica/aula/aula-1-2" aria-disabled="true"', aula)
        self.assertIn("Primeiros passos no Windows", aula)
        self.assertIn("amostra-windows-atc.mp4", aula)


class PagamentosTests(unittest.TestCase):
    """Registo, planos, pagamentos de demonstração, comprovativos, códigos de acesso e expiração."""

    def registar(self, phone, email):
        body = urllib.parse.urlencode({"name": "Teste Cabinda", "phone": phone, "email": email, "province": "Cabinda", "pw": "segredo123"}).encode()
        r = pedido("/registar", "POST", body)
        self.assertTrue(r["status"].startswith("303"), r["body"][:300])
        self.assertEqual(r["h"]["location"], "/planos")
        return r["h"]["set-cookie"].split(";")[0]

    def csrf(self, cookie, path="/planos"):
        return pedido(path, headers={"Cookie": cookie})["body"].decode().split('name="csrf" content="')[1].split('"')[0]

    def post(self, path, cookie, **campos):
        campos["csrf"] = self.csrf(cookie)
        return pedido(path, "POST", urllib.parse.urlencode(campos).encode(), headers={"Cookie": cookie})

    def acesso(self, cookie):
        """True se o formando consegue abrir o curso publicado (200, ou redirecionado para escolher o guia), False se recebe 403."""
        st = pedido("/cursos/informatica", headers={"Cookie": cookie})["status"]
        self.assertTrue(st[:3] in ("200", "303", "403"), st)
        return not st.startswith("403")

    def pagar(self, cookie, method, plan="mensal", **extra):
        r = self.post(f"/pagar/{plan}", cookie, method=method, **extra)
        self.assertTrue(r["status"].startswith("303"), r["body"][:300])
        return r["h"]["location"]

    def test_registo_valida_e_entra_com_telemovel(self):
        bad = pedido("/registar", "POST", b"name=Ana&phone=123&email=x%40y.ao&province=Cabinda&pw=segredo123")
        self.assertIn("telemóvel angolano válido".encode(), bad["body"])
        self.registar("923 000 001", "t1@exemplo.ao")
        dup = pedido("/registar", "POST", b"name=Outro&phone=%2B244923000001&email=t1b%40exemplo.ao&province=Luanda&pw=segredo123")
        self.assertIn("Já existe uma conta com este telemóvel".encode(), dup["body"])
        r = pedido("/entrar", "POST", b"email=923000001&pw=segredo123")
        self.assertTrue(r["status"].startswith("303"))

    def test_multicaixa_express_demo_ativa_acesso(self):
        c = self.registar("923000002", "t2@exemplo.ao")
        self.assertFalse(self.acesso(c))
        loc = self.pagar(c, "mcx", phone="923000002")
        page = pedido(loc, headers={"Cookie": c})["body"].decode()
        self.assertIn("Confirme no seu telemóvel", page)
        r = self.post(loc + "/simular", c, ok="1")
        self.assertTrue(r["status"].startswith("303"))
        self.assertIn("Pagamento confirmado", pedido(loc, headers={"Cookie": c})["body"].decode())
        self.assertTrue(self.acesso(c))
        self.assertIn("Acesso ativo", pedido("/planos", headers={"Cookie": c})["body"].decode())

    def test_referencia_e_pagamento_alheio(self):
        c = self.registar("923000003", "t3@exemplo.ao")
        loc = self.pagar(c, "referencia", plan="trimestral")
        page = pedido(loc, headers={"Cookie": c})["body"].decode()
        self.assertIn("Entidade", page)
        self.assertIn("19 500 Kz", page)
        outro = self.registar("923000004", "t4@exemplo.ao")
        self.assertTrue(pedido(loc, headers={"Cookie": outro})["status"].startswith("404"))   # não vê pagamentos de outros

    def test_transferencia_com_comprovativo_e_aprovacao(self):
        c = self.registar("923000005", "t5@exemplo.ao")
        loc = self.pagar(c, "transferencia")
        csrf = self.csrf(c, loc)
        fr = "----atc"
        body = (f"--{fr}\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\n{csrf}\r\n"
                f"--{fr}\r\nContent-Disposition: form-data; name=\"note\"\r\n\r\nOP123\r\n"
                f"--{fr}\r\nContent-Disposition: form-data; name=\"proof\"; filename=\"recibo.pdf\"\r\nContent-Type: application/pdf\r\n\r\n").encode() \
            + b"%PDF-1.4 teste" + f"\r\n--{fr}--\r\n".encode()
        r = pedido(loc + "/comprovativo", "POST", body, headers={"Cookie": c}, ctype=f"multipart/form-data; boundary={fr}")
        self.assertTrue(r["status"].startswith("303"), r["body"][:300])
        self.assertIn("Comprovativo recebido", pedido(loc, headers={"Cookie": c})["body"].decode())
        admin = pedido("/entrar", "POST", b"email=admin%40atc.ao&pw=admin123")["h"]["set-cookie"].split(";")[0]
        lista = pedido("/admin/pagamentos", headers={"Cookie": admin})["body"].decode()
        self.assertIn("Ver comprovativo", lista)
        pid = loc.rsplit("/", 1)[1]
        self.assertTrue(pedido(f"/admin/pagamentos/{pid}/comprovativo", headers={"Cookie": admin})["body"].startswith(b"%PDF"))
        csrf_a = lista.split('name="csrf" content="')[1].split('"')[0]
        pedido(f"/admin/pagamentos/{pid}", "POST", f"ok=1&csrf={csrf_a}".encode(), headers={"Cookie": admin})
        self.assertTrue(self.acesso(c))

    def test_codigo_de_acesso_uso_unico_e_expiracao(self):
        admin = pedido("/entrar", "POST", b"email=admin%40atc.ao&pw=admin123")["h"]["set-cookie"].split(";")[0]
        page = pedido("/admin/codigos", headers={"Cookie": admin})["body"].decode()
        csrf_a = page.split('name="csrf" content="')[1].split('"')[0]
        pedido("/admin/codigos", "POST", f"label=Internet+Angbu&plan_id=1&n=2&csrf={csrf_a}".encode(), headers={"Cookie": admin})
        csv_ = pedido("/admin/codigos.csv?lote=Internet%20Angbu", headers={"Cookie": admin})["body"].decode("utf-8-sig")
        code = csv_.splitlines()[1].split(",")[0]
        c = self.registar("923000006", "t6@exemplo.ao")
        r = self.post("/codigo", c, code=code.replace("-", "").lower())
        self.assertIn("Código ativado".encode(), r["body"])
        self.assertTrue(self.acesso(c))
        outro = self.registar("923000007", "t7@exemplo.ao")
        self.assertIn("já foi utilizado".encode(), self.post("/codigo", outro, code=code)["body"])
        con = passenger_wsgi.atc.db() if hasattr(passenger_wsgi, "atc") else None
        if con is None:
            import atc_lms
            con = atc_lms.db()
        uid = con.execute("SELECT id FROM users WHERE email='t6@exemplo.ao'").fetchone()[0]
        con.execute("UPDATE subscriptions SET ends='2000-01-01 00:00:00' WHERE user_id=?", (uid,))
        con.commit()
        self.assertFalse(self.acesso(c))   # acesso expirado
        self.assertIn("O seu acesso terminou", pedido("/planos", headers={"Cookie": c})["body"].decode())

    def test_notificacao_sem_segredo_desligada(self):
        r = pedido("/pagamentos/notificacao", "POST", b'{"payment_id": 1, "status": "pago"}', ctype="application/json")
        self.assertTrue(r["status"].startswith("404"))


class ApresentacaoTests(unittest.TestCase):
    def test_pagina_publica_sem_credenciais_e_fora_dos_motores(self):
        r = pedido("/apresentacao")
        self.assertTrue(r["status"].startswith("200"))
        self.assertIn(b'name="robots" content="noindex', r["body"])
        self.assertIn(b"walkthrough-formando.mp4", r["body"])
        for segredo in (b"admin123", b"formador123", b"formando123"):
            self.assertNotIn(segredo, r["body"])

    def test_formador_abre_aula_sem_escolher_guia(self):
        c = pedido("/entrar", "POST", b"email=formador%40atc.ao&pw=formador123")["h"]["set-cookie"].split(";")[0]
        r = pedido("/cursos/informatica/aula/aula-1-1", headers={"Cookie": c})
        self.assertTrue(r["status"].startswith("200"), r["status"])
        self.assertIn(b'id="perguntas" open', r["body"])


if __name__ == "__main__":
    unittest.main()


class GaleriaTests(unittest.TestCase):
    """Galeria 3D: só com sessão iniciada; os modelos também ficam protegidos."""

    def test_gallery_and_models_need_a_session(self):
        r = pedido("/galeria")
        self.assertTrue(r["status"].startswith("30"), r["status"])
        r = pedido("/galeria/modelos/motherboard.glb")
        self.assertFalse(r["status"].startswith("200"), r["status"])

    def test_learner_sees_every_piece_and_can_load_a_model(self):
        cookie = pedido("/entrar", "POST", b"email=formando%40atc.ao&pw=formando123")["h"]["set-cookie"].split(";")[0]
        html = pedido("/galeria", headers={"Cookie": cookie})["body"].decode()
        self.assertIn('href="/galeria"', html)
        dados = json.loads(html.split('<script id="galeria-dados" type="application/json">')[1].split("</script>")[0])
        self.assertEqual(len(dados), 9)
        for p in dados:
            self.assertTrue(p["pontos"], p["slug"])
            self.assertTrue((passenger_wsgi.atc_lms.GALERIA_DIR / "modelos" / p["ficheiro"]).is_file(), p["ficheiro"])
        r = pedido("/galeria/modelos/motherboard.glb", headers={"Cookie": cookie})
        self.assertTrue(r["status"].startswith("200"), r["status"])
        self.assertEqual(r["h"]["content-type"], "model/gltf-binary")
        self.assertEqual(r["body"][:4], b"glTF")
        self.assertFalse(pedido("/galeria/modelos/..%2Fpecas.json", headers={"Cookie": cookie})["status"].startswith("200"))
