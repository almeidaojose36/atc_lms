#!/usr/bin/env python3
"""ATC LMS: plataforma de formação online da ATC (Angbu Training Centre).

Um único ficheiro, só biblioteca padrão do Python 3.10+, base de dados SQLite.

    python atc_lms.py                      # inicia o servidor em http://localhost:8080
    python atc_lms.py --porta 80           # outra porta
    python atc_lms.py importar             # (re)importa os cursos da pasta cursos/
    python atc_lms.py utilizador EMAIL NOME PAPEL PALAVRA-PASSE
"""
import argparse
import csv
import hashlib
import hmac
import html
import io
import json
import math
import mimetypes
import os
import random
import re
import secrets
import socket
import sqlite3
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
COURSES_DIR = Path(os.environ.get("ATC_CURSOS", BASE / "cursos"))
DATA_DIR = Path(os.environ.get("ATC_DADOS", BASE / "dados"))
DB_PATH = DATA_DIR / "atc.db"
OLLAMA_URL = os.environ.get("ATC_OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("ATC_MODELO", "qwen2.5:7b")
COOKIE = "atc_sessao"
SESSION_DAYS = 14
COMPLETE_RATIO = 0.9  # fração do vídeo que conta como "aula vista"

ROLES = {"admin": "Administrador", "formador": "Formador", "formando": "Formando"}
PRESENTERS = {"helena": {"name": "Helena", "label": "Avatar feminino"}, "miguel": {"name": "Miguel", "label": "Avatar masculino"}}
PROFILE_COLORS = {"sand": "Areia", "navy": "Azul", "green": "Verde", "rose": "Rosa"}

STATUS = {"publicado": "Disponível", "em_breve": "Em breve"}

mimetypes.add_type("text/vtt", ".vtt")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")

# ---------------------------------------------------------------------------
# Base de dados
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'formando', pw_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL, last_seen TEXT);
CREATE TABLE IF NOT EXISTS learner_profiles (
  user_id INTEGER PRIMARY KEY REFERENCES users(id), display_name TEXT NOT NULL,
  occupation TEXT NOT NULL DEFAULT '', goal TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL DEFAULT 'sand', updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS course_presenters (
  user_id INTEGER NOT NULL REFERENCES users(id), course_id INTEGER NOT NULL REFERENCES courses(id),
  presenter TEXT NOT NULL CHECK(presenter IN ('helena','miguel')), updated TEXT NOT NULL,
  PRIMARY KEY(user_id, course_id));
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS courses (
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL, subtitle TEXT,
  description TEXT, status TEXT NOT NULL, sort INTEGER DEFAULT 0, hours_video REAL,
  hours_class REAL, cover TEXT, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS modules (
  id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL, num INTEGER NOT NULL, title TEXT NOT NULL,
  intro TEXT, manual_json TEXT, manual_docx TEXT, manual_figures TEXT,
  active INTEGER NOT NULL DEFAULT 1, UNIQUE(course_id, num));
CREATE TABLE IF NOT EXISTS lessons (
  id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL, module_id INTEGER NOT NULL,
  slug TEXT NOT NULL, title TEXT NOT NULL, summary TEXT, video TEXT, subtitles TEXT,
  subtitles_on INTEGER DEFAULT 0, poster TEXT, duration REAL, transcript TEXT,
  sort INTEGER DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, UNIQUE(course_id, slug));
CREATE TABLE IF NOT EXISTS quizzes (
  id INTEGER PRIMARY KEY, module_id INTEGER UNIQUE NOT NULL, title TEXT NOT NULL,
  pass_mark INTEGER NOT NULL DEFAULT 70, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY, quiz_id INTEGER NOT NULL, code TEXT, text TEXT NOT NULL,
  options TEXT NOT NULL, correct INTEGER NOT NULL, feedback TEXT, sort INTEGER);
CREATE TABLE IF NOT EXISTS enrolments (
  user_id INTEGER NOT NULL, course_id INTEGER NOT NULL, created TEXT NOT NULL,
  PRIMARY KEY(user_id, course_id));
CREATE TABLE IF NOT EXISTS lesson_progress (
  user_id INTEGER NOT NULL, lesson_id INTEGER NOT NULL, position REAL DEFAULT 0,
  seen TEXT DEFAULT '', completed TEXT, updated TEXT, PRIMARY KEY(user_id, lesson_id));
CREATE TABLE IF NOT EXISTS presenter_progress (
  user_id INTEGER NOT NULL REFERENCES users(id), lesson_id INTEGER NOT NULL REFERENCES lessons(id),
  presenter TEXT NOT NULL, position REAL DEFAULT 0, seen TEXT DEFAULT '', completed TEXT, updated TEXT,
  PRIMARY KEY(user_id, lesson_id, presenter));
CREATE TABLE IF NOT EXISTS quiz_attempts (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, quiz_id INTEGER NOT NULL, score INTEGER,
  total INTEGER, pct INTEGER, passed INTEGER, answers TEXT, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY, lesson_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  parent_id INTEGER, body TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS certificates (
  code TEXT PRIMARY KEY, user_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
  issued TEXT NOT NULL, UNIQUE(user_id, course_id));
"""


def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)


def setting(con, key, default=None):
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(con, key, value):
    con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)", (key, value))


# ---------------------------------------------------------------------------
# Palavras-passe e sessões
# ---------------------------------------------------------------------------

def hash_pw(pw):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"pbkdf2$200000${salt}${dk}"


def check_pw(pw, stored):
    try:
        _, it, salt, dk = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(it)).hex()
        return hmac.compare_digest(test, dk)
    except ValueError:
        return False


def create_user(con, email, name, role, pw):
    email = email.strip().lower()
    if role not in ROLES:
        raise ValueError(f"Papel inválido: {role}")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError(f"Email inválido: {email}")
    if len(pw) < 6:
        raise ValueError("A palavra-passe tem de ter pelo menos 6 caracteres.")
    cur = con.execute("INSERT INTO users(email, name, role, pw_hash, created) VALUES(?,?,?,?,?)",
                      (email, name.strip(), role, hash_pw(pw), now()))
    return cur.lastrowid


def seed_demo():
    """Na primeira execução: importa os cursos e cria contas de demonstração."""
    with db() as con:
        if con.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return
        import_all(con)
        uid_admin = create_user(con, "admin@atc.ao", "Administração ATC", "admin", "admin123")
        create_user(con, "formador@atc.ao", "Formador ATC", "formador", "formador123")
        uid = create_user(con, "formando@atc.ao", "Ana Formanda", "formando", "formando123")
        course = con.execute("SELECT id FROM courses WHERE slug='informatica'").fetchone()
        if course:
            for u in (uid, uid_admin):
                con.execute("INSERT OR IGNORE INTO enrolments VALUES(?,?,?)", (u, course["id"], now()))
        set_setting(con, "demo", "1")
        print("Contas de demonstração criadas: admin@atc.ao / admin123, "
              "formador@atc.ao / formador123, formando@atc.ao / formando123")


# ---------------------------------------------------------------------------
# Importação de cursos (pasta cursos/<slug>/curso.json)
# ---------------------------------------------------------------------------

def parse_gift(text):
    """Lê perguntas de escolha múltipla e verdadeiro/falso em formato GIFT (Moodle)."""
    out = []
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    blocks = re.split(r"\n\s*\n", "\n".join(lines))
    unesc = lambda s: re.sub(r"\\([:=~#{}])", r"\1", s).strip()
    for blk in blocks:
        blk = blk.strip()
        if not blk or blk.startswith("$CATEGORY"):
            continue
        code = ""
        m = re.match(r"::(.*?)::(.*)", blk, re.S)
        if m:
            code, blk = m.group(1).strip(), m.group(2)
        m = re.match(r"(.*?)(?<!\\)\{(.*)(?<!\\)\}(.*)", blk, re.S)
        if not m:
            continue
        qtext = unesc(m.group(1) + (" " + m.group(3) if m.group(3).strip() else ""))
        qtext = re.sub(r"^\[(html|moodle|markdown|plain)\]", "", qtext)
        body = m.group(2).strip()
        if body.upper() in ("T", "TRUE", "F", "FALSE"):
            opts, correct = ["Verdadeiro", "Falso"], 0 if body.upper().startswith("T") else 1
            out.append({"code": code, "text": qtext, "options": opts, "correct": correct, "feedback": ""})
            continue
        parts = re.findall(r"(?<!\\)([=~])((?:\\.|[^=~\\])*)", body)
        opts, correct, feedback = [], None, ""
        for sign, val in parts:
            val, fb = (re.split(r"(?<!\\)#", val, maxsplit=1) + [""])[:2]
            val = re.sub(r"^%-?\d+(\.\d+)?%", "", val.strip())
            if sign == "=":
                correct, feedback = len(opts), unesc(fb)
            opts.append(unesc(val))
        if opts and correct is not None:
            out.append({"code": code, "text": qtext, "options": opts, "correct": correct, "feedback": feedback})
    return out


def parse_subtitles(text):
    """Devolve [(início, fim, texto)] de um ficheiro VTT ou SRT."""
    cues = []
    for blk in re.split(r"\n\s*\n", text.replace("\r", "").strip()):
        ls = blk.split("\n")
        for i, ln in enumerate(ls):
            m = re.match(r"([\d:.,]+)\s*-->\s*([\d:.,]+)", ln)
            if m:
                cues.append((m.group(1).replace(",", "."), m.group(2).replace(",", "."), " ".join(ls[i + 1:]).strip()))
                break
    return cues


def to_vtt(text):
    def ts(t):
        p = t.split(":")
        return ("00:" + t) if len(p) == 2 else t
    return "WEBVTT\n\n" + "\n\n".join(f"{ts(a)} --> {ts(b)}\n{t}" for a, b, t in parse_subtitles(text)) + "\n"


def mp4_duration(path):
    """Duração de um MP4 lida da caixa mvhd (sem ffprobe)."""
    try:
        with open(path, "rb") as f:
            def boxes(end):
                while f.tell() < end:
                    hdr = f.read(8)
                    if len(hdr) < 8:
                        return
                    size, typ = struct.unpack(">I4s", hdr)
                    start = f.tell() - 8
                    if size == 1:
                        size = struct.unpack(">Q", f.read(8))[0]
                    elif size == 0:
                        size = end - start
                    yield typ, start, size
                    f.seek(start + size)
            total = os.path.getsize(path)
            for typ, start, size in boxes(total):
                if typ == b"moov":
                    f.seek(start + 8)
                    for t2, s2, _ in boxes(start + size):
                        if t2 == b"mvhd":
                            f.seek(s2 + 8)
                            ver = f.read(1)[0]
                            f.read(3)
                            if ver == 1:
                                f.read(16); scale, dur = struct.unpack(">IQ", f.read(12))
                            else:
                                f.read(8); scale, dur = struct.unpack(">II", f.read(8))
                            return dur / scale if scale else None
    except (OSError, struct.error, IndexError):
        pass
    return None


def import_pack(con, folder):
    meta = json.loads((folder / "curso.json").read_text(encoding="utf-8"))
    slug = meta.get("slug") or folder.name
    con.execute("""INSERT INTO courses(slug, title, subtitle, description, status, sort, hours_video, hours_class, cover, active)
                   VALUES(?,?,?,?,?,?,?,?,?,1)
                   ON CONFLICT(slug) DO UPDATE SET title=excluded.title, subtitle=excluded.subtitle,
                   description=excluded.description, status=excluded.status, sort=excluded.sort,
                   hours_video=excluded.hours_video, hours_class=excluded.hours_class, cover=excluded.cover, active=1""",
                (slug, meta["title"], meta.get("subtitle", ""), meta.get("description", ""),
                 meta.get("status", "publicado"), meta.get("order", 99), meta.get("hours_video"),
                 meta.get("hours_class"), meta.get("cover")))
    cid = con.execute("SELECT id FROM courses WHERE slug=?", (slug,)).fetchone()["id"]
    con.execute("UPDATE modules SET active=0 WHERE course_id=?", (cid,))
    con.execute("UPDATE lessons SET active=0 WHERE course_id=?", (cid,))
    n_lessons = n_q = 0
    for order, mod in enumerate(meta.get("modules", [])):
        con.execute("""INSERT INTO modules(course_id, num, title, intro, manual_json, manual_docx, manual_figures, active)
                       VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(course_id, num) DO UPDATE SET title=excluded.title,
                       intro=excluded.intro, manual_json=excluded.manual_json, manual_docx=excluded.manual_docx,
                       manual_figures=excluded.manual_figures, active=1""",
                    (cid, mod["num"], mod["title"], mod.get("intro", ""), mod.get("manual_json"),
                     mod.get("manual_docx"), mod.get("manual_figures")))
        mid = con.execute("SELECT id FROM modules WHERE course_id=? AND num=?", (cid, mod["num"])).fetchone()["id"]
        for i, les in enumerate(mod.get("lessons", [])):
            transcript, sub = "", les.get("subtitles")
            if sub and (folder / sub).exists():
                transcript = "\n".join(t for _, _, t in parse_subtitles((folder / sub).read_text(encoding="utf-8-sig")))
            dur = mp4_duration(folder / les["video"]) if les.get("video") else None
            con.execute("""INSERT INTO lessons(course_id, module_id, slug, title, summary, video, subtitles, subtitles_on,
                           poster, duration, transcript, sort, active) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)
                           ON CONFLICT(course_id, slug) DO UPDATE SET module_id=excluded.module_id, title=excluded.title,
                           summary=excluded.summary, video=excluded.video, subtitles=excluded.subtitles,
                           subtitles_on=excluded.subtitles_on, poster=excluded.poster,
                           duration=COALESCE(excluded.duration, lessons.duration), transcript=excluded.transcript,
                           sort=excluded.sort, active=1""",
                        (cid, mid, les["slug"], les["title"], les.get("summary", ""), les.get("video"), sub,
                         1 if les.get("subtitles_on") else 0, les.get("poster"), dur, transcript, order * 100 + i))
            n_lessons += 1
        qz = mod.get("quiz")
        con.execute("UPDATE quizzes SET active=0 WHERE module_id=?", (mid,))
        if qz and qz.get("gift"):
            questions = parse_gift((folder / qz["gift"]).read_text(encoding="utf-8-sig"))
            con.execute("""INSERT INTO quizzes(module_id, title, pass_mark, active) VALUES(?,?,?,1)
                           ON CONFLICT(module_id) DO UPDATE SET title=excluded.title, pass_mark=excluded.pass_mark, active=1""",
                        (mid, qz.get("title", f"Questionário do Módulo {mod['num']}"), qz.get("pass_mark", 70)))
            qid = con.execute("SELECT id FROM quizzes WHERE module_id=?", (mid,)).fetchone()["id"]
            con.execute("DELETE FROM questions WHERE quiz_id=?", (qid,))
            for k, q in enumerate(questions):
                con.execute("INSERT INTO questions(quiz_id, code, text, options, correct, feedback, sort) VALUES(?,?,?,?,?,?,?)",
                            (qid, q["code"], q["text"], json.dumps(q["options"], ensure_ascii=False), q["correct"], q["feedback"], k))
            n_q += len(questions)
    return f"{meta['title']}: {len(meta.get('modules', []))} módulo(s), {n_lessons} aula(s), {n_q} pergunta(s)"


def import_all(con):
    report = []
    for folder in sorted(p for p in COURSES_DIR.iterdir() if (p / "curso.json").exists()):
        try:
            report.append("✓ " + import_pack(con, folder))
        except Exception as e:  # noqa: BLE001 - o relatório mostra o erro ao administrador
            report.append(f"✗ {folder.name}: {e}")
    return report


# ---------------------------------------------------------------------------
# Progresso
# ---------------------------------------------------------------------------

def course_progress(con, uid, cid):
    lessons = con.execute("""SELECT l.id, p.completed FROM lessons l LEFT JOIN lesson_progress p
                             ON p.lesson_id=l.id AND p.user_id=? WHERE l.course_id=? AND l.active=1""", (uid, cid)).fetchall()
    quizzes = con.execute("""SELECT q.id, q.pass_mark, (SELECT MAX(pct) FROM quiz_attempts a WHERE a.quiz_id=q.id AND a.user_id=?) best
                             FROM quizzes q JOIN modules m ON m.id=q.module_id
                             WHERE m.course_id=? AND m.active=1 AND q.active=1""", (uid, cid)).fetchall()
    done_l = sum(1 for r in lessons if r["completed"])
    done_q = sum(1 for r in quizzes if r["best"] is not None and r["best"] >= r["pass_mark"])
    total = len(lessons) + len(quizzes)
    return {"lessons": len(lessons), "lessons_done": done_l, "quizzes": len(quizzes), "quizzes_done": done_q,
            "pct": round(100 * (done_l + done_q) / total) if total else 0,
            "complete": total > 0 and done_l + done_q == total}


# ---------------------------------------------------------------------------
# Assistente de estudo (modelo local via Ollama, opcional)
# ---------------------------------------------------------------------------

_ollama = {"ok": False, "checked": 0.0}


def ollama_available():
    if time.time() - _ollama["checked"] > 60:
        _ollama["checked"] = time.time()
        try:
            with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=1.5) as r:
                names = [m.get("name", "") for m in json.load(r).get("models", [])]
                _ollama["ok"] = any(n == OLLAMA_MODEL or n.split(":")[0] == OLLAMA_MODEL for n in names)
        except (OSError, ValueError):
            _ollama["ok"] = False
    return _ollama["ok"]


def manual_text(course_slug, mod):
    if not mod["manual_json"]:
        return ""
    try:
        data = json.loads((COURSES_DIR / course_slug / mod["manual_json"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    parts = []
    for m in data.get("modules", []):
        for s in m.get("sections", []):
            parts.append(s["title"])
            for b in s.get("blocks", []):
                for k in ("p", "note", "tip", "warn"):
                    if k in b:
                        parts.append(b[k])
                if "steps" in b:
                    parts.extend(b["steps"])
                if "table" in b:
                    parts.extend(" | ".join(r) for r in b["table"])
        parts.extend(m.get("summary", []))
    return re.sub(r"\*\*", "", "\n".join(parts))


def ask_assistant(question, lesson, mod, course_slug):
    context = (f"TRANSCRIÇÃO DA AULA «{lesson['title']}»:\n{lesson['transcript'] or ''}\n\n"
               f"MANUAL DO MÓDULO:\n{manual_text(course_slug, mod)}")[:12000]
    system = ("És o assistente de estudo da ATC – Angbu Training Centre, em Angola. Respondes sempre em português "
              "europeu (PT-PT), de forma simples, curta e amável, a formandos que estão a começar. Usa apenas o "
              "conteúdo da aula e do manual abaixo. Se a resposta não estiver no conteúdo, diz que não sabes e "
              "sugere que coloque a pergunta ao formador na secção Perguntas.\n\n" + context)
    payload = json.dumps({"model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0.2},
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": question}]}).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["message"]["content"].strip()


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def h(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def md(s):
    """Texto com **negrito** → HTML seguro."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", h(s))


def fmt_dur(sec):
    if not sec:
        return ""
    sec = int(round(sec))
    return f"{sec // 60} min {sec % 60:02d} s" if sec >= 60 else f"{sec} s"


def fmt_date(s):
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return s or ""


def fmt_h(x):
    return f"{x:g}".replace(".", ",")


def bar(pct):
    return f'<div class="bar" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100"><span style="width:{pct}%"></span></div>'


def page(title, body, user=None, csrf="", wide=False, flash="", profile=None):
    if user:
        user = dict(user)
        user["name"] = (profile or {}).get("display_name") or user["name"]
    profile_color = (profile or {}).get("color", "sand")
    brand = '<a class="brand" href="/"><img src="/static/logo-200.png" alt=""><span><b>ATC</b> Formação<small>Angbu Training Centre</small></span></a>'
    sidebar = ""
    if user:
        links = [("/", "◫", "Os meus cursos"), ("/#catalogo", "▦", "Catálogo")]
        if user["role"] in ("admin", "formador"):
            links.append(("/admin", "▤", "Gestão"))
        links.append(("/conta", "◎", "A minha conta"))
        sidebar = ('<aside class="sidebar">' + brand + '<p class="nav-label">ESPAÇO DE FORMAÇÃO</p><nav aria-label="Navegação principal">' +
                   "".join(f'<a href="{u}"><span aria-hidden="true">{icon}</span>{t}</a>' for u, icon, t in links) +
                   '</nav><div class="sidebar-note"><span class="eyebrow">O SEU PRÓXIMO PASSO</span><h3>Aprender hoje.<br>Ir mais longe amanhã.</h3><p>Competências que fazem a diferença.</p></div>' +
                   f'<div class="profile"><span class="avatar avatar-{h(profile_color)}">{h(user["name"][:1].upper())}</span><div><b>{h(user["name"])}</b><small>{ROLES[user["role"]]}</small></div></div>' +
                   f'<form class="logout" method="post" action="/sair">{csrf_field(csrf)}<button class="linkbtn">Sair da conta →</button></form></aside>')
    flash_html = f'<div class="flash" role="status">{flash}</div>' if flash else ""
    header = (f'<div class="workspace-label">Área de aprendizagem <span>/</span> <b>{h(title)}</b></div><a class="account-link" href="/conta">{h(user["name"].split()[0])} <span class="avatar avatar-{h(profile_color)}">{h(user["name"][:1].upper())}</span></a>' if user else brand)
    return f"""<!doctype html><html lang="pt-PT"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(title)} · ATC Formação</title><link rel="icon" href="/static/logo-200.png">
<link rel="stylesheet" href="/static/atc.css?v=3"><meta name="csrf" content="{h(csrf)}"><script src="/static/ui.js?v=3" defer></script></head>
<body class="{'app' if user else 'public'}"><a class="skip-link" href="#conteudo">Saltar para o conteúdo</a>{sidebar}<div class="workspace"><header class="top"><div class="wrap">{header}</div></header>
<main id="conteudo" class="wrap{' wide' if wide else ''}">{flash_html}{body}</main>
<footer><div class="wrap"><span>ATC · Angbu Training Centre</span><span>Luanda, Angola · Aprendizagem com propósito</span></div></footer></div></body></html>"""


def csrf_field(csrf):
    return f'<input type="hidden" name="csrf" value="{h(csrf)}">'


# ---------------------------------------------------------------------------
# Servidor HTTP
# ---------------------------------------------------------------------------

class Redirect(Exception):
    def __init__(self, url):
        self.url = url


class HttpError(Exception):
    def __init__(self, code, msg=""):
        self.code, self.msg = code, msg


ROUTES = []


def route(method, pattern, role=None):
    """role: None = público, 'user' = sessão iniciada, 'staff' = formador/admin, 'admin'."""
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, role))
        return fn
    return deco


class Handler(BaseHTTPRequestHandler):
    server_version = "ATC-LMS/1.0"
    protocol_version = "HTTP/1.1"

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def log_message(self, fmt, *args):
        if os.environ.get("ATC_LOG"):
            super().log_message(fmt, *args)

    # -- utilitários -------------------------------------------------------
    def send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def form(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 5_000_000:
            raise HttpError(413, "Pedido demasiado grande.")
        raw = self.rfile.read(n) if n else b""
        if (self.headers.get("Content-Type") or "").startswith("application/json"):
            return json.loads(raw or b"{}")
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(), keep_blank_values=True).items()}

    def session(self, con):
        c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        tok = c[COOKIE].value if COOKIE in c else None
        if not tok:
            return None, ""
        row = con.execute("""SELECT u.*, s.csrf, s.created s_created FROM sessions s JOIN users u ON u.id=s.user_id
                             WHERE s.token=? AND u.active=1""", (tok,)).fetchone()
        if not row or time.time() - row["s_created"] > SESSION_DAYS * 86400:
            return None, ""
        return row, row["csrf"]

    def serve_file(self, path, download_name=None, ctype=None):
        if not path.is_file():
            raise HttpError(404)
        size = path.stat().st_size
        ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2) or 0))
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "private, max-age=3600")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download_name:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    # -- despacho ----------------------------------------------------------
    def do_GET(self):
        self.dispatch("GET")

    def do_HEAD(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def dispatch(self, method):
        url = urllib.parse.urlsplit(self.path)
        self.query = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        path = urllib.parse.unquote(url.path)
        con = db()
        try:
            if path.startswith("/static/"):
                target = (STATIC / path[8:]).resolve()
                if STATIC not in target.parents:
                    raise HttpError(404)
                return self.serve_file(target)
            user, csrf = self.session(con)
            for m, rx, fn, role in ROUTES:
                mt = rx.match(path)
                if m != method or not mt:
                    continue
                if role and not user:
                    raise Redirect("/entrar?seguinte=" + urllib.parse.quote(self.path))
                if role == "staff" and user["role"] not in ("admin", "formador"):
                    raise HttpError(403, "Esta página é apenas para formadores e administradores.")
                if role == "admin" and user["role"] != "admin":
                    raise HttpError(403, "Esta página é apenas para administradores.")
                self.data = {}
                if method == "POST":
                    self.data = self.form()
                    sent = self.data.get("csrf") or self.headers.get("X-CSRF")
                    if fn.__name__ != "login_post" and (not user or not hmac.compare_digest(str(sent or ""), csrf)):
                        raise HttpError(403, "Sessão expirada. Volte à página anterior e tente de novo.")
                self.user, self.csrf, self.con = user, csrf, con
                if user and method == "GET":
                    con.execute("UPDATE users SET last_seen=? WHERE id=?", (now(), user["id"]))
                    # Release the write lock before streaming a video or rendering a slow page.
                    con.commit()
                result = fn(self, *mt.groups())
                con.commit()
                if result is not None:
                    self.send(200, result)
                return
            raise HttpError(404)
        except Redirect as r:
            con.commit()
            self.send(303, "", headers={"Location": r.url})
        except HttpError as e:
            msg = e.msg or {404: "Página não encontrada.", 403: "Acesso negado."}.get(e.code, "Erro.")
            if self.path.startswith("/api/"):
                self.send(e.code, json.dumps({"erro": msg}), "application/json")
            else:
                self.send(e.code, page("Erro", f'<section class="card"><h1>{e.code}</h1><p>{h(msg)}</p>'
                                              f'<p><a class="btn" href="/">Voltar ao início</a></p></section>'))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            try:
                self.send(500, page("Erro", '<section class="card"><h1>Erro interno</h1><p>Ocorreu um erro. '
                                            'Consulte a janela do servidor.</p></section>'))
            except OSError:
                pass
        finally:
            con.close()

    # -- ajudas para as páginas --------------------------------------------
    def render(self, title, body, **kw):
        return page(title, body, self.user, self.csrf, profile=learner_profile(self), **kw)

    def is_staff(self):
        return self.user and self.user["role"] in ("admin", "formador")

    def course_for(self, slug, need_access=True):
        c = self.con.execute("SELECT * FROM courses WHERE slug=? AND active=1", (slug,)).fetchone()
        if not c:
            raise HttpError(404)
        if need_access and not self.can_access(c):
            raise HttpError(403, "Ainda não está inscrito neste curso. Fale com a ATC para se inscrever.")
        return c

    def can_access(self, c):
        if self.is_staff():
            return True
        return c["status"] == "publicado" and self.con.execute(
            "SELECT 1 FROM enrolments WHERE user_id=? AND course_id=?", (self.user["id"], c["id"])).fetchone() is not None


# ---------------------------------------------------------------------------
# Páginas: entrada e conta
# ---------------------------------------------------------------------------

@route("GET", "/entrar")
def login_get(r, error=""):
    demo = ""
    if setting(r.con, "demo") == "1":
        demo = ('<div class="demo"><b>Contas de demonstração</b><br>Formando: formando@atc.ao / formando123<br>'
                'Formador: formador@atc.ao / formador123<br>Administrador: admin@atc.ao / admin123</div>')
    err = f'<p class="error">{h(error)}</p>' if error else ""
    nxt = h(r.query.get("seguinte", "/"))
    return page("Entrar", f"""<div class="login-layout"><section class="login-story"><span class="eyebrow">ANGBU TRAINING CENTRE</span><h1>O seu futuro<br>começa com<br><em>conhecimento.</em></h1><p>Desenvolva competências digitais, aprenda ao seu ritmo e prepare o próximo passo da sua carreira.</p><div class="login-benefits"><span>01 / Aulas em vídeo</span><span>02 / Aprendizagem prática</span><span>03 / Certificado de conclusão</span></div></section><section class="login card"><img src="/static/logo-600.png" alt="ATC – Angbu Training Centre">
<span class="eyebrow">A SUA ÁREA DE FORMAÇÃO</span><h1>Bem-vindo de volta.</h1><p class="muted">Entre para continuar o seu percurso.</p>{err}<form method="post" action="/entrar"><input type="hidden" name="seguinte" value="{nxt}">
<label>Email<input type="email" name="email" required autofocus autocomplete="username"></label>
<label>Palavra-passe<input type="password" name="pw" required autocomplete="current-password"></label>
<button class="btn">Entrar na plataforma →</button></form>{demo}</section></div>""")


@route("POST", "/entrar")
def login_post(r):
    email, pw = r.data.get("email", "").strip().lower(), r.data.get("pw", "")
    u = r.con.execute("SELECT * FROM users WHERE email=? AND active=1", (email,)).fetchone()
    if not u or not check_pw(pw, u["pw_hash"]):
        time.sleep(0.5)
        r.query = {"seguinte": r.data.get("seguinte", "/")}
        r.send(200, login_get(r, "Email ou palavra-passe incorretos."))
        return None
    tok = secrets.token_urlsafe(32)
    r.con.execute("DELETE FROM sessions WHERE created < ?", (time.time() - SESSION_DAYS * 86400,))
    r.con.execute("INSERT INTO sessions VALUES(?,?,?,?)", (tok, u["id"], secrets.token_urlsafe(24), time.time()))
    r.con.commit()
    nxt = r.data.get("seguinte", "/")
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    r.send(303, "", headers={"Location": nxt, "Set-Cookie":
           f"{COOKIE}={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS * 86400}"})


@route("POST", "/sair", "user")
def logout(r):
    c = cookies.SimpleCookie(r.headers.get("Cookie", ""))
    if COOKIE in c:
        r.con.execute("DELETE FROM sessions WHERE token=?", (c[COOKIE].value,))
    r.con.commit()
    r.send(303, "", headers={"Location": "/entrar", "Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0"})


def learner_profile(r):
    row = r.con.execute("SELECT * FROM learner_profiles WHERE user_id=?", (r.user["id"],)).fetchone()
    return dict(row) if row else {"display_name": r.user["name"], "occupation": "", "goal": "", "color": "sand"}


def selected_presenter(r, cid):
    row = r.con.execute("SELECT presenter FROM course_presenters WHERE user_id=? AND course_id=?", (r.user["id"], cid)).fetchone()
    return row["presenter"] if row else None


@route("POST", "/conta/perfil", "user")
def profile_save(r):
    name = r.data.get("display_name", "").strip()
    occupation = r.data.get("occupation", "").strip()
    goal = r.data.get("goal", "").strip()
    color = r.data.get("color", "sand")
    if not 1 <= len(name) <= 60 or len(occupation) > 100 or len(goal) > 300 or color not in PROFILE_COLORS:
        raise HttpError(400, "Verifique o nome, a cor e os limites dos campos do perfil.")
    r.con.execute("""INSERT INTO learner_profiles VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
        display_name=excluded.display_name, occupation=excluded.occupation, goal=excluded.goal,
        color=excluded.color, updated=excluded.updated""", (r.user["id"], name, occupation, goal, color, now()))
    raise Redirect("/conta?guardado=1")


@route("GET", "/conta", "user")
def account(r, flash=""):
    profile = learner_profile(r)
    if r.query.get("guardado") == "1":
        flash = "Perfil atualizado."
    colors = "".join(f'<label class="color-choice"><input type="radio" name="color" value="{key}" {"checked" if profile["color"] == key else ""}><span class="color-swatch avatar-{key}"></span>{label}</label>' for key, label in PROFILE_COLORS.items())
    profile_form = f'''<section class="card profile-editor"><div class="profile-intro"><span class="avatar avatar-large avatar-{h(profile['color'])}">{h(profile['display_name'][:1].upper())}</span><div><span class="eyebrow">O SEU ESPAÇO</span><h2>Um perfil à sua medida</h2><p class="muted">Personalize a forma como aparece na plataforma.</p></div></div>
<form method="post" action="/conta/perfil">{csrf_field(r.csrf)}<div class="grid2"><label>Nome de apresentação<input name="display_name" maxlength="60" required value="{h(profile['display_name'])}" autocomplete="nickname"></label><label>Profissão ou área de interesse<input name="occupation" maxlength="100" value="{h(profile['occupation'])}" placeholder="Ex.: Administração, informática, gestão"></label></div>
<label>O que gostaria de aprender?<textarea name="goal" maxlength="300" rows="3" placeholder="O seu objetivo de aprendizagem…">{h(profile['goal'])}</textarea></label>
<fieldset class="profile-colors"><legend>Cor do perfil</legend>{colors}</fieldset><p class="muted">O nome nos certificados mantém-se: {h(r.user['name'])}.</p><button class="btn">Guardar perfil</button></form></section>'''
    certs = r.con.execute("""SELECT c.code, c.issued, co.title FROM certificates c JOIN courses co ON co.id=c.course_id
                             WHERE c.user_id=?""", (r.user["id"],)).fetchall()
    cert_html = "".join(f'<li><a href="/certificado/{h(c["code"])}">{h(c["title"])}</a> · {fmt_date(c["issued"])[:10]}</li>'
                        for c in certs) or "<li>Ainda não tem certificados.</li>"
    return r.render("A minha conta", f"""<h1>A minha conta</h1>{profile_form}<div class="grid2">
<section class="card"><h2>Dados</h2><p><b>{h(r.user['name'])}</b><br>{h(r.user['email'])}<br>{ROLES[r.user['role']]}</p>
<h2>Certificados</h2><ul>{cert_html}</ul></section>
<section class="card"><h2>Alterar palavra-passe</h2><form method="post" action="/conta">{csrf_field(r.csrf)}
<label>Palavra-passe atual<input type="password" name="atual" required></label>
<label>Nova palavra-passe (mín. 6 caracteres)<input type="password" name="nova" minlength="6" required></label>
<button class="btn">Guardar</button></form></section></div>""", flash=flash)


@route("POST", "/conta", "user")
def account_post(r):
    if not check_pw(r.data.get("atual", ""), r.user["pw_hash"]):
        return account(r, "A palavra-passe atual não está correta.")
    if len(r.data.get("nova", "")) < 6:
        return account(r, "A nova palavra-passe tem de ter pelo menos 6 caracteres.")
    r.con.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(r.data["nova"]), r.user["id"]))
    return account(r, "Palavra-passe alterada.")


# ---------------------------------------------------------------------------
# Páginas: cursos
# ---------------------------------------------------------------------------

def course_card(r, c, enrolled):
    cover = (f'<img src="/media/{h(c["slug"])}/{h(c["cover"])}" alt="" loading="lazy">' if c["cover"]
             else f'<div class="ph ph-{h(c["slug"])}"><span class="course-monogram">{h({"word": "W", "excel": "X", "powerpoint": "P", "outlook": "O", "comptia-a-plus": "A+", "comptia-network-plus": "N+"}.get(c["slug"], "ATC"))}</span><span class="cover-caption">ATC · FORMAÇÃO PROFISSIONAL</span></div>')
    hours = f'{fmt_h(c["hours_video"])} h de vídeo' if c["hours_video"] else ""
    if c["status"] != "publicado":
        foot = f'<span class="tag soon">Em breve</span> <span class="muted">{hours}</span>'
        return f'<article class="course soon">{cover}<div><h3>{h(c["title"])}</h3><p>{h(c["subtitle"])}</p>{foot}</div></article>'
    if enrolled or r.is_staff():
        p = course_progress(r.con, r.user["id"], c["id"])
        label = "Concluído" if p["complete"] else (f'{p["pct"]}% concluído' if p["pct"] else "Começar")
        foot = f'{bar(p["pct"])}<span class="muted">{label} · {hours}</span>'
        return (f'<a class="course" href="/cursos/{h(c["slug"])}">{cover}<div><h3>{h(c["title"])}</h3>'
                f'<p>{h(c["subtitle"])}</p>{foot}</div></a>')
    return (f'<article class="course locked">{cover}<div><h3>{h(c["title"])}</h3><p>{h(c["subtitle"])}</p>'
            f'<span class="tag">Inscrição na ATC</span> <span class="muted">{hours}</span></div></article>')


@route("GET", "/", "user")
def home(r):
    courses = r.con.execute("SELECT * FROM courses WHERE active=1 ORDER BY sort, title").fetchall()
    enrolled = {row["course_id"] for row in r.con.execute("SELECT course_id FROM enrolments WHERE user_id=?", (r.user["id"],))}
    mine = [c for c in courses if c["id"] in enrolled and c["status"] == "publicado"]
    others = [c for c in courses if c not in mine]
    profile = learner_profile(r)
    first = profile["display_name"].split()[0] if profile["display_name"] else ""
    mine_html = ("".join(course_card(r, c, True) for c in mine) if mine else
                 '<p class="muted">Ainda não está inscrito em nenhum curso. Fale com a ATC para se inscrever.</p>')
    progress = [course_progress(r.con, r.user["id"], c["id"]) for c in mine]
    completed = sum(p["complete"] for p in progress)
    lessons_done = sum(p["lessons_done"] for p in progress)
    cert_count = r.con.execute("SELECT COUNT(*) FROM certificates WHERE user_id=?", (r.user["id"],)).fetchone()[0]
    feature = ""
    target = next((c for c, p in zip(mine, progress) if not p["complete"]), mine[0] if mine else None)
    if target:
        p = course_progress(r.con, r.user["id"], target["id"])
        lesson = r.con.execute("""SELECT l.* FROM lessons l LEFT JOIN lesson_progress p ON p.lesson_id=l.id AND p.user_id=?
            WHERE l.course_id=? AND l.active=1 AND COALESCE(p.completed,0)=0 ORDER BY l.sort LIMIT 1""", (r.user["id"], target["id"])).fetchone()
        url = f'/cursos/{target["slug"]}' + (f'/aula/{lesson["slug"]}' if lesson else '')
        if not selected_presenter(r, target["id"]):
            url = f'/cursos/{target["slug"]}/apresentador'
        label = "Continuar a aprender" if p["pct"] or (lesson and r.con.execute("SELECT 1 FROM lesson_progress WHERE user_id=? AND lesson_id=? AND position>0", (r.user["id"], lesson["id"])).fetchone()) else "Começar a aprender"
        if p["complete"]:
            label = "Rever o curso"
        feature = f'''<section class="featured"><div class="featured-copy"><span class="eyebrow">O SEU PERCURSO · INFORMÁTICA E TECNOLOGIA</span>
<h2>{h(target['title'])}</h2><p>{h(lesson['title'] if lesson else 'Reveja os conteúdos e consulte o seu progresso.')}</p>
<a class="btn" href="{h(url)}">{label} <span aria-hidden="true">↗</span></a><div class="feature-progress"><span>{p['pct']}% concluído</span><span>{p['lessons_done']} de {p['lessons']} aulas</span>{bar(p['pct'])}</div></div>
<div class="featured-art" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="art-window"><div class="window-dots">● ● ●</div><span class="art-symbol">⌘</span><div class="art-line"></div><div class="art-line short"></div><span class="art-label">O conhecimento abre portas.</span></div><span class="art-badge">ATC / ACADEMIA DIGITAL</span></div></section>'''
    else:
        feature = '<section class="welcome-empty card"><span class="eyebrow">O SEU PERCURSO COMEÇA AQUI</span><h2>Novas competências. Novas possibilidades.</h2><p>Explore a oferta de formação e fale com a ATC para se inscrever.</p><a class="btn" href="#catalogo">Explorar catálogo ↗</a></section>'
    profile_hint = (f'<section class="profile-prompt"><div><b>Bem-vindo à sua academia.</b><span>Personalize o perfil e conte-nos o que gostaria de aprender.</span></div><a class="btn ghost small" href="/conta">Personalizar perfil →</a></section>' if not r.con.execute("SELECT 1 FROM learner_profiles WHERE user_id=?", (r.user["id"],)).fetchone() else (f'<section class="profile-prompt"><div><span class="eyebrow">O SEU OBJETIVO</span><b>{h(profile["goal"])}</b></div><a href="/conta">Editar</a></section>' if profile['goal'] else ''))
    return r.render("Os meus cursos", f'''{profile_hint}<div class="page-heading"><div><span class="eyebrow">A SUA ACADEMIA DIGITAL</span><h1>Olá, {h(first)}<span class="greeting-dot">.</span></h1><p class="muted">É um bom dia para dar o próximo passo.</p></div><span class="learning-badge">● Ao seu ritmo. Com a ATC.</span></div>
<div class="learning-stats"><div><span class="stat-icon">◫</span><div><b>{len(mine):02d}</b><span>Cursos inscritos</span></div></div><div><span class="stat-icon">✓</span><div><b>{lessons_done:02d}</b><span>Aulas concluídas</span></div></div><div><span class="stat-icon">◎</span><div><b>{cert_count:02d}</b><span>Certificados obtidos</span></div></div></div>
{feature}<div class="section-heading"><div><span class="eyebrow">PASSO A PASSO</span><h2>Os meus cursos <span class="count">{len(mine)}</span></h2></div><span class="muted">{completed} concluídos</span></div><div class="courses my-courses">{mine_html}</div>
<section id="catalogo"><div class="section-heading"><div><span class="eyebrow">CONTINUE A DESCOBRIR</span><h2>Explore o catálogo</h2></div><label class="catalog-search"><span class="sr-only">Pesquisar cursos no catálogo</span><input id="course-search" type="search" placeholder="Pesquisar cursos…" aria-controls="catalog-courses"></label></div>
<div class="courses" id="catalog-courses">{''.join(course_card(r, c, False) for c in others)}</div><p id="catalog-empty" class="card muted" hidden role="status">Não foram encontrados cursos. Experimente outro termo.</p></section>''')


def lesson_state(r, lesson_ids):
    if not lesson_ids:
        return {}
    q = ",".join("?" * len(lesson_ids))
    return {row["lesson_id"]: row for row in r.con.execute(
        f"SELECT * FROM lesson_progress WHERE user_id=? AND lesson_id IN ({q})", (r.user["id"], *lesson_ids))}


@route("GET", "/cursos/([a-z0-9-]+)/apresentador", "user")
def presenter_page(r, slug):
    c = r.course_for(slug)
    selected = selected_presenter(r, c["id"])
    cards = "".join(f'''<label class="presenter-option"><input type="radio" name="presenter" value="{key}" required {"checked" if key == selected else ""}><span class="presenter-portrait"><img src="/static/presenters/{key}.png" alt="{p['name']}, {p['label'].lower()}, com vestuário profissional"><span class="selection-check" aria-hidden="true">✓</span></span><span class="presenter-info"><span class="eyebrow">{p['label']}</span><strong>{p['name']}</strong><span>O seu guia virtual na formação ATC.</span></span></label>''' for key, p in PRESENTERS.items())
    return r.render("Escolher apresentador", f'''<p class="crumbs"><a href="/cursos/{slug}">{h(c['title'])}</a> › Apresentador</p><section class="presenter-heading"><span class="eyebrow">UMA FORMAÇÃO À SUA MEDIDA</span><h1>Quem vai acompanhar<br>o seu percurso?</h1><p>Escolha a Helena ou o Miguel. O conteúdo e a avaliação são iguais.<br>Pode mudar a sua escolha a qualquer momento.</p></section><form method="post" action="/cursos/{slug}/apresentador">{csrf_field(r.csrf)}<div class="presenter-options">{cards}</div><div class="presenter-submit"><p class="muted">Personagens virtuais criadas para a ATC.</p><button class="btn">Guardar e conhecer o apresentador →</button></div></form>''')


@route("POST", "/cursos/([a-z0-9-]+)/apresentador", "user")
def presenter_save(r, slug):
    c = r.course_for(slug)
    key = r.data.get("presenter", "")
    if key not in PRESENTERS:
        raise HttpError(400, "Escolha um dos apresentadores disponíveis.")
    r.con.execute("""INSERT INTO course_presenters VALUES(?,?,?,?) ON CONFLICT(user_id,course_id)
        DO UPDATE SET presenter=excluded.presenter, updated=excluded.updated""", (r.user["id"], c["id"], key, now()))
    raise Redirect(f"/cursos/{slug}/introducao")


def presenter_banner(r, c):
    key = selected_presenter(r, c["id"])
    if not key:
        return f'<section class="profile-prompt"><div><b>Escolha o seu apresentador</b><span>Helena ou Miguel: a formação ao seu ritmo.</span></div><a class="btn small" href="/cursos/{h(c["slug"])}/apresentador">Escolher →</a></section>'
    return f'<section class="presenter-banner"><img src="/static/presenters/{key}.png" alt=""><div><span class="eyebrow">O SEU GUIA VIRTUAL</span><b>{PRESENTERS[key]["name"]}</b></div><a href="/cursos/{h(c["slug"])}/introducao">Introdução</a><a href="/cursos/{h(c["slug"])}/apresentador">Mudar apresentador</a></section>'


@route("GET", "/cursos/([a-z0-9-]+)/introducao", "user")
def presenter_intro(r, slug):
    c = r.course_for(slug)
    key = selected_presenter(r, c["id"])
    if not key:
        raise Redirect(f"/cursos/{slug}/apresentador")
    name = PRESENTERS[key]["name"]
    scripts = json.loads((STATIC / "presenters/scripts.json").read_text(encoding="utf-8"))
    intro = scripts[key]["courses"].get(slug, scripts[key]["welcome"])
    video = COURSES_DIR / slug / "apresentadores" / f"{key}-introducao.mp4"
    intro_track = (f'<track kind="subtitles" srclang="pt" label="Português" src="/media/{slug}/apresentadores/{key}-introducao.vtt" default>' if video.with_suffix('.vtt').is_file() else '')
    media = (f'<video controls playsinline preload="metadata" poster="/static/presenters/{key}.png"><source src="/media/{slug}/apresentadores/{key}-introducao.mp4" type="video/mp4">{intro_track}</video>' if video.is_file() else f'<img src="/static/presenters/{key}.png" alt="{name}, apresentador virtual">')
    availability = '' if video.is_file() else '<p class="muted intro-status">Apresentação em texto. O vídeo deste apresentador ainda não está disponível.</p>'
    lesson = r.con.execute("""SELECT l.slug FROM lessons l LEFT JOIN lesson_progress p ON p.lesson_id=l.id AND p.user_id=?
        WHERE l.course_id=? AND l.active=1 AND COALESCE(p.completed,0)=0 ORDER BY l.sort LIMIT 1""", (r.user["id"], c["id"])).fetchone()
    url = f'/cursos/{slug}/aula/{lesson["slug"]}' if lesson else f'/cursos/{slug}'
    return r.render(f"Conheça {name}", f'''<p class="crumbs"><a href="/cursos/{slug}">{h(c['title'])}</a> › Introdução</p><section class="intro-layout"><div class="intro-media">{media}</div><div class="intro-copy"><span class="eyebrow">O SEU GUIA VIRTUAL · ATC</span><h1>Olá, sou {"a" if key == "helena" else "o"} {name}.</h1><p class="lead">{h(c['title'])}</p><div class="intro-script">{''.join(f'<p>{h(line)}</p>' for line in intro.split(chr(10)) if line)}</div>{availability}<div class="actions"><a class="btn" href="{h(url)}">{"Ir para a aula" if lesson else "Voltar ao curso"} →</a><a class="btn ghost" href="/cursos/{slug}/apresentador">Mudar apresentador</a></div></div></section>''')


@route("GET", "/cursos/([a-z0-9-]+)", "user")
def course_page(r, slug):
    c = r.course_for(slug)
    mods = r.con.execute("SELECT * FROM modules WHERE course_id=? AND active=1 ORDER BY num", (c["id"],)).fetchall()
    lessons = r.con.execute("SELECT * FROM lessons WHERE course_id=? AND active=1 ORDER BY sort", (c["id"],)).fetchall()
    state = lesson_state(r, [l["id"] for l in lessons])
    p = course_progress(r.con, r.user["id"], c["id"])
    next_lesson = next((l for l in lessons if not (state.get(l["id"]) and state[l["id"]]["completed"])), None)
    out = []
    for m in mods:
        items = []
        for l in (l for l in lessons if l["module_id"] == m["id"]):
            st = state.get(l["id"])
            done = st and st["completed"]
            icon = '<span class="ok" title="Vista">✓</span>' if done else '<span class="todo">▶</span>'
            items.append(f'<li>{icon}<a href="/cursos/{slug}/aula/{h(l["slug"])}">{h(l["title"])}</a>'
                         f'<span class="muted">{fmt_dur(l["duration"])}</span></li>')
        quiz = r.con.execute("SELECT * FROM quizzes WHERE module_id=? AND active=1", (m["id"],)).fetchone()
        if quiz:
            best = r.con.execute("SELECT MAX(pct) b, COUNT(*) n FROM quiz_attempts WHERE quiz_id=? AND user_id=?",
                                 (quiz["id"], r.user["id"])).fetchone()
            passed = best["b"] is not None and best["b"] >= quiz["pass_mark"]
            icon = '<span class="ok">✓</span>' if passed else '<span class="todo">?</span>'
            info = f'Melhor resultado: {best["b"]}%' if best["n"] else f'Aprovação com {quiz["pass_mark"]}%'
            items.append(f'<li>{icon}<a href="/cursos/{slug}/modulo/{m["num"]}/questionario">{h(quiz["title"])}</a>'
                         f'<span class="muted">{info}</span></li>')
        res = []
        if m["manual_json"]:
            res.append(f'<a class="btn ghost" href="/cursos/{slug}/modulo/{m["num"]}/manual">Ler o manual</a>')
        if m["manual_docx"]:
            res.append(f'<a class="btn ghost" href="/media/{slug}/{h(m["manual_docx"])}?descarregar=1">Descarregar manual (Word)</a>')
        out.append(f'<section class="card module"><h2><span class="num">Módulo {m["num"]}</span>{h(m["title"])}</h2>'
                   f'<p>{h(m["intro"])}</p><ul class="items">{"".join(items)}</ul><div class="actions">{"".join(res)}</div></section>')
    cert = r.con.execute("SELECT code FROM certificates WHERE user_id=? AND course_id=?", (r.user["id"], c["id"])).fetchone()
    if cert:
        cert_html = f'<a class="btn" href="/certificado/{h(cert["code"])}">Ver certificado</a>'
    elif p["complete"]:
        cert_html = (f'<form method="post" action="/cursos/{slug}/certificado">{csrf_field(r.csrf)}'
                     f'<button class="btn">Obter certificado</button></form>')
    else:
        cert_html = '<p class="muted">O certificado fica disponível quando concluir todas as aulas e questionários.</p>'
    cont = (f'<a class="btn" href="/cursos/{slug}/aula/{h(next_lesson["slug"])}">'
            f'{"Continuar" if p["pct"] else "Começar"}: {h(next_lesson["title"])}</a>' if next_lesson else "")
    hours = " · ".join(x for x in [f'{fmt_h(c["hours_video"])} h de vídeo' if c["hours_video"] else "",
                                   f'{fmt_h(c["hours_class"])} h presenciais' if c["hours_class"] else ""] if x)
    staff = (f' <a class="btn ghost" href="/admin/relatorio/{slug}">Relatório de turma</a>' if r.is_staff() else "")
    sample = ""
    if slug == "informatica" and (COURSES_DIR / slug / "video/amostra-windows-atc.mp4").is_file():
        sample = '''<section class="card module" id="amostra-windows">
<span class="eyebrow">AMOSTRA ATC · 32 SEGUNDOS</span><h2>Primeiros passos no Windows</h2>
<p>Explore os ecrãs personalizados com Helena e Miguel. Quatro cenas de 8 segundos, com legendas em português europeu.</p>
<video controls playsinline preload="none" style="width:100%;max-height:640px;border-radius:12px"
poster="/media/informatica/video/amostra-windows-atc.png" aria-label="Amostra ATC: primeiros passos no Windows">
<source src="/media/informatica/video/amostra-windows-atc.mp4" type="video/mp4">
O seu navegador não suporta vídeo.</video>
<p class="muted">Simulação pedagógica com imagens editadas. Amostra sem áudio, preparada para as vozes dos formadores.</p>
<div class="actions"><a class="btn ghost" href="/media/informatica/video/amostra-windows-atc.mp4?descarregar=1">Descarregar amostra</a>
<a class="btn ghost" href="/media/informatica/video/amostra-windows-atc.vtt?descarregar=1">Descarregar legendas</a></div></section>'''
    return r.render(c["title"], f"""<p class="crumbs"><a href="/">Os meus cursos</a></p>
{presenter_banner(r, c)}<section class="hero"><div><h1>{h(c['title'])}</h1><p class="lead">{h(c['subtitle'])}</p><p>{h(c['description'])}</p>
<p class="muted">{hours}</p><div class="actions">{cont}{staff}</div></div>
<aside class="card"><h3>O seu progresso</h3>{bar(p['pct'])}<p><b>{p['pct']}%</b> · {p['lessons_done']}/{p['lessons']} aulas ·
{p['quizzes_done']}/{p['quizzes']} questionários</p>{cert_html}</aside></section>{sample}{''.join(out)}""")


def lesson_media(slug, lesson, presenter):
    """Optional presenter videos: separate timelines, shared lesson completion."""
    rel = f"apresentadores/{presenter}/{lesson['slug']}.mp4"
    root = COURSES_DIR / slug
    if presenter in PRESENTERS and (root / rel).is_file():
        duration = mp4_duration(root / rel)
        if duration and duration > 0:
            sub = rel[:-4] + ".vtt"
            return {"key": presenter, "video": rel, "duration": duration,
                    "subtitles": sub if (root / sub).is_file() else None}
    return {"key": "original", "video": lesson["video"], "duration": lesson["duration"], "subtitles": None}


@route("GET", "/cursos/([a-z0-9-]+)/aula/([a-z0-9-]+)", "user")
def lesson_page(r, slug, lslug):
    c = r.course_for(slug)
    l = r.con.execute("SELECT * FROM lessons WHERE course_id=? AND slug=? AND active=1", (c["id"], lslug)).fetchone()
    if not l:
        raise HttpError(404)
    if not selected_presenter(r, c["id"]):
        raise Redirect(f"/cursos/{slug}/apresentador")
    m = r.con.execute("SELECT * FROM modules WHERE id=?", (l["module_id"],)).fetchone()
    seq = r.con.execute("SELECT slug, title FROM lessons WHERE course_id=? AND active=1 ORDER BY sort", (c["id"],)).fetchall()
    idx = [s["slug"] for s in seq].index(lslug)
    prev = seq[idx - 1] if idx > 0 else None
    nxt = seq[idx + 1] if idx + 1 < len(seq) else None
    st = r.con.execute("SELECT * FROM lesson_progress WHERE user_id=? AND lesson_id=?", (r.user["id"], l["id"])).fetchone()
    medium = lesson_media(slug, l, selected_presenter(r, c["id"]))
    timeline = st
    if medium["key"] != "original":
        timeline = r.con.execute("SELECT * FROM presenter_progress WHERE user_id=? AND lesson_id=? AND presenter=?", (r.user["id"], l["id"], medium["key"])).fetchone()
    pos = timeline["position"] if timeline else 0
    seen = timeline["seen"] if timeline else ""
    quiz = r.con.execute("SELECT 1 FROM quizzes WHERE module_id=? AND active=1", (m["id"],)).fetchone()
    nav = []
    nav.append(f'<a class="btn ghost" href="/cursos/{slug}/aula/{h(prev["slug"])}">← {h(prev["title"])}</a>' if prev else "<span></span>")
    if nxt:
        nav.append(f'<a class="btn" href="/cursos/{slug}/aula/{h(nxt["slug"])}">{h(nxt["title"])} →</a>')
    elif quiz:
        nav.append(f'<a class="btn" href="/cursos/{slug}/modulo/{m["num"]}/questionario">Fazer o questionário →</a>')
    track = (f'<track kind="subtitles" srclang="pt" label="Português" src="/legendas/{l["id"]}.vtt"'
             f'{" default" if l["subtitles_on"] else ""}>' if l["subtitles"] else "")
    if medium["key"] != "original":
        track = (f'<track kind="subtitles" srclang="pt" label="Português" src="/media/{slug}/{medium["subtitles"]}" default>' if medium["subtitles"] else '')
    poster = f' poster="/media/{slug}/{h(l["poster"])}"' if l["poster"] else ""
    if medium["key"] != "original":
        poster = f' poster="/static/presenters/{medium["key"]}.png"'
    transcript_text = l["transcript"] or ""
    if medium["key"] != "original":
        transcript_text = "\n".join(t for _, _, t in parse_subtitles((COURSES_DIR / slug / medium["subtitles"]).read_text(encoding="utf-8-sig"))) if medium["subtitles"] else ""
    transcript = "".join(f"<p>{h(t)}</p>" for t in transcript_text.split("\n") if t)
    media_note = '<p class="muted">Vídeo de demonstração comum aos dois apresentadores. A versão com o seu avatar ainda não está disponível.</p>' if medium["key"] == "original" else '' 
    comments = r.con.execute("""SELECT cm.*, u.name, u.role FROM comments cm JOIN users u ON u.id=cm.user_id
                                WHERE cm.lesson_id=? ORDER BY cm.created""", (l["id"],)).fetchall()

    def thread(parent):
        items = []
        for cm in (x for x in comments if x["parent_id"] == parent):
            badge = f'<span class="tag">{ROLES[cm["role"]]}</span>' if cm["role"] != "formando" else ""
            reply = ""
            if parent is None:
                reply = (f'<details class="reply"><summary>Responder</summary><form method="post" '
                         f'action="/cursos/{slug}/aula/{lslug}/comentar">{csrf_field(r.csrf)}'
                         f'<input type="hidden" name="parent" value="{cm["id"]}"><textarea name="body" required rows="2"></textarea>'
                         f'<button class="btn small">Enviar</button></form></details>')
            items.append(f'<li><div class="meta"><b>{h(cm["name"])}</b> {badge} <span class="muted">{fmt_date(cm["created"])}</span></div>'
                         f'<div>{h(cm["body"])}</div>{reply}<ul>{thread(cm["id"])}</ul></li>')
        return "".join(items)

    assistant = ""
    if ollama_available():
        assistant = f"""<section class="card"><h2>Assistente de estudo</h2>
<p class="muted">Faça uma pergunta sobre esta aula. O assistente responde com base no vídeo e no manual.</p>
<form id="ask"><textarea name="q" rows="2" required placeholder="Ex.: Qual é a diferença entre hardware e software?"></textarea>
<button class="btn small">Perguntar</button></form><div id="answer" class="answer" hidden></div></section>"""
    return r.render(l["title"], f"""<p class="crumbs"><a href="/">Os meus cursos</a> › <a href="/cursos/{slug}">{h(c['title'])}</a> › Módulo {m['num']}</p>
{presenter_banner(r, c)}<h1>{h(l['title'])}</h1>
{media_note}<div class="player"><video id="v" controls preload="metadata" playsinline{poster} data-lesson="{l['id']}" data-media="{medium['key']}" data-pos="{pos}" data-seen="{h(seen)}">
<source src="/media/{slug}/{h(medium['video'])}">{track}O seu navegador não suporta vídeo.</video></div>
<p id="status" class="{'okmsg' if st and st['completed'] else 'muted'}">{'✓ Aula concluída' if st and st['completed'] else 'Veja a aula até ao fim para a marcar como concluída.'}</p>
<div class="lessonnav">{''.join(nav)}</div>
<div class="grid2"><section class="card"><h2>Sobre esta aula</h2><p>{h(l['summary'])}</p>
<details><summary>Transcrição</summary><div class="transcript">{transcript or '<p class="muted">Sem transcrição.</p>'}</div></details>
<p class="actions">{f'<a class="btn ghost small" href="/cursos/{slug}/modulo/{m["num"]}/manual">Ler o manual do módulo</a>' if m['manual_json'] else ''}</p></section>
{assistant}</div>
<section class="card" id="perguntas"><h2>Perguntas e dúvidas</h2><p class="muted">Deixe aqui a sua dúvida. O formador responde nesta página.</p>
<ul class="comments">{thread(None) or '<li class="muted">Ainda não há perguntas sobre esta aula.</li>'}</ul>
<form method="post" action="/cursos/{slug}/aula/{lslug}/comentar">{csrf_field(r.csrf)}
<textarea name="body" rows="3" required placeholder="Escreva a sua pergunta…"></textarea><button class="btn small">Publicar pergunta</button></form></section>
<script src="/static/player.js?v=3"></script>""")


@route("POST", "/cursos/([a-z0-9-]+)/aula/([a-z0-9-]+)/comentar", "user")
def comment_post(r, slug, lslug):
    c = r.course_for(slug)
    l = r.con.execute("SELECT id FROM lessons WHERE course_id=? AND slug=?", (c["id"], lslug)).fetchone()
    body = r.data.get("body", "").strip()[:4000]
    if l and body:
        parent = r.data.get("parent")
        parent = int(parent) if parent and parent.isdigit() else None
        r.con.execute("INSERT INTO comments(lesson_id, user_id, parent_id, body, created) VALUES(?,?,?,?,?)",
                      (l["id"], r.user["id"], parent, body, now()))
    raise Redirect(f"/cursos/{slug}/aula/{lslug}#perguntas")


@route("GET", r"/legendas/(\d+)\.vtt", "user")
def subtitles(r, lid):
    l = r.con.execute("SELECT l.*, c.slug cslug FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=?", (lid,)).fetchone()
    if not l or not l["subtitles"]:
        raise HttpError(404)
    r.course_for(l["cslug"])
    text = (COURSES_DIR / l["cslug"] / l["subtitles"]).read_text(encoding="utf-8-sig")
    r.send(200, text if text.lstrip().startswith("WEBVTT") else to_vtt(text), "text/vtt; charset=utf-8")


@route("GET", "/media/([a-z0-9-]+)/(.+)", "user")
def media(r, slug, rel):
    c = r.course_for(slug, need_access=False)
    if rel != c["cover"] and not r.can_access(c):
        raise HttpError(403)
    root = (COURSES_DIR / slug).resolve()
    target = (root / rel).resolve()
    if root not in target.parents:
        raise HttpError(404)
    r.serve_file(target, download_name=target.name if r.query.get("descarregar") else None)


@route("POST", "/api/progresso", "user")
def progress_api(r):
    lid = int(r.data.get("lesson", 0))
    l = r.con.execute("SELECT l.*, c.slug cslug FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=?", (lid,)).fetchone()
    if not l:
        raise HttpError(404)
    r.course_for(l["cslug"])
    key = str(r.data.get("media", "original"))
    if key not in ("original", *PRESENTERS):
        raise HttpError(400, "Versão de vídeo inválida.")
    medium = lesson_media(l["cslug"], l, key)
    if medium["key"] != key:
        raise HttpError(400, "Esta versão de vídeo não está disponível.")
    try:
        pos = float(r.data.get("pos", 0))
        dur = medium["duration"] or float(r.data.get("dur", 0))
        if not math.isfinite(pos) or not math.isfinite(dur) or dur <= 0 or dur > 20000:
            raise ValueError()
    except (TypeError, ValueError):
        raise HttpError(400, "Progresso inválido.")
    pos = max(0, min(pos, dur))
    st = r.con.execute("SELECT * FROM lesson_progress WHERE user_id=? AND lesson_id=?", (r.user["id"], lid)).fetchone()
    timeline = st if key == "original" else r.con.execute("SELECT * FROM presenter_progress WHERE user_id=? AND lesson_id=? AND presenter=?", (r.user["id"], lid, key)).fetchone()
    old = (timeline["seen"] if timeline else "") or ""
    new = str(r.data.get("seen", ""))[:math.ceil(dur)]
    seen = "".join("1" if old[i:i+1] == "1" or new[i:i+1] == "1" else "0" for i in range(math.ceil(dur)))
    done = (timeline["completed"] if timeline else None) or (now() if seen.count("1") >= COMPLETE_RATIO * math.ceil(dur) else None)
    completed = (st["completed"] if st else None) or done
    if key == "original":
        r.con.execute("INSERT OR REPLACE INTO lesson_progress VALUES(?,?,?,?,?,?)", (r.user["id"], lid, pos, seen, completed, now()))
    else:
        r.con.execute("INSERT OR REPLACE INTO presenter_progress VALUES(?,?,?,?,?,?,?)", (r.user["id"], lid, key, pos, seen, done, now()))
        r.con.execute("""INSERT INTO lesson_progress VALUES(?,?,0,'',?,?) ON CONFLICT(user_id,lesson_id)
            DO UPDATE SET completed=COALESCE(lesson_progress.completed,excluded.completed), updated=excluded.updated""", (r.user["id"], lid, completed, now()))
    r.send(200, json.dumps({"completed": bool(completed)}), "application/json")


@route("POST", "/api/assistente", "user")
def assistant_api(r):
    l = r.con.execute("SELECT l.*, c.slug cslug FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=?",
                      (int(r.data.get("lesson", 0)),)).fetchone()
    q = str(r.data.get("q", "")).strip()[:1000]
    if not l or not q:
        raise HttpError(400, "Pergunta vazia.")
    r.course_for(l["cslug"])
    m = r.con.execute("SELECT * FROM modules WHERE id=?", (l["module_id"],)).fetchone()
    try:
        ans = ask_assistant(q, l, m, l["cslug"])
    except (OSError, ValueError, KeyError):
        _ollama["checked"] = 0
        raise HttpError(503, "O assistente não está disponível neste momento. Coloque a dúvida ao formador.")
    r.send(200, json.dumps({"resposta": ans}, ensure_ascii=False), "application/json; charset=utf-8")


# -- manual online ----------------------------------------------------------

def render_blocks(blocks, figbase):
    out = []
    for b in blocks:
        if "p" in b:
            out.append(f"<p>{md(b['p'])}</p>")
        elif "table" in b:
            rows = b["table"]
            head = "".join(f"<th>{md(x)}</th>" for x in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{md(x)}</td>" for x in row) + "</tr>" for row in rows[1:])
            out.append(f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
        elif "steps" in b:
            out.append("<ol class='steps'>" + "".join(f"<li>{md(s)}</li>" for s in b["steps"]) + "</ol>")
        elif "figure" in b:
            out.append(f'<figure><img src="{figbase}/{h(b["figure"])}" alt="{h(b.get("caption", ""))}" loading="lazy">'
                       f'<figcaption>{h(b.get("caption", ""))}</figcaption>'
                       + (f'<a class="asset-credit" href="{h(b["source"])}" target="_blank" rel="noopener noreferrer">Fonte da imagem ↗</a>' if b.get("source", "").startswith("https://") else "") + "</figure>")
        for k, label in (("tip", "Dica"), ("note", "Nota"), ("warn", "Atenção")):
            if k in b:
                out.append(f'<div class="box {k}"><b>{label}</b> {md(b[k])}</div>')
    return "".join(out)


@route("GET", r"/cursos/([a-z0-9-]+)/modulo/(\d+)/manual", "user")
def manual_page(r, slug, num):
    c = r.course_for(slug)
    m = r.con.execute("SELECT * FROM modules WHERE course_id=? AND num=? AND active=1", (c["id"], int(num))).fetchone()
    if not m or not m["manual_json"]:
        raise HttpError(404)
    data = json.loads((COURSES_DIR / slug / m["manual_json"]).read_text(encoding="utf-8"))
    figbase = f"/media/{slug}/{m['manual_figures'] or ''}".rstrip("/")
    parts = []
    for mod in data.get("modules", []):
        toc = "".join(f'<li><a href="#s{i}">{h(s["title"])}</a></li>' for i, s in enumerate(mod.get("sections", [])))
        parts.append(f'<h1>Módulo {mod["num"]} · {h(mod["title"])}</h1><p class="lead">{md(mod.get("intro", ""))}</p>')
        if mod.get("objectives"):
            parts.append('<div class="box obj"><b>Objetivos</b><ul>' +
                         "".join(f"<li>{md(o)}</li>" for o in mod["objectives"]) + "</ul></div>")
        parts.append(f'<nav class="toc"><b>Neste módulo</b><ol>{toc}</ol></nav>')
        for i, s in enumerate(mod.get("sections", [])):
            parts.append(f'<h2 id="s{i}">{h(s["title"])}</h2>{render_blocks(s.get("blocks", []), figbase)}')
        ex = mod.get("exercise")
        if ex:
            parts.append(f'<div class="box exercise"><h2>{h(ex["title"])}</h2><p class="muted">Duração: {ex.get("minutes", "")} min · '
                         f'Ficheiro: {h(ex.get("file", ""))}</p><ol>' + "".join(f"<li>{md(t)}</li>" for t in ex["tasks"]) + "</ol></div>")
        if mod.get("summary"):
            parts.append("<h2>Resumo</h2><ul>" + "".join(f"<li>{md(s)}</li>" for s in mod["summary"]) + "</ul>")
    if data.get("glossary"):
        parts.append("<h2>Glossário</h2><dl class='gloss'>" +
                     "".join(f"<dt>{h(t)}</dt><dd>{md(d)}</dd>" for t, d in data["glossary"]) + "</dl>")
    quiz = r.con.execute("SELECT 1 FROM quizzes WHERE module_id=? AND active=1", (m["id"],)).fetchone()
    foot = (f'<a class="btn" href="/cursos/{slug}/modulo/{num}/questionario">Fazer o questionário</a> ' if quiz else "")
    if m["manual_docx"]:
        foot += f'<a class="btn ghost" href="/media/{slug}/{h(m["manual_docx"])}?descarregar=1">Descarregar em Word</a>'
    return r.render(f"Manual · Módulo {num}", f"""<p class="crumbs"><a href="/">Os meus cursos</a> › <a href="/cursos/{slug}">{h(c['title'])}</a> › Manual</p>
<article class="card manual">{''.join(parts)}<div class="actions">{foot}</div></article>""")


# -- questionários ----------------------------------------------------------

def quiz_for(r, slug, num):
    c = r.course_for(slug)
    m = r.con.execute("SELECT * FROM modules WHERE course_id=? AND num=? AND active=1", (c["id"], int(num))).fetchone()
    q = m and r.con.execute("SELECT * FROM quizzes WHERE module_id=? AND active=1", (m["id"],)).fetchone()
    if not q:
        raise HttpError(404)
    qs = r.con.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY sort", (q["id"],)).fetchall()
    return c, m, q, qs


@route("GET", r"/cursos/([a-z0-9-]+)/modulo/(\d+)/questionario", "user")
def quiz_page(r, slug, num):
    c, m, q, qs = quiz_for(r, slug, num)
    hist = r.con.execute("SELECT pct, passed, created FROM quiz_attempts WHERE quiz_id=? AND user_id=? ORDER BY id DESC LIMIT 5",
                         (q["id"], r.user["id"])).fetchall()
    hist_html = ""
    if hist:
        hist_html = ("<p class='muted'>Tentativas anteriores: " + ", ".join(
            f'{a["pct"]}%{" ✓" if a["passed"] else ""} ({fmt_date(a["created"])})' for a in hist) + "</p>")
    items = []
    for i, qq in enumerate(qs):
        opts = list(enumerate(json.loads(qq["options"])))
        random.shuffle(opts)
        radios = "".join(f'<label class="opt"><input type="radio" name="q{qq["id"]}" value="{k}" required> {h(o)}</label>'
                         for k, o in opts)
        items.append(f'<fieldset class="q"><legend><span class="num">{i + 1}</span> {h(qq["text"])}</legend>{radios}</fieldset>')
    return r.render(q["title"], f"""<p class="crumbs"><a href="/">Os meus cursos</a> › <a href="/cursos/{slug}">{h(c['title'])}</a> › Módulo {num}</p>
<h1>{h(q['title'])}</h1><p>{len(qs)} perguntas · aprovação com {q['pass_mark']}% · pode repetir as vezes que quiser.</p>{hist_html}
<form method="post" class="card quiz">{csrf_field(r.csrf)}{''.join(items)}<button class="btn">Entregar respostas</button></form>""")


@route("POST", r"/cursos/([a-z0-9-]+)/modulo/(\d+)/questionario", "user")
def quiz_submit(r, slug, num):
    c, m, q, qs = quiz_for(r, slug, num)
    answers, score, rows = {}, 0, []
    for i, qq in enumerate(qs):
        opts = json.loads(qq["options"])
        val = r.data.get(f"q{qq['id']}")
        chosen = int(val) if val and val.isdigit() else None
        ok = chosen == qq["correct"]
        score += ok
        answers[qq["code"] or str(qq["id"])] = chosen
        your = h(opts[chosen]) if chosen is not None and chosen < len(opts) else "<i>sem resposta</i>"
        fix = "" if ok else f'<div>Resposta certa: <b>{h(opts[qq["correct"]])}</b></div>'
        fb = f'<div class="muted">{h(qq["feedback"])}</div>' if qq["feedback"] else ""
        rows.append(f'<li class="{"right" if ok else "wrong"}"><div><b>{i + 1}.</b> {h(qq["text"])}</div>'
                    f'<div>A sua resposta: {your} {"✓" if ok else "✗"}</div>{fix}{fb}</li>')
    pct = round(100 * score / len(qs)) if qs else 0
    passed = pct >= q["pass_mark"]
    r.con.execute("INSERT INTO quiz_attempts(user_id, quiz_id, score, total, pct, passed, answers, created) VALUES(?,?,?,?,?,?,?,?)",
                  (r.user["id"], q["id"], score, len(qs), pct, int(passed), json.dumps(answers), now()))
    p = course_progress(r.con, r.user["id"], c["id"])
    msg = ("Parabéns, ficou aprovado!" if passed else
           f"Ainda não chegou aos {q['pass_mark']}%. Reveja a aula e o manual e tente de novo.")
    nxt = (f'<a class="btn" href="/cursos/{slug}">{"Obter o certificado" if p["complete"] else "Voltar ao curso"}</a>' if passed
           else f'<a class="btn" href="/cursos/{slug}/modulo/{num}/questionario">Tentar de novo</a> '
                f'<a class="btn ghost" href="/cursos/{slug}/modulo/{num}/manual">Rever o manual</a>')
    return r.render("Resultado", f"""<p class="crumbs"><a href="/">Os meus cursos</a> › <a href="/cursos/{slug}">{h(c['title'])}</a></p>
<section class="card result {'pass' if passed else 'fail'}"><h1>{pct}%</h1><p><b>{score} de {len(qs)} certas.</b> {msg}</p>
<div class="actions">{nxt}</div></section><section class="card"><h2>Correção</h2><ol class="review">{''.join(rows)}</ol></section>""")


# -- certificados -----------------------------------------------------------

@route("POST", "/cursos/([a-z0-9-]+)/certificado", "user")
def cert_issue(r, slug):
    c = r.course_for(slug)
    row = r.con.execute("SELECT code FROM certificates WHERE user_id=? AND course_id=?", (r.user["id"], c["id"])).fetchone()
    if row:
        raise Redirect(f"/certificado/{row['code']}")
    if not course_progress(r.con, r.user["id"], c["id"])["complete"]:
        raise HttpError(403, "Ainda não concluiu todas as aulas e questionários deste curso.")
    code = "ATC-" + secrets.token_hex(4).upper()
    r.con.execute("INSERT INTO certificates VALUES(?,?,?,?)", (code, r.user["id"], c["id"], now()))
    raise Redirect(f"/certificado/{code}")


@route("GET", "/certificado/([A-Z0-9-]+)")
def cert_page(r, code):
    row = r.con.execute("""SELECT ce.*, u.name, co.title, co.hours_video, co.hours_class FROM certificates ce
                           JOIN users u ON u.id=ce.user_id JOIN courses co ON co.id=ce.course_id WHERE ce.code=?""", (code,)).fetchone()
    if not row:
        raise HttpError(404, "Certificado não encontrado.")
    d = datetime.strptime(row["issued"][:10], "%Y-%m-%d")
    months = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
              "outubro", "novembro", "dezembro"]
    date = f"{d.day} de {months[d.month - 1]} de {d.year}"
    hours = row["hours_class"] or row["hours_video"]
    verify = f"http://{r.headers.get('Host', 'localhost')}/verificar?codigo={code}"
    return f"""<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><title>Certificado {h(code)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/static/atc.css?v=3"></head>
<body class="certbody"><div class="noprint certbar"><a href="/">← Voltar</a> <button onclick="print()" class="btn small">Imprimir / guardar PDF</button></div>
<div class="cert"><div class="certin"><img src="/static/logo-600.png" alt="ATC"><p class="k">Certificado de conclusão</p>
<p>Certifica-se que</p><h1>{h(row['name'])}</h1><p>concluiu com aproveitamento o curso</p><h2>{h(row['title'])}</h2>
<p>{f"com a duração de {fmt_h(hours)} horas, " if hours else ""}na plataforma de formação online da ATC – Angbu Training Centre.</p>
<div class="certfoot"><div><span>{date}</span><small>Data de emissão</small></div><div><span>&nbsp;</span><small>A Direção da ATC</small></div>
<div><span>{h(code)}</span><small>Código · {h(verify)}</small></div></div></div></div></body></html>"""


@route("GET", "/verificar")
def verify_page(r):
    code = r.query.get("codigo", "").strip().upper()
    res = ""
    if code:
        row = r.con.execute("""SELECT ce.issued, u.name, co.title FROM certificates ce JOIN users u ON u.id=ce.user_id
                               JOIN courses co ON co.id=ce.course_id WHERE ce.code=?""", (code,)).fetchone()
        res = (f'<p class="ok-box">✓ Certificado válido: <b>{h(row["name"])}</b> concluiu <b>{h(row["title"])}</b> em '
               f'{fmt_date(row["issued"])[:10]}.</p>' if row else '<p class="error">Não existe nenhum certificado com este código.</p>')
    return page("Verificar certificado", f"""<section class="card login"><h1>Verificar certificado</h1>{res}
<form><label>Código do certificado<input name="codigo" value="{h(code)}" placeholder="ATC-XXXXXXXX" required></label>
<button class="btn">Verificar</button></form></section>""")


# ---------------------------------------------------------------------------
# Gestão (formadores e administradores)
# ---------------------------------------------------------------------------

def admin_tabs(active, admin):
    tabs = [("/admin", "Resumo"), ("/admin/utilizadores", "Utilizadores"), ("/admin/perguntas", "Perguntas dos formandos")]
    if admin:
        tabs.append(("/admin/cursos", "Cursos"))
    return '<nav class="tabs">' + "".join(f'<a href="{u}"{" class=on" if u == active else ""}>{t}</a>' for u, t in tabs) + "</nav>"


@route("GET", "/admin", "staff")
def admin_home(r):
    con = r.con
    n_users = con.execute("SELECT COUNT(*) FROM users WHERE role='formando' AND active=1").fetchone()[0]
    n_active = con.execute("SELECT COUNT(*) FROM users WHERE role='formando' AND last_seen >= datetime('now','-7 days','localtime')").fetchone()[0]
    n_certs = con.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]
    n_open = con.execute("""SELECT COUNT(*) FROM comments c JOIN users u ON u.id=c.user_id WHERE c.parent_id IS NULL
                            AND u.role='formando' AND NOT EXISTS (SELECT 1 FROM comments r JOIN users ru ON ru.id=r.user_id
                            WHERE r.parent_id=c.id AND ru.role!='formando')""").fetchone()[0]
    rows = []
    for c in con.execute("SELECT * FROM courses WHERE active=1 AND status='publicado' ORDER BY sort"):
        n = con.execute("SELECT COUNT(*) FROM enrolments e JOIN users u ON u.id=e.user_id WHERE course_id=? AND u.role='formando'",
                        (c["id"],)).fetchone()[0]
        nc = con.execute("SELECT COUNT(*) FROM certificates WHERE course_id=?", (c["id"],)).fetchone()[0]
        rows.append(f'<tr><td><a href="/cursos/{c["slug"]}">{h(c["title"])}</a></td><td>{n}</td><td>{nc}</td>'
                    f'<td><a href="/admin/relatorio/{c["slug"]}">Relatório</a></td></tr>')
    demo = ""
    if r.user["role"] == "admin" and setting(con, "demo") == "1":
        demo = (f'<section class="card warnbox"><b>Modo de demonstração ativo.</b> As contas de teste aparecem na página de entrada. '
                f'Antes de abrir aos formandos, altere as palavras-passe e desative este aviso.'
                f'<form method="post" action="/admin/demo-off">{csrf_field(r.csrf)}<button class="btn small">Desativar aviso</button></form></section>')
    ai = ("ligado (" + h(OLLAMA_MODEL) + ")") if ollama_available() else f"desligado (Ollama não encontrado em {h(OLLAMA_URL)} com o modelo {h(OLLAMA_MODEL)})"
    return r.render("Gestão", f"""<h1>Gestão da formação</h1>{admin_tabs('/admin', r.user['role'] == 'admin')}{demo}
<div class="stats"><div><b>{n_users}</b>formandos</div><div><b>{n_active}</b>ativos nos últimos 7 dias</div>
<div><b>{n_certs}</b>certificados emitidos</div><div><a href="/admin/perguntas"><b>{n_open}</b>perguntas por responder</a></div></div>
<section class="card"><h2>Cursos</h2><div class="tablewrap"><table><thead><tr><th>Curso</th><th>Formandos</th><th>Certificados</th><th></th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<p class="muted">Assistente de estudo (modelo local): {ai}.</p>""")


@route("POST", "/admin/demo-off", "admin")
def demo_off(r):
    set_setting(r.con, "demo", "0")
    raise Redirect("/admin")


@route("GET", "/admin/utilizadores", "staff")
def users_page(r, flash=""):
    q = r.query.get("q", "").strip()
    sql = "SELECT * FROM users"
    args = ()
    if q:
        sql += " WHERE name LIKE ? OR email LIKE ?"
        args = (f"%{q}%", f"%{q}%")
    users = r.con.execute(sql + " ORDER BY role, name", args).fetchall()
    courses = r.con.execute("SELECT * FROM courses WHERE active=1 AND status='publicado' ORDER BY sort").fetchall()
    enr = {}
    for e in r.con.execute("SELECT e.user_id, c.title FROM enrolments e JOIN courses c ON c.id=e.course_id"):
        enr.setdefault(e["user_id"], []).append(e["title"])
    rows = "".join(f'<tr{" class=inactive" if not u["active"] else ""}><td><a href="/admin/utilizadores/{u["id"]}">{h(u["name"])}</a></td>'
                   f'<td>{h(u["email"])}</td><td>{ROLES[u["role"]]}</td><td>{h(", ".join(enr.get(u["id"], [])))}</td>'
                   f'<td>{fmt_date(u["last_seen"])}</td></tr>' for u in users)
    copts = "".join(f'<option value="{c["slug"]}">{h(c["title"])}</option>' for c in courses)
    role_opts = "".join(f'<option value="{k}">{v}</option>' for k, v in ROLES.items()
                        if r.user["role"] == "admin" or k == "formando")
    return r.render("Utilizadores", f"""<h1>Utilizadores</h1>{admin_tabs('/admin/utilizadores', r.user['role'] == 'admin')}
<form class="search"><input name="q" value="{h(q)}" placeholder="Procurar por nome ou email"><button class="btn small">Procurar</button></form>
<section class="card"><div class="tablewrap"><table><thead><tr><th>Nome</th><th>Email</th><th>Papel</th><th>Cursos</th><th>Último acesso</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>
<div class="grid2"><section class="card"><h2>Novo utilizador</h2><form method="post" action="/admin/utilizadores">{csrf_field(r.csrf)}
<label>Nome completo<input name="name" required></label><label>Email<input type="email" name="email" required></label>
<label>Palavra-passe inicial<input name="pw" minlength="6" required></label>
<label>Papel<select name="role">{role_opts}</select></label>
<label>Inscrever no curso<select name="course"><option value="">(nenhum)</option>{copts}</select></label>
<button class="btn">Criar</button></form></section>
<section class="card"><h2>Criar vários de uma vez</h2><p class="muted">Uma linha por formando: <code>nome;email;palavra-passe;curso</code>.
O curso é o código (por exemplo <code>informatica</code>) e é opcional. Pode colar diretamente do Excel.</p>
<form method="post" action="/admin/utilizadores/lote">{csrf_field(r.csrf)}<textarea name="lines" rows="7" placeholder="Maria Silva;maria@exemplo.ao;atc2026;informatica"></textarea>
<button class="btn">Importar</button></form></section></div>""", flash=flash)


def enrol(con, uid, slug):
    c = con.execute("SELECT id FROM courses WHERE slug=? AND active=1", (slug.strip(),)).fetchone()
    if not c:
        raise ValueError(f"Curso desconhecido: {slug}")
    con.execute("INSERT OR IGNORE INTO enrolments VALUES(?,?,?)", (uid, c["id"], now()))


@route("POST", "/admin/utilizadores", "staff")
def user_create(r):
    d = r.data
    role = d.get("role", "formando") if r.user["role"] == "admin" else "formando"
    try:
        uid = create_user(r.con, d.get("email", ""), d.get("name", ""), role, d.get("pw", ""))
        if d.get("course"):
            enrol(r.con, uid, d["course"])
    except sqlite3.IntegrityError:
        return users_page(r, "Já existe um utilizador com esse email.")
    except ValueError as e:
        return users_page(r, h(e))
    raise Redirect(f"/admin/utilizadores/{uid}")


@route("POST", "/admin/utilizadores/lote", "staff")
def user_bulk(r):
    ok, errors = 0, []
    for n, line in enumerate(r.data.get("lines", "").splitlines(), 1):
        if not line.strip():
            continue
        cols = [x.strip() for x in re.split(r"[;\t]", line)]
        if len(cols) < 3:
            errors.append(f"Linha {n}: faltam colunas")
            continue
        try:
            existing = r.con.execute("SELECT id FROM users WHERE email=?", (cols[1].lower(),)).fetchone()
            uid = existing["id"] if existing else create_user(r.con, cols[1], cols[0], "formando", cols[2])
            if len(cols) > 3 and cols[3]:
                enrol(r.con, uid, cols[3])
            ok += 1
        except ValueError as e:
            errors.append(f"Linha {n}: {e}")
    msg = f"{ok} formando(s) importado(s)."
    if errors:
        msg += "<br>" + "<br>".join(h(e) for e in errors)
    return users_page(r, msg)


@route("GET", r"/admin/utilizadores/(\d+)", "staff")
def user_page(r, uid, flash=""):
    u = r.con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        raise HttpError(404)
    can_edit = r.user["role"] == "admin" or u["role"] == "formando"
    courses = r.con.execute("SELECT * FROM courses WHERE active=1 AND status='publicado' ORDER BY sort").fetchall()
    enrolled = {e["course_id"] for e in r.con.execute("SELECT course_id FROM enrolments WHERE user_id=?", (uid,))}
    rows = []
    for c in courses:
        if c["id"] in enrolled:
            p = course_progress(r.con, int(uid), c["id"])
            action = (f'<form method="post" action="/admin/utilizadores/{uid}/inscricao">{csrf_field(r.csrf)}'
                      f'<input type="hidden" name="course" value="{c["slug"]}"><input type="hidden" name="op" value="remover">'
                      f'<button class="linkbtn">Anular inscrição</button></form>')
            rows.append(f'<tr><td>{h(c["title"])}</td><td>{bar(p["pct"])} {p["pct"]}%</td><td>{action}</td></tr>')
        else:
            action = (f'<form method="post" action="/admin/utilizadores/{uid}/inscricao">{csrf_field(r.csrf)}'
                      f'<input type="hidden" name="course" value="{c["slug"]}"><input type="hidden" name="op" value="inscrever">'
                      f'<button class="btn small">Inscrever</button></form>')
            rows.append(f'<tr><td>{h(c["title"])}</td><td class="muted">não inscrito</td><td>{action}</td></tr>')
    edit = ""
    if can_edit:
        role_sel = ""
        if r.user["role"] == "admin":
            role_sel = ('<label>Papel<select name="role">' + "".join(
                f'<option value="{k}"{" selected" if k == u["role"] else ""}>{v}</option>' for k, v in ROLES.items()) + "</select></label>")
        edit = f"""<section class="card"><h2>Editar</h2><form method="post">{csrf_field(r.csrf)}
<label>Nome<input name="name" value="{h(u['name'])}" required></label>{role_sel}
<label>Nova palavra-passe (deixe vazio para manter)<input name="pw" minlength="6"></label>
<label class="check"><input type="checkbox" name="active" value="1"{' checked' if u['active'] else ''}> Conta ativa</label>
<button class="btn">Guardar</button></form></section>"""
    return r.render(u["name"], f"""<p class="crumbs"><a href="/admin/utilizadores">Utilizadores</a></p>
<h1>{h(u['name'])}</h1><p>{h(u['email'])} · {ROLES[u['role']]} · criado em {fmt_date(u['created'])[:10]}</p>
<div class="grid2"><section class="card"><h2>Cursos</h2><div class="tablewrap"><table><tbody>{''.join(rows)}</tbody></table></div></section>{edit}</div>""",
                    flash=flash)


@route("POST", r"/admin/utilizadores/(\d+)", "staff")
def user_update(r, uid):
    u = r.con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u or (r.user["role"] != "admin" and u["role"] != "formando"):
        raise HttpError(403)
    role = r.data.get("role", u["role"]) if r.user["role"] == "admin" else u["role"]
    if role not in ROLES:
        raise HttpError(400)
    active = 1 if r.data.get("active") else 0
    if int(uid) == r.user["id"] and (not active or role != r.user["role"]):
        return user_page(r, uid, "Não pode desativar nem mudar o papel da sua própria conta.")
    r.con.execute("UPDATE users SET name=?, role=?, active=? WHERE id=?", (r.data.get("name", u["name"]).strip(), role, active, uid))
    pw = r.data.get("pw", "")
    if pw:
        if len(pw) < 6:
            return user_page(r, uid, "A palavra-passe tem de ter pelo menos 6 caracteres.")
        r.con.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(pw), uid))
        r.con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    if not active:
        r.con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    return user_page(r, uid, "Alterações guardadas.")


@route("POST", r"/admin/utilizadores/(\d+)/inscricao", "staff")
def user_enrol(r, uid):
    c = r.con.execute("SELECT id FROM courses WHERE slug=?", (r.data.get("course", ""),)).fetchone()
    if not c:
        raise HttpError(404)
    if r.data.get("op") == "remover":
        r.con.execute("DELETE FROM enrolments WHERE user_id=? AND course_id=?", (uid, c["id"]))
    else:
        r.con.execute("INSERT OR IGNORE INTO enrolments VALUES(?,?,?)", (uid, c["id"], now()))
    raise Redirect(f"/admin/utilizadores/{uid}")


def report_rows(con, c):
    quizzes = con.execute("""SELECT q.id, q.pass_mark, m.num FROM quizzes q JOIN modules m ON m.id=q.module_id
                             WHERE m.course_id=? AND m.active=1 AND q.active=1 ORDER BY m.num""", (c["id"],)).fetchall()
    learners = con.execute("""SELECT u.* FROM enrolments e JOIN users u ON u.id=e.user_id
                              WHERE e.course_id=? AND u.role='formando' ORDER BY u.name""", (c["id"],)).fetchall()
    out = []
    for u in learners:
        p = course_progress(con, u["id"], c["id"])
        scores = []
        for q in quizzes:
            b = con.execute("SELECT MAX(pct) FROM quiz_attempts WHERE quiz_id=? AND user_id=?", (q["id"], u["id"])).fetchone()[0]
            scores.append(b)
        cert = con.execute("SELECT code FROM certificates WHERE user_id=? AND course_id=?", (u["id"], c["id"])).fetchone()
        out.append((u, p, scores, cert["code"] if cert else ""))
    return quizzes, out


@route("GET", "/admin/relatorio/([a-z0-9-]+)", "staff")
def report_page(r, slug):
    c = r.course_for(slug)
    quizzes, rows = report_rows(r.con, c)
    qh = "".join(f"<th>Quest. M{q['num']}</th>" for q in quizzes)
    body = "".join(
        f'<tr><td><a href="/admin/utilizadores/{u["id"]}">{h(u["name"])}</a><br><span class="muted">{h(u["email"])}</span></td>'
        f'<td>{bar(p["pct"])} {p["pct"]}%</td><td>{p["lessons_done"]}/{p["lessons"]}</td>' +
        "".join(f'<td>{"—" if s is None else f"{s}%"}</td>' for s in scores) +
        f'<td>{f"<a href=/certificado/{cert}>{cert}</a>" if cert else "—"}</td><td>{fmt_date(u["last_seen"])}</td></tr>'
        for u, p, scores, cert in rows) or f'<tr><td colspan="{5 + len(quizzes)}" class="muted">Ainda não há formandos inscritos.</td></tr>'
    return r.render(f"Relatório · {c['title']}", f"""<p class="crumbs"><a href="/admin">Gestão</a></p>
<h1>Relatório de turma</h1><p class="lead">{h(c['title'])}</p>
<p><a class="btn ghost small" href="/admin/relatorio/{slug}.csv">Exportar para Excel (CSV)</a></p>
<section class="card"><div class="tablewrap"><table><thead><tr><th>Formando</th><th>Progresso</th><th>Aulas</th>{qh}<th>Certificado</th><th>Último acesso</th></tr></thead>
<tbody>{body}</tbody></table></div></section>""")


@route("GET", r"/admin/relatorio/([a-z0-9-]+)\.csv", "staff")
def report_csv(r, slug):
    c = r.course_for(slug)
    quizzes, rows = report_rows(r.con, c)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Nome", "Email", "Progresso %", "Aulas vistas", "Aulas"] + [f"Questionário M{q['num']} %" for q in quizzes] +
               ["Certificado", "Último acesso"])
    for u, p, scores, cert in rows:
        w.writerow([u["name"], u["email"], p["pct"], p["lessons_done"], p["lessons"]] +
                   ["" if s is None else s for s in scores] + [cert, u["last_seen"] or ""])
    r.send(200, "﻿" + buf.getvalue(), "text/csv; charset=utf-8",
           {"Content-Disposition": f'attachment; filename="relatorio-{slug}.csv"'})


@route("GET", "/admin/perguntas", "staff")
def questions_page(r):
    rows = r.con.execute("""SELECT cm.*, u.name, l.title lt, l.slug ls, co.slug cs,
                            EXISTS (SELECT 1 FROM comments x JOIN users xu ON xu.id=x.user_id WHERE x.parent_id=cm.id
                                    AND xu.role!='formando') answered
                            FROM comments cm JOIN users u ON u.id=cm.user_id JOIN lessons l ON l.id=cm.lesson_id
                            JOIN courses co ON co.id=l.course_id WHERE cm.parent_id IS NULL AND u.role='formando'
                            ORDER BY answered, cm.created DESC LIMIT 200""").fetchall()
    items = "".join(f'<li class="{"done" if q["answered"] else "open"}"><div class="meta"><b>{h(q["name"])}</b> em '
                    f'<a href="/cursos/{q["cs"]}/aula/{q["ls"]}">{h(q["lt"])}</a> · {fmt_date(q["created"])} · '
                    f'{"respondida" if q["answered"] else "<b>por responder</b>"}</div><div>{h(q["body"])}</div></li>'
                    for q in rows) or '<li class="muted">Ainda não há perguntas.</li>'
    return r.render("Perguntas", f"""<h1>Perguntas dos formandos</h1>{admin_tabs('/admin/perguntas', r.user['role'] == 'admin')}
<section class="card"><ul class="comments">{items}</ul></section>""")


@route("GET", "/admin/cursos", "admin")
def courses_admin(r, report=None):
    packs = sorted(p.name for p in COURSES_DIR.iterdir() if (p / "curso.json").exists())
    rows = []
    for c in r.con.execute("SELECT * FROM courses ORDER BY sort"):
        n_l = r.con.execute("SELECT COUNT(*) FROM lessons WHERE course_id=? AND active=1", (c["id"],)).fetchone()[0]
        rows.append(f'<tr><td>{h(c["title"])}</td><td><code>{h(c["slug"])}</code></td><td>{STATUS.get(c["status"], c["status"])}</td>'
                    f'<td>{n_l}</td><td>{"sim" if c["slug"] in packs else "<b>pasta em falta</b>"}</td></tr>')
    rep = ("<section class='card'><h2>Resultado da importação</h2><ul>" + "".join(f"<li>{h(x)}</li>" for x in report) +
           "</ul></section>") if report else ""
    return r.render("Cursos", f"""<h1>Cursos</h1>{admin_tabs('/admin/cursos', True)}{rep}
<section class="card"><div class="tablewrap"><table><thead><tr><th>Curso</th><th>Código</th><th>Estado</th><th>Aulas</th><th>Pasta</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<section class="card"><h2>Atualizar cursos</h2><p>Os cursos vivem na pasta <code>{h(COURSES_DIR)}</code>, uma subpasta por curso com um
ficheiro <code>curso.json</code>. Depois de acrescentar aulas, vídeos ou questionários, carregue em <b>Importar</b>.
O progresso dos formandos mantém-se.</p><form method="post" action="/admin/cursos">{csrf_field(r.csrf)}
<button class="btn">Importar / atualizar todos os cursos</button></form></section>""")


@route("POST", "/admin/cursos", "admin")
def courses_import(r):
    return courses_admin(r, import_all(r.con))


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser(description="ATC LMS")
    ap.add_argument("comando", nargs="?", default="servir", choices=["servir", "importar", "utilizador"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--porta", type=int, default=int(os.environ.get("ATC_PORTA", 8080)))
    ap.add_argument("--host", default=os.environ.get("ATC_HOST", "0.0.0.0"))
    a = ap.parse_args()
    init_db()
    if a.comando == "importar":
        with db() as con:
            print("\n".join(import_all(con)))
        return
    if a.comando == "utilizador":
        if len(a.args) != 4:
            sys.exit("Uso: python atc_lms.py utilizador EMAIL \"NOME\" admin|formador|formando PALAVRA-PASSE")
        with db() as con:
            create_user(con, a.args[0], a.args[1], a.args[2], a.args[3])
        print("Utilizador criado.")
        return
    seed_demo()
    srv = ThreadingHTTPServer((a.host, a.porta), Handler)
    srv.daemon_threads = True
    print(f"ATC LMS a funcionar em http://localhost:{a.porta}")
    ip = lan_ip()
    if ip and a.host == "0.0.0.0":
        print(f"Na rede local (sala de formação): http://{ip}:{a.porta}")
    print(f"Assistente de estudo: {'ligado (' + OLLAMA_MODEL + ')' if ollama_available() else 'desligado (Ollama não encontrado)'}")
    print("Para parar: Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor parado.")


if __name__ == "__main__":
    main()
