#!/usr/bin/env python3
"""Base de dados de demonstração para gravar os walkthroughs (formando, formador e administração).

Cria uma base nova numa pasta à parte (nunca toca em dados/atc.db): as contas iniciais, formandos fictícios de
várias províncias com progresso, resultados, certificados, perguntas por responder, pagamentos (incluindo uma
transferência com comprovativo e um pagamento na loja) e um lote de códigos de acesso.
Uso: python3 preparar_dados.py <pasta-de-dados>
"""
import json, os, random, sys
from datetime import datetime, timedelta
from pathlib import Path

PASTA = Path(sys.argv[1]).resolve()
if PASTA.exists() and any(PASTA.iterdir()):
    sys.exit(f"A pasta {PASTA} não está vazia.")
PASTA.mkdir(parents=True, exist_ok=True)
os.environ["ATC_DADOS"] = str(PASTA)
RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))
import atc_lms as A  # noqa: E402

random.seed(7)
A.init_db()
A.seed_demo()
DIA = timedelta(days=1)
agora = datetime.now()
quando = lambda dias, h=10: (agora - dias * DIA).replace(hour=h, minute=random.randint(0, 59), second=0).strftime("%Y-%m-%d %H:%M:%S")

FORMANDOS = [  # (nome, email, telemóvel, província, estado)
    ("Pedro Tati", "pedro.tati@exemplo.ao", "+244923100201", "Cabinda", "certificado"),
    ("Joana Mbala", "joana.mbala@exemplo.ao", "+244923100202", "Luanda", "pronta"),        # aulas feitas, falta o questionário
    ("Esperança Nzinga", "esperanca.nzinga@exemplo.ao", "+244923100203", "Huambo", "meio"),
    ("Domingos Kiala", "domingos.kiala@exemplo.ao", "+244923100204", "Benguela", "reprovou"),
    ("Rosa Lukamba", "rosa.lukamba@exemplo.ao", "+244923100205", "Huíla", "inicio"),
    ("Mateus Cassule", "mateus.cassule@exemplo.ao", "+244923100206", "Uíge", "certificado"),
    ("Isabel Kapinga", "isabel.kapinga@exemplo.ao", "+244923100207", "Bié", "meio"),
    ("Teresa Ngola", "teresa.ngola@exemplo.ao", "+244923100208", "Cabinda", "sem-acesso"),   # transferência à espera
    ("Afonso Bumba", "afonso.bumba@exemplo.ao", "+244923100209", "Malanje", "sem-acesso"),   # pagamento na loja à espera
    ("Luzia Muteka", "luzia.muteka@exemplo.ao", "+244923100210", "Namibe", "inicio"),
]

with A.db() as con:
    curso = con.execute("SELECT * FROM courses WHERE slug='informatica'").fetchone()
    licoes = con.execute("SELECT * FROM lessons WHERE course_id=? AND active=1 ORDER BY sort", (curso["id"],)).fetchall()
    quiz = con.execute("""SELECT q.* FROM quizzes q JOIN modules m ON m.id=q.module_id WHERE m.course_id=? ORDER BY m.num""", (curso["id"],)).fetchone()
    nq = con.execute("SELECT COUNT(*) FROM questions WHERE quiz_id=?", (quiz["id"],)).fetchone()[0]
    planos = {p["slug"]: p for p in con.execute("SELECT * FROM plans")}
    uid = {}
    for i, (nome, email, tel, prov, estado) in enumerate(FORMANDOS):
        u = A.create_user(con, email, nome, "formando", "demo-formando-2026")
        con.execute("UPDATE users SET phone=?, province=?, created=?, last_seen=? WHERE id=?", (tel, prov, quando(40 - i * 3), quando(i % 5), u))
        uid[nome] = u
        con.execute("INSERT OR REPLACE INTO learner_presenter VALUES(?,?,?)", (u, "helena" if i % 3 else "miguel", quando(30)))
        con.execute("INSERT OR REPLACE INTO onboarding VALUES(?,?,?)", (u, "guia", quando(30)))
        if estado == "sem-acesso":
            continue
        A.ativar_plano(con, u, planos["trimestral" if i % 2 else "mensal"], "pagamento", f"demo-{i}")
        feitas = {"certificado": len(licoes), "pronta": len(licoes), "meio": len(licoes) // 2, "reprovou": len(licoes), "inicio": 0}[estado]
        for k, l in enumerate(licoes[:feitas]):
            con.execute("INSERT OR REPLACE INTO lesson_progress(user_id, lesson_id, position, seen, completed, updated) VALUES(?,?,?,?,?,?)",
                        (u, l["id"], 0, "", quando(20 - k - i), quando(20 - k - i)))
        if estado in ("certificado", "reprovou"):
            score = nq if estado == "certificado" else max(1, nq // 2 - 1)
            con.execute("INSERT INTO quiz_attempts(user_id, quiz_id, score, total, pct, passed, answers, created) VALUES(?,?,?,?,?,?,?,?)",
                        (u, quiz["id"], score, nq, round(100 * score / nq), int(score / nq * 100 >= quiz["pass_mark"]), "[]", quando(6 - i % 4)))
        if estado == "certificado":
            con.execute("INSERT INTO certificates VALUES(?,?,?,?)", (f"ATC-{random.randrange(16**8):08X}", u, curso["id"], quando(5 - i % 3)))

    # Perguntas dos formandos, por responder
    perguntas = [("Esperança Nzinga", 0, "Qual é a diferença entre desligar e suspender o computador? Posso deixar sempre em suspensão?"),
                 ("Rosa Lukamba", 1, "Quando crio uma pasta no ambiente de trabalho, ela fica guardada em que sítio do disco?"),
                 ("Isabel Kapinga", 0, "O meu teclado não tem a tecla Windows. Há outra forma de abrir o menu Iniciar?")]
    for nome, k, texto in perguntas:
        con.execute("INSERT INTO comments(lesson_id, user_id, parent_id, body, created) VALUES(?,?,?,?,?)",
                    (licoes[min(k, len(licoes) - 1)]["id"], uid[nome], None, texto, quando(1, 9 + k)))

    # Pagamentos: transferência com comprovativo, loja à espera, e alguns já pagos
    A.COMPROVATIVOS.mkdir(parents=True, exist_ok=True)
    comp = Path(__file__).with_name("comprovativo-exemplo.png")
    if comp.is_file():
        (A.COMPROVATIVOS / "P-demo-comprovativo.png").write_bytes(comp.read_bytes())
    def pagamento(nome, plano, metodo, estado, dias, **extra):
        con.execute("""INSERT INTO payments(user_id, plan_id, amount_kz, method, status, provider, entity, reference, phone, note, proof, created, updated)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (uid[nome], planos[plano]["id"], planos[plano]["price_kz"], metodo, estado, "demo",
                       extra.get("entity"), extra.get("reference"), extra.get("phone"), extra.get("note"), extra.get("proof"), quando(dias), quando(dias)))
    pagamento("Pedro Tati", "mensal", "mcx", "pago", 30, phone="+244923100201")
    pagamento("Mateus Cassule", "trimestral", "referencia", "pago", 22, entity="00000", reference="381204557")
    pagamento("Isabel Kapinga", "trimestral", "mcx", "pago", 12, phone="+244923100207")
    pagamento("Afonso Bumba", "mensal", "loja", "pendente", 0, reference="ATC-K7Q2MX")
    pagamento("Teresa Ngola", "trimestral", "transferencia", "em_analise", 0, note="OP 20261016-4471",
              proof="P-demo-comprovativo.png" if comp.is_file() else None)

    # Lote de códigos da internet Angbu, alguns já usados
    admin = con.execute("SELECT id FROM users WHERE email='admin@atc.ao'").fetchone()["id"]
    for k in range(40):
        code = A.gerar_codigo()
        usado = uid["Luzia Muteka"] if k == 0 else None
        con.execute("INSERT INTO access_codes(code, plan_id, label, created_by, created, used_by, used_at) VALUES(?,?,?,?,?,?,?)",
                    (code, planos["trimestral"]["id"], "Internet Angbu — setembro", admin, quando(25), usado, quando(3) if usado else None))
    A.set_setting(con, "demo", "0")   # sem o aviso de contas de teste nos vídeos
    con.commit()
print("ok", PASTA)
