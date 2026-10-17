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
import email
import email.policy
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
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
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
# Guia por voz (ElevenLabs). A chave vem do ambiente e nunca fica no código.
ELEVEN_URL = os.environ.get("ATC_ELEVEN_URL", "https://api.elevenlabs.io/v1").rstrip("/")
ELEVEN_KEY = os.environ.get("ATC_ELEVEN_KEY", "")
VOZ_LIMITE_DIA = int(os.environ.get("ATC_VOZ_LIMITE", "40"))  # perguntas por formando e por dia
COOKIE = "atc_sessao"
SESSION_DAYS = 14
COMPLETE_RATIO = 0.9  # fração do vídeo que conta como "aula vista"

ROLES = {"admin": "Administrador", "formador": "Formador", "formando": "Formando"}
PRESENTERS = {"helena": {"name": "Helena", "label": "Avatar feminino"}, "miguel": {"name": "Miguel", "label": "Avatar masculino"}}
PROFILE_COLORS = {"sand": "Areia", "navy": "Azul", "green": "Verde", "rose": "Rosa"}

STATUS = {"publicado": "Disponível", "amostra": "Amostra", "em_breve": "Em breve"}

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
CREATE TABLE IF NOT EXISTS learner_presenter (
  user_id INTEGER PRIMARY KEY REFERENCES users(id),
  presenter TEXT NOT NULL CHECK(presenter IN ('helena','miguel')), updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS onboarding (
  user_id INTEGER NOT NULL REFERENCES users(id), step TEXT NOT NULL, done TEXT NOT NULL,
  PRIMARY KEY(user_id, step));
CREATE TABLE IF NOT EXISTS voice_answers (
  lesson_id INTEGER NOT NULL, qkey TEXT NOT NULL, answer TEXT NOT NULL, source TEXT NOT NULL,
  hits INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, PRIMARY KEY(lesson_id, qkey));
CREATE TABLE IF NOT EXISTS voice_log (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, lesson_id INTEGER NOT NULL, presenter TEXT NOT NULL,
  question TEXT NOT NULL, source TEXT NOT NULL, stt_bytes INTEGER NOT NULL DEFAULT 0, tts_chars INTEGER NOT NULL DEFAULT 0,
  created TEXT NOT NULL);
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
        pag_init(con)


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


def ts_seconds(ts):
    parts = [float(x) for x in ts.replace(",", ".").split(":")]
    return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0]


def fmt_ts(sec):
    s = max(0, int(round(sec)))
    return f"{s // 60}:{s % 60:02d}"



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
# Guia por voz: o formando pergunta em voz alta e o guia escolhido responde.
# Custo controlado: respostas guardadas por aula e pergunta, áudio gerado uma vez e reutilizado.
# Ordem: cache → perguntas frequentes da aula → modelo local (se existir) → "pergunte ao formador".
# ---------------------------------------------------------------------------

VOZES = {"helena": "JGnWZj684pcXmK2SxYIv", "miguel": "FbFkkfp4Iv6U5Q1WC4C2"}
VOZ_ISOLAR = {"helena"}  # a voz da Helena tem eco: passa uma vez pelo isolador de voz
VOZ_AJUSTES = {"stability": 0.5, "similarity_boost": 0.8, "style": 0.15, "speed": 1.0}
VOZ_PARAGEM = set("""a o as os um uma uns umas de do da dos das no na nos nas ao aos em por para com sem que se e é
eu me mim meu minha tu te você voce ele ela isto isso este esta esse essa como qual quais quando onde porque
porquê pode posso podes faz fazer faço fica ficam é são ser está estão tem têm há mais ou também já algum alguma
the""".split())
_VOZ_SINONIMOS = {"desli": "encer", "entro": "inici", "entra": "inici", "aplic": "progr", "pesqu": "procu",
                  "encon": "procu", "mudo": "alter", "mudar": "alter", "agora": "segui"}


def voz_tokens(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    out = set()
    for w in re.findall(r"[a-z0-9]+", t):
        if w in VOZ_PARAGEM or len(w) < 2:
            continue
        w = w[:5]
        out.add(_VOZ_SINONIMOS.get(w, w))
    return out


def voz_dados(slug, lslug):
    path = COURSES_DIR / slug / "voz" / f"{lslug}.json"
    return read_json(path) if path.is_file() else None


def voz_procurar(pergunta, dados, minimo=0.5):
    """Pergunta frequente mais parecida (coeficiente de Dice sobre radicais), ou None."""
    q = voz_tokens(pergunta)
    melhor, pontos = None, 0.0
    if not q:
        return None
    for entrada in dados.get("perguntas", []):
        for ex in entrada["exemplos"]:
            e = voz_tokens(ex)
            comum = len(q & e)
            if e and comum / len(q) >= 0.6:   # a maior parte da pergunta tem de estar coberta ("copiar ficheiro" ≠ "o que é um ficheiro")
                d = 2 * comum / (len(q) + len(e))
                if d > pontos:
                    melhor, pontos = entrada, d
    return melhor if pontos >= minimo else None


def voz_responder(con, lesson, mod, slug, dados, pergunta):
    """Devolve (resposta, fonte). Guarda as respostas novas para não voltar a pagar por elas."""
    toks = voz_tokens(pergunta)
    if not toks:
        return dados["linhas"]["nao_ouvi"], "linha"
    chave = " ".join(sorted(toks))
    row = con.execute("SELECT answer FROM voice_answers WHERE lesson_id=? AND qkey=?", (lesson["id"], chave)).fetchone()
    if row:
        con.execute("UPDATE voice_answers SET hits=hits+1 WHERE lesson_id=? AND qkey=?", (lesson["id"], chave))
        return row["answer"], "cache"
    faq = voz_procurar(pergunta, dados)
    if faq:
        resposta, fonte = faq["resposta"], "faq"
    elif ollama_available():
        try:
            resposta, fonte = ask_assistant(pergunta, lesson, mod, slug), "modelo"
        except (OSError, ValueError, KeyError):
            return dados["linhas"]["nao_sei"], "sem_resposta"
    else:
        return dados["linhas"]["nao_sei"], "sem_resposta"
    con.execute("INSERT OR IGNORE INTO voice_answers VALUES(?,?,?,?,0,?)", (lesson["id"], chave, resposta, fonte, now()))
    return resposta, fonte


def _eleven(caminho, corpo, tipo, timeout=60):
    headers = {"Content-Type": tipo}
    if ELEVEN_KEY:
        headers["xi-api-key"] = ELEVEN_KEY
    req = urllib.request.Request(ELEVEN_URL + caminho, data=corpo, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _multipart(campos, ficheiro):
    fronteira = "atc" + secrets.token_hex(12)
    partes = [f'--{fronteira}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in campos.items()]
    nome, dados, tipo = ficheiro
    partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"; filename="{nome}"\r\n'
                  f'Content-Type: {tipo}\r\n\r\n'.encode() + dados + b"\r\n")
    partes.append(f"--{fronteira}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


def voz_transcrever(audio, tipo):
    """Fala → texto (ElevenLabs Scribe, português)."""
    corpo, ct = _multipart({"model_id": "scribe_v1", "language_code": "por", "tag_audio_events": "false"},
                           ("file", audio, tipo.split(";")[0]))
    return json.loads(_eleven("/speech-to-text", corpo, ct, timeout=60)).get("text", "").strip()


def voz_chave_audio(presenter, texto):
    return hashlib.sha1(f"{VOZES[presenter]}|{texto}".encode()).hexdigest()[:20]


def voz_ficheiro(slug, presenter, chave):
    """Áudio já gerado: primeiro o que vem com o curso, depois a cache local."""
    for base in (COURSES_DIR / slug / "voz" / "audio", DATA_DIR / "voz" / slug):
        f = base / presenter / f"{chave}.mp3"
        if f.is_file():
            return f
    return None


def voz_falar(slug, presenter, texto, destino=None):
    """Texto → fala na voz do guia. Devolve (chave, caracteres pagos). Só gera o que ainda não existe."""
    chave = voz_chave_audio(presenter, texto)
    if voz_ficheiro(slug, presenter, chave):
        return chave, 0
    pedido = json.dumps({"text": texto, "model_id": "eleven_multilingual_v2", "language_code": "pt",
                         "voice_settings": VOZ_AJUSTES}).encode()
    audio = _eleven(f"/text-to-speech/{VOZES[presenter]}?output_format=mp3_44100_128", pedido, "application/json", timeout=90)
    if presenter in VOZ_ISOLAR:
        corpo, ct = _multipart({}, ("audio", audio, "audio/mpeg"))
        try:
            audio = _eleven("/audio-isolation", corpo, ct, timeout=120)
        except urllib.error.HTTPError as e:
            if e.code != 400:   # 400: frase demasiado curta para o isolador (mínimo 4,6 s); fica a voz original
                raise
    pasta = (destino or DATA_DIR / "voz" / slug) / presenter
    pasta.mkdir(parents=True, exist_ok=True)
    tmp = pasta / f"{chave}.tmp"
    tmp.write_bytes(audio)
    tmp.replace(pasta / f"{chave}.mp3")
    return chave, len(texto)


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


def ring_svg(pct, size=68, dark=False):
    pct = max(0, min(100, int(round(pct or 0))))
    r = 26
    circ = 2 * 3.14159265 * r
    off = circ * (1 - pct / 100.0)
    cls = "ring ring-dark" if dark else "ring"
    return (f'<div class="{cls}" style="width:{size}px;height:{size}px" aria-hidden="true">'
            f'<svg viewBox="0 0 64 64"><circle class="ring-bg" cx="32" cy="32" r="{r}"/>'
            f'<circle class="ring-fg" cx="32" cy="32" r="{r}" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{off:.1f}"/></svg>'
            f'<b>{pct}%</b></div>')


def page(title, body, user=None, csrf="", wide=False, flash="", profile=None, presenter=None, here="/", foco=False, cta=False, scripts="", body_class=""):
    if user:
        user = dict(user)
        user["name"] = (profile or {}).get("display_name") or user["name"]
    profile_color = (profile or {}).get("color", "sand")
    brand = '<a class="brand" href="/"><img src="/static/logo-200.png" alt=""><span><b>ATC</b> Formação<small>Angbu Training Centre</small></span></a>'
    sidebar = ""
    if user and not foco:
        links = [("/", "◫", "Os meus cursos"), ("/#catalogo", "▦", "Catálogo")]
        if user["role"] in ("admin", "formador"):
            links.append(("/admin", "▤", "Gestão"))
        if user["role"] == "formando":
            links.append(("/planos", "◈", "Planos e pagamentos"))
        links.append(("/conta", "◎", "A minha conta"))
        sidebar = ('<aside class="sidebar">' + brand + '<p class="nav-label">ESPAÇO DE FORMAÇÃO</p><nav aria-label="Navegação principal">' +
                   "".join(f'<a href="{u}"><span aria-hidden="true">{icon}</span>{t}</a>' for u, icon, t in links) +
                   '</nav><div class="sidebar-note"><span class="eyebrow">O SEU PRÓXIMO PASSO</span><h3>Aprender hoje.<br>Ir mais longe amanhã.</h3><p>Competências que fazem a diferença.</p></div>' +
                   f'<div class="profile"><span class="avatar avatar-{h(profile_color)}">{h(user["name"][:1].upper())}</span><div><b>{h(user["name"])}</b><small>{ROLES[user["role"]]}</small></div></div>' +
                   f'<form class="logout" method="post" action="/sair">{csrf_field(csrf)}<button class="linkbtn">Sair da conta →</button></form></aside>')
    chip = ""
    if user and presenter in PRESENTERS and not foco:
        chip = (f'<a class="guide-chip" href="/apresentador?seguinte={urllib.parse.quote(safe_next(here), safe="/")}" title="Mudar de guia"><img src="/static/presenters/{presenter}.png" alt="">'
                f'<span><small>O seu guia</small><b>{PRESENTERS[presenter]["name"]}</b></span></a>')
    flash_html = f'<div class="flash" role="status">{flash}</div>' if flash else ""
    header = (brand + f'<a class="account-link" href="/conta">{h(user["name"].split()[0])} <span class="avatar avatar-{h(profile_color)}">{h(user["name"][:1].upper())}</span></a>' if user and foco else
              f'<div class="workspace-label">Área de aprendizagem <span>/</span> <b>{h(title)}</b></div>{chip}<a class="account-link" href="/conta">{h(user["name"].split()[0])} <span class="avatar avatar-{h(profile_color)}">{h(user["name"][:1].upper())}</span></a>' if user else brand + ('<a class="top-cta" href="/entrar">Entrar <span aria-hidden="true">→</span></a>' if cta else ''))
    return f"""<!doctype html><html lang="pt-PT"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(title)} · ATC Formação</title><link rel="icon" href="/static/logo-200.png"><link rel="preload" href="/static/fonts/Geist.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/static/atc.css?v=17"><meta name="csrf" content="{h(csrf)}"><script src="/static/ui.js?v=6" defer></script></head>
<body class="{('app foco' if foco else 'app') if user else 'public'}{' ' + body_class if body_class else ''}"{f' data-u="{user["id"]}"' if user else ''}><a class="skip-link" href="#conteudo">Saltar para o conteúdo</a>{sidebar}<div class="workspace"><header class="top"><div class="wrap">{header}</div></header>
<main id="conteudo" class="wrap{' wide' if wide else ''}">{flash_html}{body}</main>
<footer><div class="wrap"><span>ATC · Angbu Training Centre</span><span>Cabinda, Angola · Aprendizagem com propósito</span></div></footer></div>{scripts}</body></html>"""


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
        if (self.headers.get("Content-Type") or "").startswith("audio/"):
            return {"_audio": raw, "_audio_type": self.headers.get("Content-Type")}
        if (self.headers.get("Content-Type") or "").startswith("application/json"):
            return json.loads(raw or b"{}")
        if (self.headers.get("Content-Type") or "").startswith("multipart/form-data"):  # envio de ficheiros (comprovativos)
            msg = email.message_from_bytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + raw,
                                           policy=email.policy.HTTP)
            out = {}
            for part in msg.iter_parts():
                name, payload = part.get_param("name", header="content-disposition"), part.get_payload(decode=True) or b""
                out[name] = ({"filename": part.get_filename(), "type": part.get_content_type(), "data": payload}
                             if part.get_filename() is not None else payload.decode("utf-8", "replace"))
            return out
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
                    if fn.__name__ not in ("login_post", "register_post", "pay_webhook") and (not user or not hmac.compare_digest(str(sent or ""), csrf)):
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
        return page(title, body, self.user, self.csrf, profile=learner_profile(self),
                    presenter=selected_presenter(self) if self.user else None,
                    here=urllib.parse.urlsplit(self.path).path, **kw)

    def is_staff(self):
        return self.user and self.user["role"] in ("admin", "formador")

    def course_for(self, slug, need_access=True):
        c = self.con.execute("SELECT * FROM courses WHERE slug=? AND active=1", (slug,)).fetchone()
        if not c:
            raise HttpError(404)
        if need_access and not self.can_access(c):
            raise HttpError(403, "Não tem acesso ativo a este curso. Escolha um plano ou ative um código em «Planos e pagamentos».")
        return c

    def can_access(self, c):
        if self.is_staff():
            return True
        if c["status"] == "amostra":
            return True  # cursos de amostra: módulo de demonstração aberto a qualquer conta
        return c["status"] == "publicado" and self.con.execute(
            "SELECT 1 FROM enrolments WHERE user_id=? AND course_id=?", (self.user["id"], c["id"])).fetchone() is not None \
            and not acesso_expirado(self.con, self.user["id"])


# ---------------------------------------------------------------------------
# Páginas: entrada e conta
# ---------------------------------------------------------------------------

@route("GET", "/entrar")
def login_get(r, error=""):
    err = f'<p class="entry-error" role="alert">{h(error)}</p>' if error else ""
    nxt = h(r.query.get("seguinte", "/"))
    return public_page("Entrar", f"""{public_nav(("/", "Início"))}
<main class="entry">
  <section class="entry-show" aria-label="Uma aula da ATC">
    <span class="label">Angbu Training Centre — Cabinda, Angola</span>
    <h2 class="serif">O seu futuro começa com <em>conhecimento.</em></h2>
    <figure class="lesson"><div class="lesson-frame"><img src="/static/inicio/aula.jpg" alt=""><video src="/static/inicio/aula.mp4" poster="/static/inicio/aula.jpg" autoplay muted loop playsinline aria-hidden="true"></video></div>
      <figcaption><span><span class="lesson-live label">Aula 1.1 · em vídeo</span><b>O ambiente de trabalho</b></span><span class="lesson-guide"><img src="/static/presenters/helena.png" alt=""><img src="/static/presenters/miguel.png" alt=""><span class="label">Com a Helena ou o Miguel</span></span></figcaption></figure>
  </section>
  <section class="entry-form entry-pc" aria-label="Iniciar sessão no computador">
    <div class="pc-monitor">
      <div class="pc-bezel-top" aria-hidden="true"><span class="pc-cam"></span><span class="pc-mic"></span></div>
      <div class="pc-screen">
        <div class="pc-topbar" aria-hidden="true">
          <span class="pc-os-brand">❖ ATC OS · Estação de Formação</span>
          <span class="pc-os-status">
            <span class="pc-kbd">PT</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/></svg>
            <svg width="15" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="18" height="10" rx="2"/><line x1="22" y1="11" x2="22" y2="13"/><rect x="4" y="9" width="12" height="6" fill="currentColor"/></svg>
            <span id="pc-clock">09:41</span>
          </span>
        </div>
        <div class="pc-login">
          <div class="pc-user-badge" aria-hidden="true">
            <div class="pc-avatar">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="8" r="4"/><path d="M4 20c1.8-3.8 5-6 8-6s6.2 2.2 8 6"/></svg>
              <span class="pc-online" title="Pronto a iniciar"></span>
            </div>
            <span class="pc-session-pill">● Iniciar sessão no computador</span>
          </div>
          <span class="label">A sua área de formação</span>
          <h1 class="serif">Bem-vindo <em>de volta.</em></h1>
          <p class="lead">Introduza as suas credenciais para desbloquear o seu ambiente de trabalho.</p>
          {err}<form method="post" action="/entrar"><input type="hidden" name="seguinte" value="{nxt}">
            <label class="field"><span class="label">Utilizador (email ou telemóvel)</span><input name="email" required autofocus autocomplete="username" placeholder="nome@exemplo.com ou 9XX XXX XXX"></label>
            <label class="field"><span class="label">Palavra-passe da conta</span><span class="pw"><input type="password" name="pw" required autocomplete="current-password" placeholder="••••••••"><button type="button" data-pw-toggle aria-label="Mostrar palavra-passe" aria-pressed="false">Mostrar</button></span></label>
            <button class="btn btn-solid">Entrar na plataforma <span class="arr">↵</span></button>
          </form>
        </div>
        <div class="pc-taskbar">
          <p class="entry-help">Novo utilizador? <a href="/registar">Criar conta</a></p>
          <div class="pc-power" aria-hidden="true">
            <span id="pc-date">Cabinda</span>
            <span class="pc-power-btn" title="Sistema ativo">⏻</span>
          </div>
        </div>
      </div>
      <div class="pc-chin" aria-hidden="true"><span>ATC · WORKSTATION</span></div>
      <div class="pc-stand" aria-hidden="true"></div>
    </div>
  </section>
</main>""")


@route("POST", "/entrar")
def login_post(r):
    email, pw = r.data.get("email", "").strip().lower(), r.data.get("pw", "")
    phone = norm_phone(email) if "@" not in email else None   # também se pode entrar com o telemóvel
    u = r.con.execute("SELECT * FROM users WHERE (email=? OR phone=?) AND active=1", (email, phone)).fetchone()
    if not u or not check_pw(pw, u["pw_hash"]):
        time.sleep(0.5)
        r.query = {"seguinte": r.data.get("seguinte", "/")}
        r.send(200, login_get(r, "Email, telemóvel ou palavra-passe incorretos."))
        return None
    tok = secrets.token_urlsafe(32)
    r.con.execute("DELETE FROM sessions WHERE created < ?", (time.time() - SESSION_DAYS * 86400,))
    r.con.execute("INSERT INTO sessions VALUES(?,?,?,?)", (tok, u["id"], secrets.token_urlsafe(24), time.time()))
    r.con.commit()
    nxt = r.data.get("seguinte", "/")
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    seguro = "; Secure" if r.headers.get("X-Forwarded-Proto") == "https" else ""  # atrás do nginx com HTTPS
    r.send(303, "", headers={"Location": nxt, "Set-Cookie":
           f"{COOKIE}={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS * 86400}{seguro}"})


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


def selected_presenter(r, cid=None):
    """O guia é escolhido uma vez e vale para toda a plataforma (cid mantém-se por compatibilidade)."""
    uid = r.user["id"]
    row = r.con.execute("SELECT presenter FROM learner_presenter WHERE user_id=?", (uid,)).fetchone()
    if row:
        return row["presenter"]
    legacy = r.con.execute("SELECT presenter FROM course_presenters WHERE user_id=? ORDER BY updated DESC LIMIT 1", (uid,)).fetchone()
    if legacy:  # escolhas antigas, feitas por curso, passam a valer para tudo
        r.con.execute("INSERT OR IGNORE INTO learner_presenter VALUES(?,?,?)", (uid, legacy["presenter"], now()))
        return legacy["presenter"]
    if r.user["role"] in ("admin", "formador"):
        return "helena"   # formadores e administradores não precisam de escolher um guia para abrir aulas e responder
    return None


def set_presenter(r, key):
    uid = r.user["id"]
    r.con.execute("""INSERT INTO learner_presenter VALUES(?,?,?) ON CONFLICT(user_id)
        DO UPDATE SET presenter=excluded.presenter, updated=excluded.updated""", (uid, key, now()))
    r.con.execute("UPDATE course_presenters SET presenter=?, updated=? WHERE user_id=?", (key, now(), uid))


def safe_next(url, default="/"):
    return url if url and url.startswith("/") and not url.startswith("//") and "\\" not in url else default


def save_profile(r):
    name = r.data.get("display_name", "").strip()
    occupation = r.data.get("occupation", "").strip()
    goal = r.data.get("goal", "").strip()
    color = r.data.get("color", "sand")
    if not 1 <= len(name) <= 60 or len(occupation) > 100 or len(goal) > 300 or color not in PROFILE_COLORS:
        raise HttpError(400, "Verifique o nome, a cor e os limites dos campos do perfil.")
    r.con.execute("""INSERT INTO learner_profiles VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
        display_name=excluded.display_name, occupation=excluded.occupation, goal=excluded.goal,
        color=excluded.color, updated=excluded.updated""", (r.user["id"], name, occupation, goal, color, now()))


@route("POST", "/conta/perfil", "user")
def profile_save(r):
    save_profile(r)
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
    if c["status"] == "amostra":
        links = f'<a class="btn small" href="/cursos/{h(c["slug"])}">Abrir amostra →</a>'
        if (COURSES_DIR / c["slug"] / "manual/exemplos-atc.json").is_file():
            links += f' <a class="btn small ghost" href="/cursos/{h(c["slug"])}/exemplos">Ver exemplos →</a>'
        return (f'<article class="course">{cover}<div><h3>{h(c["title"])}</h3><p>{h(c["subtitle"])}</p>'
                f'<span class="tag">Amostra · Módulo 1</span> <span class="muted">Manual, exemplos e questionário</span>'
                f'<p>{links}</p></div></article>')
    if c["status"] != "publicado":
        foot = f'<span class="tag soon">Em breve</span> <span class="muted">{hours}</span>'
        if (COURSES_DIR / c["slug"] / "manual/exemplos-atc.json").is_file():
            foot += f'<p><a class="btn small ghost" href="/cursos/{h(c["slug"])}/exemplos">Ver exemplos →</a></p>'
        return f'<article class="course soon">{cover}<div><h3>{h(c["title"])}</h3><p>{h(c["subtitle"])}</p>{foot}</div></article>'
    if enrolled or r.is_staff():
        p = course_progress(r.con, r.user["id"], c["id"])
        label = "Concluído" if p["complete"] else (f'{p["pct"]}% concluído' if p["pct"] else "Começar")
        foot = f'{bar(p["pct"])}<span class="muted">{label} · {hours}</span>'
        return (f'<a class="course" href="/cursos/{h(c["slug"])}">{cover}<div><h3>{h(c["title"])}</h3>'
                f'<p>{h(c["subtitle"])}</p>{foot}</div></a>')
    return (f'<article class="course locked">{cover}<div><h3>{h(c["title"])}</h3><p>{h(c["subtitle"])}</p>'
            f'<span class="tag">Inscrição na ATC</span> <span class="muted">{hours}</span></div></article>')


def public_nav(cta=("/entrar", "Entrar")):
    return ('<header class="nav" id="nav"><nav class="nav-links label" aria-label="Secções"><a href="/#abordagem">Abordagem</a><a href="/#guias">Guias</a>'
            '<a href="/#percursos">Percursos</a></nav><a class="nav-logo" href="/"><img src="/static/logo-200.png" alt=""><span>ATC Formação</span></a>'
            f'<div class="nav-cta"><a class="btn btn-line" href="{cta[0]}">{cta[1]} <span class="arr">→</span></a></div></header>')


def public_page(title, body, privada=False):
    """Páginas públicas (início e entrada): visual editorial próprio, sem a barra lateral do LMS."""
    return f"""<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(title)} · ATC Formação</title>{'<meta name="robots" content="noindex, nofollow">' if privada else ''}<meta name="description" content="Formação em informática, hardware e redes, em português, na ATC — Angbu Training Centre, Cabinda.">
<link rel="icon" href="/static/logo-200.png"><link rel="preload" href="/static/fonts/Geist.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/static/fonts/InstrumentSerif.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/static/inicio.css?v=11"><script src="/static/inicio.js?v=5" defer></script><script src="/static/ui.js?v=6" defer></script></head>
<body>{body}</body></html>"""


LANDING_PATHS = [("informatica", "/static/inicio/thumb-info.jpg"), ("comptia-a-plus", "/static/inicio/pc.jpg"),
                 ("comptia-network-plus", "/static/inicio/rede.jpg"), ("word", "/static/inicio/thumb-office.jpg")]


def landing(r):
    count = len(list((STATIC / "frames" / "aplus").glob("*.webp")))
    courses = {c["slug"]: c for c in r.con.execute("SELECT slug, title, status FROM courses WHERE active=1")}
    rows = [(courses[s], img) for s, img in LANDING_PATHS if s in courses]
    names = {"word": "Microsoft Office"}
    paths = "\n".join(
        f'  <a class="path" href="/entrar" data-img="{img}"><span class="n">{i:02d}</span><h3>{h(names.get(c["slug"], c["title"].split(" (")[0]))}</h3>'
        f'<span class="st{" live" if c["status"] == "publicado" else ""}">{STATUS.get(c["status"], "")}</span><span class="go">→</span></a>'
        for i, (c, img) in enumerate(rows, 1))
    return public_page("Início", f'''{public_nav()}

<section class="hero">
  <img class="poster" src="/static/inicio/rede.jpg" alt="">
  <video src="/static/inicio/rede.mp4" poster="/static/inicio/rede.jpg" autoplay muted loop playsinline aria-hidden="true"></video>
  <div class="hero-inner">
    <span class="label rv">Angbu Training Centre — Cabinda, Angola</span>
    <h1 class="serif rv d1">Competências<br>digitais que<br><em>abrem portas.</em></h1>
    <div class="hero-side rv d2">
      <p>Formação em informática, hardware e redes, em português, com um guia que o acompanha do primeiro clique à certificação.</p>
      <div class="actions"><a class="btn btn-solid" href="/registar">Começar agora <span class="arr">→</span></a><a class="btn btn-line" href="#percursos">Ver percursos</a></div>
    </div>
  </div>
  <div class="hero-foot"><div class="ticker label"><span><b>01</b>Informática</span><span><b>02</b>CompTIA A+</span><span><b>03</b>CompTIA Network+</span><span><b>04</b>Microsoft Office</span></div></div>
</section>

<section class="statement" id="abordagem">
  <span class="label rv">A nossa abordagem</span>
  <h2 class="serif rv d1">Tecnologia não se decora. <em>Aprende-se a fazer.</em></h2>
  <div class="pillars">
    <div class="rv"><span class="label">01</span><b>Aulas em vídeo</b><p>Curtas, práticas e em português, para ver ao seu ritmo e rever quando quiser.</p></div>
    <div class="rv d1"><span class="label">02</span><b>Prática guiada</b><p>Exercícios e questionários em cada módulo, para pôr à prova o que aprendeu.</p></div>
    <div class="rv d2"><span class="label">03</span><b>Certificado</b><p>Reconhecimento no fim de cada percurso, pronto para o seu currículo.</p></div>
  </div>
</section>

<section class="feature" id="feature" data-frames="/static/frames/aplus/" data-count="{count}">
  <div class="feature-stick">
    <div class="feature-media"><canvas aria-hidden="true"></canvas><video class="feature-net" src="/static/inicio/rede.mp4" poster="/static/inicio/rede.jpg" muted loop playsinline preload="none" aria-hidden="true"></video><img src="/static/inicio/pc.jpg" alt="Computador de secretária montado."><div class="feature-count" aria-hidden="true"><span id="fcount">01</span><small>/ 04</small></div></div>
    <div class="feature-copy">
      <div class="feature-tabs" role="tablist" aria-label="Percursos técnicos em destaque">
        <button type="button" class="feature-tab on" role="tab" aria-selected="true" data-track="aplus">01 · CompTIA A+ · Hardware</button>
        <button type="button" class="feature-tab" role="tab" aria-selected="false" data-track="netplus">02 · CompTIA Network+ · Redes</button>
      </div>
      <span class="label" id="feyebrow">Percurso em destaque · Hardware</span>
      <h2 class="serif" id="ftitle">CompTIA A+</h2>
      <p id="fdesc">Monte, configure e repare computadores. Do processador à rede sem fios, aprende o que um técnico faz todos os dias.</p>
      <ul class="modules" id="fmodules">
        <li data-step="0" tabindex="0" role="button"><i></i><b>Componentes e montagem</b><span>01</span></li>
        <li data-step="1" tabindex="0" role="button"><i></i><b>Dispositivos móveis</b><span>02</span></li>
        <li data-step="2" tabindex="0" role="button"><i></i><b>Redes e conectividade</b><span>03</span></li>
        <li data-step="3" tabindex="0" role="button"><i></i><b>Segurança e resolução de problemas</b><span>04</span></li>
      </ul>
      <div><a class="btn btn-line" href="/entrar">Saber mais <span class="arr">→</span></a></div>
    </div>
  </div>
</section>

<section class="guides" id="guias">
  <div class="guides-head">
    <div><span class="label rv">Os seus guias</span><h2 class="serif rv d1">Alguém do seu lado, <em>em cada aula.</em></h2></div>
    <p class="rv d2">Escolha a Helena ou o Miguel. O seu guia apresenta cada aula, explica cada passo e responde às suas dúvidas em voz.</p>
  </div>
  <div class="guide-grid">
    <figure class="guide rv">
      <img src="/static/presenters/helena.png" alt="Helena, guia virtual da ATC.">
      <div class="guide-stage">
        <video class="guide-video" playsinline preload="none" src="/plataforma/helena/boas-vindas.mp4"><track kind="subtitles" srclang="pt" label="Português" src="/plataforma/helena/boas-vindas.vtt" default></video>
        <p class="guide-sub" aria-live="polite"></p>
      </div>
      <figcaption>
        <div class="guide-meta"><b>Helena</b><span class="label">Guia virtual da ATC</span></div>
        <button type="button" class="guide-play" data-guide-play data-label="▶ Ouvir a Helena">▶ Ouvir a Helena</button>
      </figcaption>
    </figure>
    <figure class="guide rv d1">
      <img src="/static/presenters/miguel.png" alt="Miguel, guia virtual da ATC.">
      <div class="guide-stage">
        <video class="guide-video" playsinline preload="none" src="/plataforma/miguel/boas-vindas.mp4"><track kind="subtitles" srclang="pt" label="Português" src="/plataforma/miguel/boas-vindas.vtt" default></video>
        <p class="guide-sub" aria-live="polite"></p>
      </div>
      <figcaption>
        <div class="guide-meta"><b>Miguel</b><span class="label">Guia virtual da ATC</span></div>
        <button type="button" class="guide-play" data-guide-play data-label="▶ Ouvir o Miguel">▶ Ouvir o Miguel</button>
      </figcaption>
    </figure>
  </div>
  <small>Personagens virtuais criadas para a ATC. Clique em «Ouvir» para conhecer a voz de cada guia.</small>
</section>

<section class="paths" id="percursos">
  <div class="paths-head"><div><span class="label">Percursos</span><h2 class="serif">Comece pelo essencial.</h2></div><span class="label">{len(rows):02d} percursos</span></div>
{paths}
  <div class="path-thumb" id="thumb" aria-hidden="true"><img alt=""></div>
</section>

<section class="final">
  <span class="label rv">Cabinda, Angola</span>
  <h2 class="serif rv d1">Pronto para <em>começar?</em></h2>
  <div class="actions rv d2"><a class="btn btn-solid" href="/entrar">Entrar na plataforma <span class="arr">→</span></a></div>
  <div class="foot label"><span>© ATC · Angbu Training Centre</span><span>Aprendizagem com propósito</span></div>
</section>''')


# ---------------------------------------------------------------------------
# Registo, planos, pagamentos e códigos de acesso
# ---------------------------------------------------------------------------
# O acesso é separado do pagamento: um formando tem acesso a todos os cursos publicados até uma data
# (tabela subscriptions). Esse acesso pode vir de um pagamento (Multicaixa Express, referência Multicaixa,
# transferência com comprovativo ou pagamento na loja) ou de um código de acesso (por exemplo, oferecido
# com a internet do Grupo Angbu). Os pagamentos online passam por um fornecedor; enquanto não houver contrato,
# PAG_FORNECEDOR="demo" simula o fornecedor e o ecrã mostra botões de simulação claramente identificados.
# Para ligar um fornecedor real (EMIS GPO através do banco, ProxyPay, AppyPay...), substituir
# pag_criar_pedido() e enviar as confirmações para POST /pagamentos/notificacao (assinadas com ATC_PAG_SEGREDO).

PAG_FORNECEDOR = os.environ.get("ATC_PAG_FORNECEDOR", "demo")
PAG_SEGREDO = os.environ.get("ATC_PAG_SEGREDO", "")
PAG_DADOS_BANCO = {"banco": "Banco de exemplo", "titular": "ATC – Angbu Training Centre",
                   "iban": "AO06 0000 0000 0000 0000 0000 0"}   # substituir pelos dados reais da ATC
PROVINCIAS = ["Bengo", "Benguela", "Bié", "Cabinda", "Cuando", "Cuanza Norte", "Cuanza Sul", "Cubango", "Cunene", "Huambo",
              "Huíla", "Icolo e Bengo", "Luanda", "Lunda Norte", "Lunda Sul", "Malanje", "Moxico", "Moxico Leste", "Namibe",
              "Uíge", "Zaire"]
PLANOS_INICIAIS = [  # (slug, nome, meses, preço em Kz, descrição) — valores de demonstração
    ("mensal", "Mensal", 1, 7500, "Acesso a todos os cursos durante 1 mês."),
    ("trimestral", "Trimestral", 3, 19500, "3 meses de acesso, com poupança face ao plano mensal."),
    ("anual", "Anual", 12, 60000, "Um ano inteiro de formação, ao melhor preço."),
]
METODOS = {"mcx": "Multicaixa Express", "referencia": "Referência Multicaixa",
           "transferencia": "Transferência bancária", "loja": "Pagamento na loja"}
PAG_ESTADOS = {"pendente": "A aguardar", "em_analise": "Em análise", "pago": "Pago", "recusado": "Recusado", "expirado": "Expirado"}
COMPROVATIVOS = DATA_DIR / "comprovativos"

PAG_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL, months INTEGER NOT NULL,
  price_kz INTEGER NOT NULL, description TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS subscriptions (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), plan_id INTEGER REFERENCES plans(id),
  starts TEXT NOT NULL, ends TEXT NOT NULL, source TEXT NOT NULL, ref TEXT, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), plan_id INTEGER NOT NULL REFERENCES plans(id),
  amount_kz INTEGER NOT NULL, method TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pendente', provider TEXT NOT NULL,
  entity TEXT, reference TEXT, phone TEXT, note TEXT, proof TEXT, expires TEXT, created TEXT NOT NULL, updated TEXT NOT NULL,
  reviewed_by INTEGER);
CREATE TABLE IF NOT EXISTS access_codes (
  code TEXT PRIMARY KEY, plan_id INTEGER NOT NULL REFERENCES plans(id), label TEXT NOT NULL DEFAULT '',
  created_by INTEGER, created TEXT NOT NULL, used_by INTEGER REFERENCES users(id), used_at TEXT);
"""


def pag_init(con):
    con.executescript(PAG_SCHEMA)
    cols = {row["name"] for row in con.execute("PRAGMA table_info(users)")}
    if "phone" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    if "province" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN province TEXT")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_phone ON users(phone) WHERE phone IS NOT NULL")
    for i, (slug, name, months, price, desc) in enumerate(PLANOS_INICIAIS):
        con.execute("INSERT OR IGNORE INTO plans(slug, name, months, price_kz, description, sort) VALUES(?,?,?,?,?,?)",
                    (slug, name, months, price, desc, i))


def kz(v):
    return f"{v:,.0f}".replace(",", " ") + " Kz"


def data_pt(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y") if s else ""


def norm_phone(s):
    """Telemóvel angolano em formato +2449XXXXXXXX, ou None."""
    d = re.sub(r"\D", "", s or "")
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("244") and len(d) == 12:
        d = d[3:]
    return "+244" + d if len(d) == 9 and d.startswith("9") else None


def acesso_ate(con, user_id):
    """Fim do acesso pago/por código mais longo que ainda está ativo (texto ISO), ou None."""
    row = con.execute("SELECT MAX(ends) e FROM subscriptions WHERE user_id=? AND ends >= ?", (user_id, now())).fetchone()
    return row["e"] if row and row["e"] else None


def acesso_expirado(con, user_id):
    """True se o formando já teve acesso pago/por código e todos expiraram (as inscrições feitas pela ATC não expiram)."""
    has = con.execute("SELECT 1 FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
    return bool(has) and not acesso_ate(con, user_id)


def ativar_plano(con, user_id, plan, source, ref):
    """Soma os meses do plano ao acesso atual e inscreve o formando em todos os cursos publicados."""
    start = max(datetime.now(), datetime.strptime(acesso_ate(con, user_id) or now(), "%Y-%m-%d %H:%M:%S"))
    end = start.replace(microsecond=0) + timedelta(days=30 * plan["months"])
    con.execute("INSERT INTO subscriptions(user_id, plan_id, starts, ends, source, ref, created) VALUES(?,?,?,?,?,?,?)",
                (user_id, plan["id"], start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"), source, ref, now()))
    for c in con.execute("SELECT id FROM courses WHERE active=1 AND status='publicado'").fetchall():
        con.execute("INSERT OR IGNORE INTO enrolments VALUES(?,?,?)", (user_id, c["id"], now()))
    return end


def pag_confirmar(con, pid, ok, reviewer=None):
    """Marca um pagamento como pago (ativa o plano) ou recusado. Idempotente: um pagamento pago não é ativado duas vezes."""
    p = con.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if not p or p["status"] in ("pago", "recusado", "expirado"):
        return p
    con.execute("UPDATE payments SET status=?, updated=?, reviewed_by=? WHERE id=?", ("pago" if ok else "recusado", now(), reviewer, pid))
    if ok:
        plan = con.execute("SELECT * FROM plans WHERE id=?", (p["plan_id"],)).fetchone()
        ativar_plano(con, p["user_id"], plan, "pagamento", f"P{pid}")
    return con.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()


def pag_criar_pedido(method, amount, phone):
    """Pedido ao fornecedor de pagamentos. Na demonstração gera dados no formato real, sem dinheiro envolvido."""
    if method == "referencia":
        return {"entity": "00000", "reference": f"{secrets.randbelow(10**9):09d}",
                "expires": datetime.fromtimestamp(time.time() + 86400).strftime("%Y-%m-%d %H:%M:%S")}
    if method == "mcx":
        return {"phone": phone, "expires": datetime.fromtimestamp(time.time() + 90).strftime("%Y-%m-%d %H:%M:%S")}
    if method == "loja":
        return {"reference": "ATC-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))}
    return {}


def gerar_codigo():
    alfa = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "-".join("".join(secrets.choice(alfa) for _ in range(4)) for _ in range(3))


def demo_aviso():
    return ('<p class="pay-demo">Ambiente de demonstração: nenhum pagamento é real. Os valores e os dados bancários são exemplos.</p>'
            if PAG_FORNECEDOR == "demo" else "")


# --- Registo ------------------------------------------------------------------

@route("GET", "/registar")
def register_get(r, error="", values=None):
    if r.user:
        raise Redirect("/planos")
    v = values or {}
    err = f'<p class="entry-error" role="alert">{h(error)}</p>' if error else ""
    provs = "".join(f'<option{" selected" if v.get("province") == p else ""}>{h(p)}</option>' for p in PROVINCIAS)
    return public_page("Criar conta", f"""{public_nav(("/entrar", "Entrar"))}
<main class="entry">
  <section class="entry-show" aria-label="O que inclui">
    <span class="label">Para todo o país</span>
    <h2 class="serif">Aprenda de qualquer <em>província.</em></h2>
    <ul class="entry-points">
      <li><b>Crie a conta</b><span>Com o seu telemóvel e email, em menos de um minuto.</span></li>
      <li><b>Escolha um plano</b><span>Pague por Multicaixa Express, referência, transferência ou na loja.</span></li>
      <li><b>Tem um código?</b><span>Clientes da internet do Grupo Angbu recebem um código de acesso.</span></li>
    </ul>
  </section>
  <section class="entry-form"><div>
    <span class="label">Nova conta</span>
    <h1 class="serif">Comece <em>hoje.</em></h1>
    <p class="lead">Já tem conta? <a class="link" href="/entrar">Entrar</a></p>
    {err}<form method="post" action="/registar">
      <label class="field"><span class="label">Nome completo</span><input name="name" required maxlength="80" autocomplete="name" value="{h(v.get('name', ''))}"></label>
      <label class="field"><span class="label">Telemóvel</span><input name="phone" required inputmode="tel" autocomplete="tel" placeholder="9XX XXX XXX" value="{h(v.get('phone', ''))}"></label>
      <label class="field"><span class="label">Email</span><input type="email" name="email" required autocomplete="email" placeholder="nome@exemplo.com" value="{h(v.get('email', ''))}"></label>
      <label class="field"><span class="label">Província</span><select name="province" required><option value="">Escolha a sua província</option>{provs}</select></label>
      <label class="field"><span class="label">Palavra-passe</span><span class="pw"><input type="password" name="pw" required minlength="8" autocomplete="new-password" placeholder="Pelo menos 8 caracteres"><button type="button" data-pw-toggle aria-label="Mostrar palavra-passe" aria-pressed="false">Mostrar</button></span></label>
      <button class="btn btn-solid">Criar conta <span class="arr">→</span></button>
    </form>
    <p class="entry-help">Ao criar conta aceita que a ATC use estes dados para gerir a sua formação.</p>
  </div></section>
</main>""")


@route("POST", "/registar")
def register_post(r):
    d = {k: (r.data.get(k) or "").strip() for k in ("name", "phone", "email", "province")}
    d["email"] = d["email"].lower()
    phone, pw = norm_phone(d["phone"]), r.data.get("pw") or ""
    error = ("Indique o seu nome." if len(d["name"]) < 2 else
             "Indique um telemóvel angolano válido (9 dígitos, começa por 9)." if not phone else
             "Indique um email válido." if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", d["email"]) else
             "Escolha a sua província." if d["province"] not in PROVINCIAS else
             "A palavra-passe precisa de pelo menos 8 caracteres." if len(pw) < 8 else
             "Já existe uma conta com este email. Entre com a sua conta." if r.con.execute("SELECT 1 FROM users WHERE email=?", (d["email"],)).fetchone() else
             "Já existe uma conta com este telemóvel. Entre com a sua conta." if r.con.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone() else "")
    if error:
        r.send(200, register_get(r, error, d))
        return None
    cur = r.con.execute("INSERT INTO users(email, name, role, pw_hash, created, phone, province) VALUES(?,?,?,?,?,?,?)",
                        (d["email"], d["name"], "formando", hash_pw(pw), now(), phone, d["province"]))
    r.con.commit()
    start_session(r, cur.lastrowid, "/planos")


def start_session(r, user_id, nxt):
    tok = secrets.token_urlsafe(32)
    r.con.execute("DELETE FROM sessions WHERE created < ?", (time.time() - SESSION_DAYS * 86400,))
    r.con.execute("INSERT INTO sessions VALUES(?,?,?,?)", (tok, user_id, secrets.token_urlsafe(24), time.time()))
    r.con.commit()
    seguro = "; Secure" if r.headers.get("X-Forwarded-Proto") == "https" else ""  # atrás do nginx com HTTPS
    r.send(303, "", headers={"Location": nxt, "Set-Cookie":
           f"{COOKIE}={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS * 86400}{seguro}"})


# --- Planos e códigos -----------------------------------------------------------

def estado_acesso(r):
    ate = acesso_ate(r.con, r.user["id"])
    if ate:
        return f'<section class="pay-status"><b>Acesso ativo</b><span>Todos os cursos disponíveis até {data_pt(ate)}.</span><a class="btn small ghost" href="/">Ir para os cursos →</a></section>'
    if acesso_expirado(r.con, r.user["id"]):
        return '<section class="pay-status warn"><b>O seu acesso terminou</b><span>Escolha um plano ou introduza um código para continuar.</span></section>'
    return ""


@route("GET", "/planos", "user")
def plans_page(r, msg=""):
    plans = r.con.execute("SELECT * FROM plans WHERE active=1 ORDER BY sort").fetchall()
    pend = r.con.execute("SELECT p.*, pl.name plan FROM payments p JOIN plans pl ON pl.id=p.plan_id WHERE user_id=? AND status IN ('pendente','em_analise') ORDER BY id DESC",
                         (r.user["id"],)).fetchall()
    cards = "".join(
        f'<article class="plan{" best" if p["slug"] == "trimestral" else ""}">{"<span class=tag>Mais escolhido</span>" if p["slug"] == "trimestral" else ""}'
        f'<h3>{h(p["name"])}</h3><p class="plan-price">{kz(p["price_kz"])}</p><p class="muted">{h(p["description"])}</p>'
        f'<a class="btn" href="/pagar/{h(p["slug"])}">Escolher {h(p["name"].lower())} →</a></article>' for p in plans)
    pend_html = "".join(f'<li><a href="/pagamentos/{p["id"]}">{h(p["plan"])} · {METODOS[p["method"]]} · {kz(p["amount_kz"])}</a>'
                        f'<span class="tag">{PAG_ESTADOS[p["status"]]}</span></li>' for p in pend)
    flash = f'<div class="flash" role="status">{msg}</div>' if msg else ""
    return r.render("Planos", f"""{flash}<div class="page-heading"><div><span class="eyebrow">ACESSO À FORMAÇÃO</span><h1>Escolha o seu plano<span class="greeting-dot">.</span></h1>
<p class="muted">Cada plano dá acesso a todos os cursos disponíveis, com aulas, manuais, questionários e certificado.</p></div></div>
{estado_acesso(r)}{demo_aviso()}<div class="plans">{cards}</div>
{"<section class='card'><h2>Pagamentos em curso</h2><ul class='pay-list'>" + pend_html + "</ul></section>" if pend_html else ""}
<section class="card code-box"><div><span class="eyebrow">TEM UM CÓDIGO DE ACESSO?</span><h2>Ative o seu código</h2>
<p class="muted">Recebeu um código com a sua internet do Grupo Angbu ou da ATC? Introduza-o aqui.</p></div>
<form method="post" action="/codigo">{csrf_field(r.csrf)}<input name="code" required placeholder="XXXX-XXXX-XXXX" autocomplete="off" aria-label="Código de acesso"><button class="btn">Ativar código</button></form></section>""")


@route("POST", "/codigo", "user")
def redeem_code(r):
    code = re.sub(r"[^A-Z0-9]", "", (r.data.get("code") or "").upper())
    code = "-".join(code[i:i + 4] for i in range(0, len(code), 4))
    row = r.con.execute("SELECT c.*, p.months, p.name FROM access_codes c JOIN plans p ON p.id=c.plan_id WHERE code=?", (code,)).fetchone()
    if not row:
        time.sleep(0.5)
        r.send(200, plans_page(r, "Código não encontrado. Confirme as letras e os números."))
        return None
    if row["used_by"]:
        r.send(200, plans_page(r, "Este código já foi utilizado."))
        return None
    r.con.execute("UPDATE access_codes SET used_by=?, used_at=? WHERE code=? AND used_by IS NULL", (r.user["id"], now(), code))
    plan = r.con.execute("SELECT * FROM plans WHERE id=?", (row["plan_id"],)).fetchone()
    end = ativar_plano(r.con, r.user["id"], plan, "codigo", code)
    r.con.commit()
    r.send(200, plans_page(r, f"Código ativado. Tem acesso a todos os cursos até {end.strftime('%d/%m/%Y')}."))


# --- Pagar ----------------------------------------------------------------------

def plano(r, slug):
    p = r.con.execute("SELECT * FROM plans WHERE slug=? AND active=1", (slug,)).fetchone()
    if not p:
        raise HttpError(404)
    return p


@route("GET", "/pagar/([a-z0-9-]+)", "user")
def pay_choose(r, slug):
    p = plano(r, slug)
    phone = r.user["phone"] if "phone" in r.user.keys() else ""
    opts = [("mcx", "Multicaixa Express", "Confirma no telemóvel, na app Multicaixa Express. Imediato."),
            ("referencia", "Referência Multicaixa", "Paga num ATM ou no home banking com entidade e referência. Válida 24 horas."),
            ("transferencia", "Transferência bancária", "Transfere para a conta da ATC e envia o comprovativo. Confirmado pela ATC."),
            ("loja", "Pagamento na loja", "Recebe um código e paga na loja do Grupo Angbu. Confirmado no momento.")]
    radios = "".join(f'<label class="pay-opt"><input type="radio" name="method" value="{k}" required{" checked" if k == "mcx" else ""}>'
                     f'<span><b>{t}</b><small>{d}</small></span></label>' for k, t, d in opts)
    return r.render("Pagamento", f"""<div class="page-heading"><div><span class="eyebrow">PLANO {h(p['name'].upper())} · {kz(p['price_kz'])}</span>
<h1>Como prefere pagar<span class="greeting-dot">?</span></h1><p class="muted">{h(p['description'])}</p></div></div>{demo_aviso()}
<form method="post" action="/pagar/{h(slug)}" class="card pay-form">{csrf_field(r.csrf)}<fieldset><legend class="sr-only">Método de pagamento</legend>{radios}</fieldset>
<label class="mcx-phone">Telemóvel associado ao Multicaixa Express<input name="phone" inputmode="tel" placeholder="9XX XXX XXX" value="{h((phone or '').replace('+244', ''))}"></label>
<div class="pay-actions"><a href="/planos">← Voltar aos planos</a><button class="btn">Continuar → {kz(p['price_kz'])}</button></div></form>""")


@route("POST", "/pagar/([a-z0-9-]+)", "user")
def pay_create(r, slug):
    p = plano(r, slug)
    method = r.data.get("method")
    if method not in METODOS:
        raise HttpError(400, "Escolha um método de pagamento.")
    phone = norm_phone(r.data.get("phone")) if method == "mcx" else None
    if method == "mcx" and not phone:
        raise HttpError(400, "Indique o telemóvel associado ao Multicaixa Express (9 dígitos).")
    info = pag_criar_pedido(method, p["price_kz"], phone)
    cur = r.con.execute("""INSERT INTO payments(user_id, plan_id, amount_kz, method, provider, entity, reference, phone, expires, created, updated)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (r.user["id"], p["id"], p["price_kz"], method, PAG_FORNECEDOR,
                           info.get("entity"), info.get("reference"), info.get("phone"), info.get("expires"), now(), now()))
    r.con.commit()
    raise Redirect(f"/pagamentos/{cur.lastrowid}")


def pagamento_do_formando(r, pid):
    p = r.con.execute("SELECT p.*, pl.name plan, pl.months FROM payments p JOIN plans pl ON pl.id=p.plan_id WHERE p.id=?", (pid,)).fetchone()
    if not p or (p["user_id"] != r.user["id"] and not r.is_staff()):
        raise HttpError(404)
    if p["status"] == "pendente" and p["expires"] and p["expires"] < now():
        r.con.execute("UPDATE payments SET status='expirado', updated=? WHERE id=?", (now(), pid))
        r.con.commit()
        return pagamento_do_formando(r, pid)
    return p


@route("GET", "/pagamentos/([0-9]+)", "user")
def pay_page(r, pid):
    p = pagamento_do_formando(r, int(pid))
    m, st = p["method"], p["status"]
    head = (f'<div class="page-heading"><div><span class="eyebrow">{METODOS[m].upper()} · PLANO {h(p["plan"].upper())}</span>'
            f'<h1>{"Pagamento confirmado" if st == "pago" else "Pagamento " + PAG_ESTADOS[st].lower()}<span class="greeting-dot">.</span></h1></div>'
            f'<span class="tag pay-{st}">{PAG_ESTADOS[st]}</span></div>')
    if st == "pago":
        ate = acesso_ate(r.con, p["user_id"])
        return r.render("Pagamento", head + f'<section class="pay-status"><b>{kz(p["amount_kz"])} recebidos.</b><span>Tem acesso a todos os cursos até {data_pt(ate)}.</span>'
                        f'<a class="btn small" href="/">Começar a aprender →</a></section>')
    if st in ("recusado", "expirado"):
        why = "O pagamento não foi aprovado." if st == "recusado" else "O prazo deste pedido terminou."
        return r.render("Pagamento", head + f'<section class="pay-status warn"><b>{why}</b><span>Pode tentar de novo com o mesmo ou outro método.</span>'
                        f'<a class="btn small" href="/planos">Escolher de novo →</a></section>')
    sim = ""
    if PAG_FORNECEDOR == "demo" and m in ("mcx", "referencia"):
        acao = "Simular aprovação no telemóvel" if m == "mcx" else "Simular pagamento no ATM"
        sim = (f'<form method="post" action="/pagamentos/{p["id"]}/simular" class="pay-sim">{csrf_field(r.csrf)}<span>Demonstração: não há fornecedor ligado.</span>'
               f'<button class="btn small" name="ok" value="1">{acao}</button>'
               + (f'<button class="btn small ghost" name="ok" value="0">Simular recusa</button>' if m == "mcx" else "") + '</form>')
    if m == "mcx":
        body = (f'<section class="card pay-box"><p class="pay-big">Confirme no seu telemóvel</p><p>Enviámos um pedido de <b>{kz(p["amount_kz"])}</b> para a app Multicaixa Express do número '
                f'<b>{h(p["phone"])}</b>. Abra a app e aprove o pagamento.</p><p class="muted">O pedido expira às {h(p["expires"][11:16])}. Esta página atualiza sozinha.</p>{sim}</section>'
                f'<meta http-equiv="refresh" content="8">')
    elif m == "referencia":
        body = (f'<section class="card pay-box"><div class="ref-grid"><div><span>Entidade</span><b>{h(p["entity"])}</b></div><div><span>Referência</span><b>{h(p["reference"][:3])} {h(p["reference"][3:6])} {h(p["reference"][6:])}</b></div>'
                f'<div><span>Montante</span><b>{kz(p["amount_kz"])}</b></div></div><p>Pague num ATM Multicaixa ou no home banking, em <b>Pagamentos → Pagamento por referência</b>. '
                f'O acesso é ativado automaticamente após o pagamento.</p><p class="muted">Válida até {data_pt(p["expires"])} às {h(p["expires"][11:16])}.</p>{sim}</section>')
    elif m == "transferencia":
        b = PAG_DADOS_BANCO
        enviado = p["proof"] or p["note"]
        body = (f'<section class="card pay-box"><div class="ref-grid"><div><span>Banco</span><b>{h(b["banco"])}</b></div><div><span>Titular</span><b>{h(b["titular"])}</b></div>'
                f'<div class="wide"><span>IBAN</span><b>{h(b["iban"])}</b></div><div><span>Montante</span><b>{kz(p["amount_kz"])}</b></div><div><span>Descritivo</span><b>ATC P{p["id"]}</b></div></div>'
                + ('<p><b>Comprovativo recebido.</b> A ATC confirma o pagamento e ativa o seu acesso, normalmente no mesmo dia útil.</p>' if enviado else
                   f'<p>Depois de transferir, envie o comprovativo (PDF ou fotografia).</p><form method="post" action="/pagamentos/{p["id"]}/comprovativo" enctype="multipart/form-data" class="proof-form">'
                   f'{csrf_field(r.csrf)}<input type="file" name="proof" accept=".pdf,.jpg,.jpeg,.png" required aria-label="Comprovativo de pagamento"><input name="note" placeholder="N.º da operação (opcional)" aria-label="Número da operação">'
                   f'<button class="btn">Enviar comprovativo</button></form>') + '</section>')
    else:
        body = (f'<section class="card pay-box"><p class="pay-big">{h(p["reference"])}</p><p>Apresente este código numa loja do Grupo Angbu e pague <b>{kz(p["amount_kz"])}</b> na caixa. '
                f'O acesso é ativado quando a loja confirmar o pagamento.</p><p class="muted">Guarde este código ou tire uma fotografia ao ecrã.</p></section>')
    return r.render("Pagamento", head + demo_aviso() + body + '<p><a href="/planos">← Voltar aos planos</a></p>')


@route("POST", "/pagamentos/([0-9]+)/simular", "user")
def pay_simulate(r, pid):
    if PAG_FORNECEDOR != "demo":
        raise HttpError(404)
    p = pagamento_do_formando(r, int(pid))
    if p["method"] in ("mcx", "referencia") and p["status"] == "pendente":
        pag_confirmar(r.con, p["id"], r.data.get("ok") == "1")
        r.con.commit()
    raise Redirect(f"/pagamentos/{pid}")


@route("POST", "/pagamentos/([0-9]+)/comprovativo", "user")
def pay_proof(r, pid):
    p = pagamento_do_formando(r, int(pid))
    f = r.data.get("proof")
    if p["method"] != "transferencia" or p["status"] != "pendente":
        raise Redirect(f"/pagamentos/{pid}")
    if not isinstance(f, dict) or not f["data"]:
        raise HttpError(400, "Escolha o ficheiro do comprovativo.")
    ext = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}.get(f["type"]) or Path(f["filename"]).suffix.lower()
    if ext not in (".pdf", ".jpg", ".jpeg", ".png") or (ext == ".pdf" and not f["data"].startswith(b"%PDF")) or \
            (ext != ".pdf" and not (f["data"].startswith(b"\xff\xd8") or f["data"].startswith(b"\x89PNG"))):
        raise HttpError(400, "O comprovativo tem de ser um PDF, JPG ou PNG.")
    COMPROVATIVOS.mkdir(parents=True, exist_ok=True)
    name = f"P{p['id']}-{secrets.token_hex(6)}{'.jpg' if ext == '.jpeg' else ext}"
    (COMPROVATIVOS / name).write_bytes(f["data"])
    r.con.execute("UPDATE payments SET proof=?, note=?, status='em_analise', updated=? WHERE id=?",
                  (name, (r.data.get("note") or "")[:80], now(), p["id"]))
    r.con.commit()
    raise Redirect(f"/pagamentos/{pid}")


@route("POST", "/pagamentos/notificacao")
def pay_webhook(r):
    """Confirmação do fornecedor de pagamentos (servidor a servidor). Corpo JSON {"payment_id": n, "status": "pago"|"recusado"},
    com cabeçalho X-ATC-Assinatura = HMAC-SHA256 de "payment_id:status" com ATC_PAG_SEGREDO. Sem segredo configurado, fica desligado.
    Ao ligar um fornecedor real, adaptar aqui o formato da notificação dele."""
    if not PAG_SEGREDO:
        raise HttpError(404)
    d = r.data if isinstance(r.data, dict) else {}
    msg = f'{d.get("payment_id")}:{d.get("status")}'.encode()
    sig = hmac.new(PAG_SEGREDO.encode(), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(r.headers.get("X-ATC-Assinatura", ""), sig) or d.get("status") not in ("pago", "recusado"):
        raise HttpError(403, "Assinatura inválida.")
    pag_confirmar(r.con, int(d["payment_id"]), d["status"] == "pago")
    r.con.commit()
    r.send(200, '{"ok": true}', ctype="application/json")


# --- Gestão: pagamentos e códigos ------------------------------------------------

@route("GET", "/admin/pagamentos", "staff")
def admin_payments(r):
    rows = r.con.execute("""SELECT p.*, u.name uname, u.phone uphone, u.province, pl.name plan FROM payments p JOIN users u ON u.id=p.user_id
                            JOIN plans pl ON pl.id=p.plan_id ORDER BY (p.status IN ('em_analise','pendente')) DESC, p.id DESC LIMIT 200""").fetchall()
    def actions(p):
        if p["status"] not in ("pendente", "em_analise") or p["method"] not in ("transferencia", "loja"):
            return ""
        return (f'<form method="post" action="/admin/pagamentos/{p["id"]}" class="inline">{csrf_field(r.csrf)}'
                f'<button class="btn small" name="ok" value="1">Confirmar</button> <button class="btn small ghost" name="ok" value="0">Recusar</button></form>')
    trs = "".join(f'<tr><td>P{p["id"]}<br><small class="muted">{h(p["created"][:16])}</small></td><td>{h(p["uname"])}<br><small class="muted">{h(p["uphone"] or "")} · {h(p["province"] or "")}</small></td>'
                  f'<td>{h(p["plan"])}<br><small class="muted">{kz(p["amount_kz"])}</small></td><td>{METODOS[p["method"]]}<br><small class="muted">{h(p["reference"] or p["note"] or "")}</small></td>'
                  f'<td><span class="tag pay-{p["status"]}">{PAG_ESTADOS[p["status"]]}</span>'
                  + (f'<br><a href="/admin/pagamentos/{p["id"]}/comprovativo">Ver comprovativo</a>' if p["proof"] else "") + f'</td><td>{actions(p)}</td></tr>' for p in rows)
    n_rev = sum(1 for p in rows if p["status"] == "em_analise")
    return r.render("Pagamentos", f"""<h1>Pagamentos</h1>{admin_tabs('/admin/pagamentos', r.user['role'] == 'admin')}{demo_aviso()}
<p class="muted">Transferências com comprovativo e pagamentos na loja são confirmados aqui. Multicaixa Express e referências são confirmados pelo fornecedor. {n_rev} por analisar.</p>
<div class="tablewrap"><table><thead><tr><th>Pedido</th><th>Formando</th><th>Plano</th><th>Método</th><th>Estado</th><th></th></tr></thead><tbody>{trs or '<tr><td colspan=6 class=muted>Ainda não há pagamentos.</td></tr>'}</tbody></table></div>""")


@route("POST", "/admin/pagamentos/([0-9]+)", "staff")
def admin_payment_review(r, pid):
    p = r.con.execute("SELECT * FROM payments WHERE id=?", (int(pid),)).fetchone()
    if p and p["method"] in ("transferencia", "loja"):
        pag_confirmar(r.con, p["id"], r.data.get("ok") == "1", r.user["id"])
        r.con.commit()
    raise Redirect("/admin/pagamentos")


@route("GET", "/admin/pagamentos/([0-9]+)/comprovativo", "staff")
def admin_payment_proof(r, pid):
    p = r.con.execute("SELECT proof FROM payments WHERE id=?", (int(pid),)).fetchone()
    if not p or not p["proof"]:
        raise HttpError(404)
    return r.serve_file(COMPROVATIVOS / p["proof"])


@route("GET", "/admin/codigos", "admin")
def admin_codes(r, msg=""):
    plans = r.con.execute("SELECT * FROM plans WHERE active=1 ORDER BY sort").fetchall()
    lotes = r.con.execute("""SELECT c.label, p.name plan, COUNT(*) n, SUM(c.used_by IS NOT NULL) used, MIN(c.created) created
                             FROM access_codes c JOIN plans p ON p.id=c.plan_id GROUP BY c.label, p.name ORDER BY created DESC""").fetchall()
    opts = "".join(f'<option value="{p["id"]}">{h(p["name"])} ({p["months"]} {"mês" if p["months"] == 1 else "meses"})</option>' for p in plans)
    trs = "".join(f'<tr><td>{h(l["label"])}</td><td>{h(l["plan"])}</td><td>{l["n"]}</td><td>{l["used"]}</td><td>{h(l["created"][:10])}</td>'
                  f'<td><a href="/admin/codigos.csv?lote={urllib.parse.quote(l["label"])}">Descarregar CSV</a></td></tr>' for l in lotes)
    flash = f'<div class="flash" role="status">{msg}</div>' if msg else ""
    return r.render("Códigos de acesso", f"""{flash}<h1>Códigos de acesso</h1>{admin_tabs('/admin/codigos', True)}
<p class="muted">Cada código dá acesso a todos os cursos durante o período do plano. Use-os para vender a formação com a internet do Grupo Angbu, em parcerias ou na loja.</p>
<form method="post" action="/admin/codigos" class="card code-gen">{csrf_field(r.csrf)}<label>Lote<input name="label" required maxlength="60" placeholder="Ex.: Internet Angbu — outubro"></label>
<label>Plano<select name="plan_id">{opts}</select></label><label>Quantidade<input type="number" name="n" min="1" max="500" value="20" required></label><button class="btn">Gerar códigos</button></form>
<div class="tablewrap"><table><thead><tr><th>Lote</th><th>Plano</th><th>Códigos</th><th>Usados</th><th>Criado</th><th></th></tr></thead><tbody>{trs or '<tr><td colspan=6 class=muted>Ainda não há códigos.</td></tr>'}</tbody></table></div>""")


@route("POST", "/admin/codigos", "admin")
def admin_codes_create(r):
    label = (r.data.get("label") or "").strip()[:60]
    plan = r.con.execute("SELECT * FROM plans WHERE id=?", (int(r.data.get("plan_id") or 0),)).fetchone()
    n = max(1, min(500, int(r.data.get("n") or 0)))
    if not label or not plan:
        raise HttpError(400, "Indique o nome do lote e o plano.")
    for _ in range(n):
        while True:
            code = gerar_codigo()
            if not r.con.execute("SELECT 1 FROM access_codes WHERE code=?", (code,)).fetchone():
                break
        r.con.execute("INSERT INTO access_codes(code, plan_id, label, created_by, created) VALUES(?,?,?,?,?)", (code, plan["id"], label, r.user["id"], now()))
    r.con.commit()
    r.send(200, admin_codes(r, f"{n} códigos criados no lote «{h(label)}». Descarregue o CSV para os distribuir."))


@route("GET", "/admin/codigos.csv", "admin")
def admin_codes_csv(r):
    rows = r.con.execute("""SELECT c.code, p.name plan, c.label, c.created, u.email FROM access_codes c JOIN plans p ON p.id=c.plan_id
                            LEFT JOIN users u ON u.id=c.used_by WHERE c.label=? ORDER BY c.created, c.code""", (r.query.get("lote", ""),)).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["codigo", "plano", "lote", "criado", "usado_por"])
    for row in rows:
        w.writerow([row["code"], row["plan"], row["label"], row["created"], row["email"] or ""])
    r.send(200, "﻿" + out.getvalue(), ctype="text/csv; charset=utf-8",
           headers={"Content-Disposition": 'attachment; filename="codigos-atc.csv"'})


# ---------------------------------------------------------------------------
# Apresentação ao cliente (página pública, fora dos motores de busca)
# ---------------------------------------------------------------------------

APRESENTACAO_VIDEOS = [  # (ficheiro, título, descrição, duração)
                       ("formando", "Formandos", "Da inscrição ao certificado: criar conta, pagar, escolher o guia, aprender e certificar.", "2:00"),
                       ("formador", "Formadores", "Responder a dúvidas, acompanhar a turma, inscrever formandos e confirmar pagamentos.", "1:01"),
                       ("admin", "Administração", "Contas, pagamentos com comprovativo, códigos de acesso, cursos e certificados.", "0:59")]


@route("GET", "/apresentacao")
def presentation(r):
    pasta = STATIC / "apresentacao"
    primeiro = APRESENTACAO_VIDEOS[0]
    cartoes = "".join(
        f'<button type="button" class="pv-card{" on" if i == 1 else ""}" data-video="/static/apresentacao/walkthrough-{k}.mp4" data-poster="/static/apresentacao/{k}.jpg" '
        f'data-titulo="{t}" aria-pressed="{"true" if i == 1 else "false"}"><img src="/static/apresentacao/{k}.jpg" alt="">'
        f'<span class="label">{i:02d} · {dur}</span><b>{t}</b><span>{d}</span></button>' for i, (k, t, d, dur) in enumerate(APRESENTACAO_VIDEOS, 1))
    videos = (f'<div class="pv-player rv"><video id="pv-video" controls preload="metadata" playsinline poster="/static/apresentacao/{primeiro[0]}.jpg">'
              f'<source src="/static/apresentacao/walkthrough-{primeiro[0]}.mp4" type="video/mp4"></video>'
              f'<button type="button" class="pv-full" id="pv-full">Ver em ecrã inteiro <span aria-hidden="true">⤢</span></button></div>'
              f'<div class="pv-cards" role="group" aria-label="Escolher o vídeo">{cartoes}</div>'
              f'<div class="pv-box" id="pv-box" hidden role="dialog" aria-modal="true" aria-label="Vídeo em ecrã inteiro">'
              f'<button type="button" class="pv-close" id="pv-close" aria-label="Fechar">✕</button><video id="pv-box-video" controls playsinline></video></div>')
    def lista(*itens):
        return "<ul>" + "".join(f"<li>{x}</li>" for x in itens) + "</ul>"
    pronto = "".join(f'<div class="pr-col rv"><span class="label">{t}</span>{l}</div>' for t, l in [
        ("Formandos", lista("Registo com telemóvel, email e província", "Planos com pagamento local ou código de acesso",
                            "Guia virtual à escolha: Helena ou Miguel", "Aulas em vídeo com demonstração e legendas",
                            "Dúvidas por escrito ou em voz", "Manuais ilustrados e descarregáveis", "Questionários e certificado verificável")),
        ("Formadores", lista("Lista de perguntas por responder", "Resposta na própria aula", "Relatório da turma com exportação para Excel",
                             "Inscrição de turmas inteiras de uma vez", "Confirmação de pagamentos na loja e por transferência")),
        ("Administração", lista("Contas e perfis (formando, formador, administrador)", "Registo de todos os pagamentos, com comprovativos",
                                "Códigos de acesso em lote, em CSV", "Publicação de cursos", "Verificação pública de certificados")),
        ("Plataforma", lista("Funciona em computador e telemóvel", "Português europeu, pensado para Angola", "Funciona também sem internet, em rede local",
                             "Sem licenças de terceiros: servidor próprio da ATC", "Página inicial e entrada com identidade própria")),
    ])
    decisoes = [
        ("Fornecedor de pagamentos", "Escolher como receber Multicaixa Express e referências Multicaixa. A plataforma está preparada para qualquer uma das opções:",
         '<div class="pr-table"><div><b>EMIS GPO, através do banco da ATC</b><span>Via oficial. Multicaixa Express e QR. Contrato com o banco.</span></div>'
         '<div><b>ProxyPay</b><span>Referências Multicaixa (ATM e home banking). Contrato com a ProxyPay e um banco angolano.</span></div>'
         '<div><b>AppyPay</b><span>Agregador com Multicaixa Express e links de pagamento. Condições a confirmar.</span></div></div>'),
        ("Preços dos planos", "Os valores atuais são de demonstração: Mensal 7 500 Kz, Trimestral 19 500 Kz, Anual 60 000 Kz.", ""),
        ("Dados bancários", "IBAN e titular para as transferências com comprovativo.", ""),
        ("Pacote com a internet Angbu", "Duração do acesso incluído (por exemplo, 3 meses) e quantos códigos gerar por mês para entregar com a internet.", ""),
        ("Próximos cursos", "Ordem e calendário dos cursos completos: Informática, CompTIA A+, CompTIA Network+ e Microsoft Office.", ""),
    ]
    dec = "".join(f'<li class="rv"><span class="n">{i:02d}</span><div><h3 class="serif">{t}</h3><p>{p}</p>{x}</div></li>'
                  for i, (t, p, x) in enumerate(decisoes, 1))
    fases = [("Validação", "A ATC experimenta a demonstração com as contas de teste e indica ajustes."),
             ("Pagamentos", "Contrato com o fornecedor escolhido e ligação à plataforma, primeiro em ambiente de testes."),
             ("Conteúdos", "Produção dos cursos completos, com a Helena e o Miguel, manuais e questionários."),
             ("Lançamento", "Abertura a formandos de todo o país e início do pacote com a internet Angbu.")]
    fs = "".join(f'<li class="rv"><span class="label">Fase {i}</span><b class="serif">{t}</b><p>{d}</p></li>' for i, (t, d) in enumerate(fases, 1))
    return public_page("Apresentação da plataforma", f"""{public_nav()}
<header class="pr-hero"><div class="pr-hero-copy"><span class="label rv">Apresentação · ATC — Angbu Training Centre · outubro de 2026</span>
<h1 class="serif rv d1">A sua academia digital, <em>pronta a crescer.</em></h1>
<p class="rv d2">Uma plataforma de formação própria da ATC, em português, para formandos de todo o país: aulas com guias virtuais, pagamentos locais,
acompanhamento pelos formadores e controlo total pela administração. Esta página reúne a demonstração, o que já está pronto e as decisões para avançar.</p>
<div class="actions rv d3"><a class="btn btn-solid" href="#videos">Ver os vídeos <span class="arr">↓</span></a><a class="btn btn-line" href="/">Abrir a plataforma <span class="arr">→</span></a></div></div>
<a class="pr-shots rv d2" href="#videos" aria-label="Ver os vídeos de demonstração"><img class="s3" src="/static/apresentacao/admin.jpg" alt="">
<img class="s2" src="/static/apresentacao/formador.jpg" alt=""><img class="s1" src="/static/apresentacao/formando.jpg" alt=""><span class="pr-play">▶ 3 vídeos · 4 min</span></a></header>
<section class="pr-sec" id="videos"><span class="label">01 · Demonstração em vídeo</span><h2 class="serif">Três percursos, <em>uma plataforma.</em></h2>
{videos}</section>
<section class="pr-sec"><span class="label">02 · O que já está pronto</span><h2 class="serif">Pronto a <em>experimentar.</em></h2><div class="pr-cols">{pronto}</div></section>
<section class="pr-sec pr-try"><span class="label">03 · Experimentar</span><h2 class="serif">Entre com as contas <em>de demonstração.</em></h2>
<p>As contas de formando, formador e administrador são enviadas em separado. Os pagamentos online estão em modo de demonstração:
os botões «Simular» substituem a aprovação no telemóvel e o pagamento no ATM, e nenhum valor é cobrado.</p>
<div class="actions"><a class="btn btn-solid" href="/entrar">Entrar na plataforma <span class="arr">→</span></a><a class="btn btn-line" href="/registar">Criar uma conta de teste</a></div></section>
<section class="pr-sec"><span class="label">04 · Decisões para a ATC</span><h2 class="serif">O que precisamos <em>de si.</em></h2><ol class="pr-dec">{dec}</ol></section>
<section class="pr-sec"><span class="label">05 · Próximos passos</span><h2 class="serif">Do piloto <em>ao país.</em></h2><ol class="pr-fases">{fs}</ol>
<p class="pr-note">O calendário de cada fase é acordado com a ATC.</p></section>
<section class="final"><span class="label rv">Cabinda, Angola</span><h2 class="serif rv d1">Pronto para <em>avançar?</em></h2>
<p class="rv d2 pr-final">Responda ao email em que recebeu esta apresentação com as suas decisões e comentários.</p>
<div class="foot label"><span>© ATC · Angbu Training Centre</span><span>Aprendizagem com propósito</span></div></section>""", privada=True)


@route("GET", "/")
def home(r):
    if not r.user:
        return landing(r)
    if r.user["role"] == "formando" and not selected_presenter(r) and not r.query.get("saltar"):
        raise Redirect("/comecar")  # primeiro acesso: escolher o guia e seguir o percurso de entrada
    courses = r.con.execute("SELECT * FROM courses WHERE active=1 ORDER BY sort, title").fetchall()
    enrolled = {row["course_id"] for row in r.con.execute("SELECT course_id FROM enrolments WHERE user_id=?", (r.user["id"],))}
    mine = [c for c in courses if c["id"] in enrolled and c["status"] == "publicado"]
    others = [c for c in courses if c not in mine]
    profile = learner_profile(r)
    first = profile["display_name"].split()[0] if profile["display_name"] else ""
    mine_html = ("".join(course_card(r, c, True) for c in mine) if mine else
                 ('<p class="muted">Ainda não tem cursos ativos. <a href="/planos">Escolha um plano ou ative um código →</a></p>'
                  if r.user["role"] == "formando" else '<p class="muted">Ainda não está inscrito em nenhum curso.</p>'))
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
        prox = next_step(course_path(r, target))
        url = prox["url"] if prox else f'/cursos/{target["slug"]}'
        if not selected_presenter(r, target["id"]):
            url = f'/cursos/{target["slug"]}/apresentador'
        label = "Continuar a aprender" if p["pct"] or (lesson and r.con.execute("SELECT 1 FROM lesson_progress WHERE user_id=? AND lesson_id=? AND position>0", (r.user["id"], lesson["id"])).fetchone()) else "Começar a aprender"
        if p["complete"]:
            label = "Rever o curso"
        guia_key = selected_presenter(r, target["id"]) or "helena"
        guia_nome = PRESENTERS[guia_key]["name"]
        feature = f'''<section class="featured"><div class="featured-copy"><span class="eyebrow">O SEU PERCURSO · INFORMÁTICA E TECNOLOGIA</span>
<h2>{h(target['title'])}</h2><p>{h(("A seguir: " + prox["titulo"]) if prox else 'Reveja os conteúdos e consulte o seu progresso.')}</p>
<a class="btn" href="{h(url)}">{label} <span aria-hidden="true">↗</span></a><div class="feature-progress"><span>{p['pct']}% concluído</span><span>{p['lessons_done']} de {p['lessons']} aulas</span>{bar(p['pct'])}</div></div>
<div class="featured-art" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="art-window"><div class="window-dots">● ● ●</div><div class="art-guide"><img src="/static/presenters/{guia_key}.png" alt="">{ring_svg(p['pct'], 62, dark=True)}</div><div class="art-meta"><b>Com {"a" if guia_key == "helena" else "o"} {guia_nome}</b><span>{h(prox["titulo"] if prox else "Curso concluído ✓")}</span></div><span class="art-label">O conhecimento abre portas.</span></div><span class="art-badge">ATC / ACADEMIA DIGITAL</span></div></section>'''
    else:
        feature = '<section class="welcome-empty card"><span class="eyebrow">O SEU PERCURSO COMEÇA AQUI</span><h2>Novas competências. Novas possibilidades.</h2><p>Explore a oferta de formação e fale com a ATC para se inscrever.</p><a class="btn" href="#catalogo">Explorar catálogo ↗</a></section>'
    ate = acesso_ate(r.con, r.user["id"])
    access_badge = (f'<a class="learning-badge" href="/planos">● Acesso até {data_pt(ate)}</a>' if ate else
                    '<a class="learning-badge warn" href="/planos">● Acesso terminado · renovar</a>' if acesso_expirado(r.con, r.user["id"]) else
                    '<span class="learning-badge">● Ao seu ritmo. Com a ATC.</span>')
    nxt_step = onboarding_next(r) if r.user["role"] == "formando" else None
    if nxt_step:
        done_n = len(onboarding_done(r))
        profile_hint = (f'<section class="profile-prompt"><div><b>Primeiros passos · {done_n} de {len(ONBOARD)}</b><span>O seu guia acompanha-o em cada passo.</span></div>'
                        f'<a class="btn small" href="/comecar/{nxt_step}">Continuar →</a></section>')
    else:
        profile_hint = ""
    profile_hint = profile_hint or (f'<section class="profile-prompt"><div><b>Bem-vindo à sua academia.</b><span>Personalize o perfil e conte-nos o que gostaria de aprender.</span></div><a class="btn ghost small" href="/conta">Personalizar perfil →</a></section>' if not r.con.execute("SELECT 1 FROM learner_profiles WHERE user_id=?", (r.user["id"],)).fetchone() else (f'<section class="profile-prompt"><div><span class="eyebrow">O SEU OBJETIVO</span><b>{h(profile["goal"])}</b></div><a href="/conta">Editar</a></section>' if profile['goal'] else ''))
    return r.render("Os meus cursos", f'''{profile_hint}<div class="page-heading"><div><span class="eyebrow">A SUA ACADEMIA DIGITAL</span><h1>Olá, {h(first)}<span class="greeting-dot">.</span></h1><p class="muted">É um bom dia para dar o próximo passo.</p></div>{access_badge}</div>
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
    raise Redirect(f"/apresentador?seguinte=/cursos/{slug}/introducao")


def presenter_choice_page(r, slug_unused=None, nxt="/", onboarding=False):
    selected = selected_presenter(r)
    cards = "".join(f'''<label class="presenter-option"><input type="radio" name="presenter" value="{key}" required {"checked" if key == selected else ""}><span class="presenter-portrait"><img src="/static/presenters/{key}.png" alt="{p['name']}, {p['label'].lower()}, com vestuário profissional"><span class="selection-check" aria-hidden="true">✓</span></span><span class="presenter-info"><span class="eyebrow">{p['label']}</span><strong>{p['name']}</strong><span>O seu guia virtual na formação ATC.</span></span></label>''' for key, p in PRESENTERS.items())
    return r.render("Escolher o guia", f'''{steps_bar(r, "guia") if onboarding else ""}<section class="presenter-heading"><span class="eyebrow">UMA FORMAÇÃO À SUA MEDIDA</span><h1>Quem vai acompanhar<br>o seu percurso?</h1><p>Escolha a Helena ou o Miguel. O seu guia vai acompanhá-lo em todos os ecrãs, vídeos e imagens da plataforma. O conteúdo e a avaliação são iguais.<br>Pode mudar a sua escolha a qualquer momento.</p></section><form method="post" action="{"/comecar/guia" if onboarding else "/apresentador"}">{csrf_field(r.csrf)}<input type="hidden" name="seguinte" value="{h(nxt)}"><div class="presenter-options">{cards}</div><div class="presenter-submit"><p class="muted">Personagens virtuais criadas para a ATC.</p><button class="btn">Escolher este guia →</button></div></form>''')


@route("POST", "/cursos/([a-z0-9-]+)/apresentador", "user")
def presenter_save(r, slug):
    c = r.course_for(slug)
    key = r.data.get("presenter", "")
    if key not in PRESENTERS:
        raise HttpError(400, "Escolha um dos apresentadores disponíveis.")
    r.con.execute("""INSERT INTO course_presenters VALUES(?,?,?,?) ON CONFLICT(user_id,course_id)
        DO UPDATE SET presenter=excluded.presenter, updated=excluded.updated""", (r.user["id"], c["id"], key, now()))
    set_presenter(r, key)
    onboarding_mark(r, "guia")
    raise Redirect(f"/cursos/{slug}/introducao")


# ---------------------------------------------------------------------------
# O guia escolhido (Helena ou Miguel) acompanha o formando em toda a plataforma
# ---------------------------------------------------------------------------

PLATAFORMA_DIR = BASE / "plataforma" / "apresentadores"
ONBOARD = [("guia", "Escolha o seu guia")]   # o perfil fica em «A minha conta»; o curso abre logo a seguir
ONBOARD_CLIP = {"boas-vindas": "boas-vindas", "perfil": "perfil", "passeio": "passeio", "curso": "escolher-curso"}


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def clip_html(key, base, name, meta):
    """Vídeo do guia com legendas do próprio leitor (sem legendas gravadas no vídeo) e transcrição."""
    texto = (meta.get("texto") or {}).get(key, "")
    track = f'<track kind="subtitles" srclang="pt" label="Português" src="{base}.vtt" default>'
    transcript = f'<details><summary>Ler o texto</summary><p>{h(texto)}</p></details>' if texto else ""
    return (f'<figure class="guide-clip"><video controls playsinline preload="metadata">'
            f'<source src="{base}.mp4" type="video/mp4">{track}</video><figcaption><span class="eyebrow">{PRESENTERS[key]["name"].upper()} · O SEU GUIA</span>'
            f'<b>{h(meta.get("titulo", ""))}</b>{transcript}</figcaption></figure>')


def platform_clip_html(key, name):
    if key not in PRESENTERS or not (PLATAFORMA_DIR / key / f"{name}.mp4").is_file():
        return ""
    meta = read_json(BASE / "plataforma" / "clips.json").get(name, {})
    return clip_html(key, f"/plataforma/{key}/{name}", name, meta)


def course_flow(slug):
    return read_json(COURSES_DIR / slug / "apresentadores" / "fluxo.json")


def course_clip(slug, key, name):
    if not name or key not in PRESENTERS or not (COURSES_DIR / slug / "apresentadores" / key / f"{name}.mp4").is_file():
        return ""
    meta = read_json(COURSES_DIR / slug / "apresentadores" / "clips.json").get(name, {})
    return clip_html(key, f"/media/{slug}/apresentadores/{key}/{name}", name, meta)


def guide_panel(slug, key, names, title):
    clips = [course_clip(slug, key, n) for n in names if n]
    clips = [c for c in clips if c]
    ordem = ' data-ordem' if len(clips) > 1 else ''
    return f'<section class="guide-panel"><h2>{h(title)}</h2><div class="guide-clips"{ordem}>{"".join(clips)}</div></section>' if clips else ""


@route("GET", r"/plataforma/(helena|miguel)/([a-z0-9-]+\.(?:mp4|vtt))")
def platform_clip(r, key, filename):
    if not r.user and not filename.startswith("boas-vindas."):
        raise Redirect("/entrar?seguinte=" + urllib.parse.quote(r.path))
    r.serve_file(PLATAFORMA_DIR / key / filename, ctype="text/vtt; charset=utf-8" if filename.endswith(".vtt") else "video/mp4")


def onboarding_done(r):
    done = {row["step"] for row in r.con.execute("SELECT step FROM onboarding WHERE user_id=?", (r.user["id"],))}
    if selected_presenter(r):
        done.add("guia")
    return done


def onboarding_mark(r, step):
    r.con.execute("INSERT OR REPLACE INTO onboarding VALUES(?,?,?)", (r.user["id"], step, now()))


def onboarding_next(r):
    done = onboarding_done(r)
    return next((s for s, _ in ONBOARD if s not in done), None)


def steps_bar(r, current):
    done = onboarding_done(r)
    items = "".join(f'<li class="{"done" if s in done else ""}{" current" if s == current else ""}"><span>{i}</span>{h(t)}</li>'
                    for i, (s, t) in enumerate(ONBOARD, 1))
    return f'<ol class="steps-bar" aria-label="Primeiros passos">{items}</ol>'


@route("GET", "/comecar", "user")
def onboarding_start(r):
    nxt = onboarding_next(r)
    raise Redirect(f"/comecar/{nxt}" if nxt else "/")


@route("GET", "/apresentador", "user")
def presenter_change_page(r):
    return presenter_choice_page(r, nxt=safe_next(r.query.get("seguinte"), "/"))


@route("POST", "/apresentador", "user")
def presenter_change_save(r):
    key = r.data.get("presenter", "")
    if key not in PRESENTERS:
        raise HttpError(400, "Escolha um dos guias disponíveis.")
    set_presenter(r, key)
    onboarding_mark(r, "guia")
    raise Redirect(safe_next(r.data.get("seguinte"), "/"))


def first_course_url(r):
    c = r.con.execute("""SELECT c.slug FROM enrolments e JOIN courses c ON c.id=e.course_id
        WHERE e.user_id=? AND c.active=1 ORDER BY c.sort, c.title LIMIT 1""", (r.user["id"],)).fetchone()
    return f'/cursos/{c["slug"]}' if c else "/"


@route("GET", "/comecar/guia", "user")
def onboarding_guide(r):
    """Primeira visita: escolher o guia, ouvi-lo dar as boas-vindas e seguir para o curso. Um só ecrã."""
    selected = selected_presenter(r)
    cards = "".join(f'''<label class="presenter-option"><input type="radio" name="presenter" value="{key}" required {"checked" if key == selected else ""}><span class="presenter-portrait"><img src="/static/presenters/{key}.png" alt="{p['name']}, {p['label'].lower()}"><video class="boas-vindas-video" playsinline preload="none" hidden><source src="/plataforma/{key}/boas-vindas.mp4" type="video/mp4"><track kind="subtitles" srclang="pt" label="Português" src="/plataforma/{key}/boas-vindas.vtt" default></video><span class="selection-check" aria-hidden="true">✓</span></span><span class="presenter-info"><span class="eyebrow">{p['label']}</span><strong>{p['name']}</strong><span>Toque para {"a" if key == "helena" else "o"} ouvir.</span></span></label>''' for key, p in PRESENTERS.items())
    return r.render("Bem-vindo", f'''<section class="presenter-heading boas-vindas"><span class="eyebrow">BEM-VINDO À ATC FORMAÇÃO</span><h1>Quem vai acompanhá-lo?</h1><p>Toque na Helena ou no Miguel para ouvir as boas-vindas. O guia que escolher fala consigo nos vídeos do curso. Pode mudar mais tarde.</p></section><form method="post" action="/comecar/guia" class="primeira-visita">{csrf_field(r.csrf)}<div class="presenter-options">{cards}</div><div class="presenter-submit"><p class="muted">Personagens virtuais criadas para a ATC.</p><button class="btn grande">Começar o meu curso →</button></div></form><script src="/static/boas-vindas.js?v=1" defer></script>''', foco=True)


@route("POST", "/comecar/guia", "user")
def onboarding_guide_save(r):
    key = r.data.get("presenter", "")
    if key not in PRESENTERS:
        raise HttpError(400, "Escolha um dos guias disponíveis.")
    set_presenter(r, key)
    onboarding_mark(r, "guia")
    raise Redirect(first_course_url(r))


def profile_fields(profile):
    colors = "".join(f'<label class="color-choice"><input type="radio" name="color" value="{key}" {"checked" if profile["color"] == key else ""}>'
                     f'<span class="color-swatch avatar-{key}"></span>{label}</label>' for key, label in PROFILE_COLORS.items())
    return (f'<div class="grid2"><label>Nome de apresentação<input name="display_name" maxlength="60" required value="{h(profile["display_name"])}" autocomplete="nickname"></label>'
            f'<label>Profissão ou área de interesse<input name="occupation" maxlength="100" value="{h(profile["occupation"])}"></label></div>'
            f'<label>O que gostaria de aprender?<textarea name="goal" maxlength="300" rows="3" placeholder="O seu objetivo de aprendizagem…">{h(profile["goal"])}</textarea></label>'
            f'<fieldset class="profile-colors"><legend>Cor do perfil</legend>{colors}</fieldset>')


@route("GET", "/comecar/(boas-vindas|perfil|passeio|curso)", "user")
def onboarding_step(r, step):
    raise Redirect("/comecar")


@route("POST", "/comecar/(boas-vindas|perfil|passeio|curso)", "user")
def onboarding_step_done(r, step):
    raise Redirect("/comecar")


def course_path(r, c):
    """Os passos do curso por ordem: introdução, aulas, manual, exemplos e questionário de cada módulo.
    Para o formando, cada passo abre quando o anterior estiver feito; formadores e administradores veem tudo."""
    slug = c["slug"]
    feitos = {row["step"] for row in r.con.execute("SELECT step FROM onboarding WHERE user_id=?", (r.user["id"],))}
    key = selected_presenter(r, c["id"])
    passos = []
    if key and course_flow(slug).get("introducao"):
        nome = PRESENTERS[key]["name"]
        passos.append({"tipo": "intro", "titulo": f'Conheça {"a" if key == "helena" else "o"} {nome}', "sub": "Boas-vindas ao curso · 2 vídeos curtos",
                       "url": f"/cursos/{slug}/introducao", "feito": f"intro:{slug}" in feitos, "modulo": None})
    mods = r.con.execute("SELECT * FROM modules WHERE course_id=? AND active=1 ORDER BY num", (c["id"],)).fetchall()
    lessons = r.con.execute("SELECT * FROM lessons WHERE course_id=? AND active=1 ORDER BY sort", (c["id"],)).fetchall()
    state = lesson_state(r, [l["id"] for l in lessons])
    exemplos = (COURSES_DIR / slug / "manual/exemplos-atc.json").is_file()
    for i, m in enumerate(mods):
        for l in (l for l in lessons if l["module_id"] == m["id"]):
            passos.append({"tipo": "aula", "titulo": l["title"], "sub": f'Vídeo · {fmt_dur(l["duration"])}', "url": f'/cursos/{slug}/aula/{l["slug"]}',
                           "feito": bool(state.get(l["id"]) and state[l["id"]]["completed"]), "modulo": m, "slug": l["slug"]})
        if m["manual_json"]:
            passos.append({"tipo": "manual", "titulo": f'Ler o manual do Módulo {m["num"]}', "sub": "Texto com imagens, passo a passo",
                           "url": f'/cursos/{slug}/modulo/{m["num"]}/manual', "feito": f'manual:{slug}:{m["num"]}' in feitos, "modulo": m})
        if exemplos and i == 0:
            passos.append({"tipo": "exemplos", "titulo": "Ver exemplos práticos", "sub": "Imagens de cada passo no programa",
                           "url": f"/cursos/{slug}/exemplos", "feito": f"exemplos:{slug}" in feitos, "modulo": m})
        quiz = r.con.execute("SELECT * FROM quizzes WHERE module_id=? AND active=1", (m["id"],)).fetchone()
        if quiz:
            best = r.con.execute("SELECT MAX(pct) b, COUNT(*) n FROM quiz_attempts WHERE quiz_id=? AND user_id=?", (quiz["id"], r.user["id"])).fetchone()
            passos.append({"tipo": "quiz", "titulo": quiz["title"],
                           "sub": f'Melhor resultado: {best["b"]}% · aprovação com {quiz["pass_mark"]}%' if best["n"] else f'Aprovação com {quiz["pass_mark"]}%',
                           "url": f'/cursos/{slug}/modulo/{m["num"]}/questionario', "feito": best["b"] is not None and best["b"] >= quiz["pass_mark"], "modulo": m})
    livre = r.is_staff()
    anteriores = True
    for n, p in enumerate(passos, 1):
        p["n"] = n
        p["trancado"] = not livre and not anteriores
        anteriores = anteriores and p["feito"]
    return passos


def next_step(passos):
    return next((p for p in passos if not p["feito"]), None)


PASSO_ICONE = {"intro": "👋", "aula": "▶", "manual": "📖", "exemplos": "🖼", "quiz": "✎"}


def path_html(passos, atual=None):
    prox = next_step(passos)
    itens, modulo = [], None
    for p in passos:
        if p["modulo"] is not None and p["modulo"] is not modulo:
            modulo = p["modulo"]
            itens.append(f'<li class="percurso-modulo">Módulo {modulo["num"]} · {h(modulo["title"])}</li>')
        estado = "feito" if p["feito"] else "trancado" if p["trancado"] else "seguinte" if p is prox else "aberto"
        marca = "✓" if p["feito"] else "🔒" if p["trancado"] else str(p["n"])
        etiqueta = {"feito": "Feito", "trancado": "Abre depois do passo anterior", "seguinte": "A seguir"}.get(estado, "")
        titulo = f'<span class="percurso-titulo">{h(p["titulo"])}</span>' if p["trancado"] else f'<a class="percurso-titulo" href="{h(p["url"])}">{h(p["titulo"])}</a>'
        aqui = ' aria-current="step"' if atual is not None and p["url"] == atual else ""
        itens.append(f'<li class="percurso-passo {estado}"{aqui}><span class="percurso-marca" aria-hidden="true">{marca}</span><span class="percurso-texto">{titulo}'
                     f'<small>{PASSO_ICONE.get(p["tipo"], "")} {h(p["sub"])}</small></span><span class="percurso-estado">{etiqueta}</span></li>')
    return f'<ol class="percurso" aria-label="O seu percurso">{"".join(itens)}</ol>'


def next_step_card(passos, aqui, concluido, texto_espera, texto_pronto="Muito bem! Pode avançar."):
    """O cartão «Próximo passo» no fim de cada página do percurso."""
    i = next((k for k, p in enumerate(passos) if p["url"] == aqui), None)
    seguinte = passos[i + 1] if i is not None and i + 1 < len(passos) else None
    if not seguinte:
        return ('<section class="proximo-passo pronto"><span class="eyebrow">PRÓXIMO PASSO</span><b>Chegou ao fim do percurso deste curso.</b>'
                f'<div class="actions"><a class="btn grande" href="/cursos/{aqui.split("/")[2]}">Ver o curso e o certificado →</a></div></section>') if i is not None else ""
    aberto = concluido or not seguinte["trancado"] or (i is not None and passos[i]["feito"])
    dica = texto_pronto if aberto else texto_espera
    fechado = "" if aberto else ' aria-disabled="true" tabindex="-1"'
    botao = f'<a class="btn grande" data-seguinte href="{h(seguinte["url"])}"{fechado}>{h(seguinte["titulo"])} →</a>'
    return (f'<section class="proximo-passo{" pronto" if aberto else ""}" data-proximo-passo><span class="eyebrow">PRÓXIMO PASSO · {seguinte["n"]} DE {len(passos)}</span>'
            f'<p class="proximo-dica" data-espera="{h(texto_espera)}">{dica}</p><div class="actions">{botao}</div></section>')


def guide_message(slug, key, names):
    """Os vídeos curtos do guia, recolhidos numa mensagem opcional para não ficarem à frente da aula."""
    clips = [x for x in (course_clip(slug, key, n) for n in names if n) if x]
    if not clips or key not in PRESENTERS:
        return ""
    nome = PRESENTERS[key]["name"]
    quantos = "1 vídeo curto" if len(clips) == 1 else f"{len(clips)} vídeos curtos"
    ordem = ' data-ordem' if len(clips) > 1 else ''
    return (f'<details class="guia-msg"><summary><img src="/static/presenters/{key}.png" alt=""><span><b>Mensagem {"da" if key == "helena" else "do"} {nome}</b>'
            f'<small>{quantos} · opcional</small></span></summary><div class="guide-clips"{ordem}>{"".join(clips)}</div></details>')


def som_escolha():
    return ('<div class="som-escolha" role="group" aria-label="Som dos vídeos"><span>Vídeos:</span>'
            '<button type="button" data-som="on" aria-pressed="true">🔊 Com som</button>'
            '<button type="button" data-som="off" aria-pressed="false">💬 Só legendas</button></div>')


def presenter_banner(r, c):
    key = selected_presenter(r, c["id"])
    if not key:
        return f'<section class="profile-prompt"><div><b>Escolha o seu apresentador</b><span>Helena ou Miguel: a formação ao seu ritmo.</span></div><a class="btn small" href="/apresentador?seguinte=/cursos/{h(c["slug"])}">Escolher →</a></section>'
    return f'<section class="presenter-banner"><img src="/static/presenters/{key}.png" alt=""><div><span class="eyebrow">O SEU GUIA VIRTUAL</span><b>{PRESENTERS[key]["name"]}</b></div><a href="/cursos/{h(c["slug"])}/introducao">Introdução</a><a href="/apresentador?seguinte=/cursos/{h(c["slug"])}">Mudar de guia</a></section>'


@route("GET", "/cursos/([a-z0-9-]+)/introducao", "user")
def presenter_intro(r, slug):
    c = r.course_for(slug)
    key = selected_presenter(r, c["id"])
    if not key:
        raise Redirect(f"/apresentador?seguinte=/cursos/{slug}/introducao")
    name = PRESENTERS[key]["name"]
    scripts = json.loads((STATIC / "presenters/scripts.json").read_text(encoding="utf-8"))
    intro = scripts[key]["courses"].get(slug, scripts[key]["welcome"])
    clips = [x for x in (course_clip(slug, key, n) for n in course_flow(slug).get("introducao", [])) if x]
    if clips:
        onboarding_mark(r, f"intro:{slug}")
        passos = course_path(r, c)
        aqui = f"/cursos/{slug}/introducao"
        n = next((p["n"] for p in passos if p["url"] == aqui), 1)
        ordem = ' data-ordem' if len(clips) > 1 else ''
        cartao = next_step_card(passos, aqui, True, "", "Depois dos vídeos, continue para a primeira aula.")
        return r.render(f"Conheça {name}", f'''<p class="crumbs"><a href="/cursos/{slug}">{h(c['title'])}</a> › Passo {n} de {len(passos)}</p><section class="guide-intro"><span class="eyebrow">PASSO {n} DE {len(passos)} · O SEU GUIA</span><h1>Olá, sou {"a" if key == "helena" else "o"} {name}.</h1><p class="lead">Veja os dois vídeos pela ordem: o segundo abre quando o primeiro terminar.</p><div class="guide-clips"{ordem}>{"".join(clips)}</div>{cartao}<p class="muted pequeno"><a href="/apresentador?seguinte=/cursos/{slug}/introducao">Prefere outro guia? Mudar de guia</a></p></section>''')
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
    if not selected_presenter(r, c["id"]) and r.user["role"] == "formando":
        raise Redirect("/comecar")
    passos = course_path(r, c)
    p = course_progress(r.con, r.user["id"], c["id"])
    prox = next_step(passos)
    cert = r.con.execute("SELECT code FROM certificates WHERE user_id=? AND course_id=?", (r.user["id"], c["id"])).fetchone()
    if c["status"] == "amostra":
        cert_html = '<p class="muted">Curso de amostra: inclui o Módulo 1 e não emite certificado.</p>'
    elif cert:
        cert_html = f'<a class="btn" href="/certificado/{h(cert["code"])}">Ver certificado</a>'
    elif p["complete"]:
        cert_html = (f'<form method="post" action="/cursos/{slug}/certificado">{csrf_field(r.csrf)}'
                     f'<button class="btn">Obter certificado</button></form>')
    else:
        cert_html = '<p class="muted">O certificado fica disponível quando concluir todos os passos.</p>'
    if prox:
        cont = f'<a class="btn grande" href="{h(prox["url"])}">{"Continuar" if any(x["feito"] for x in passos) else "Começar"}: {h(prox["titulo"])} →</a>'
        feitos = sum(x["feito"] for x in passos)
        onde = f'<p class="muted">Passo {prox["n"]} de {len(passos)} · {feitos} {"feito" if feitos == 1 else "feitos"}</p>'
    elif passos:
        cont, onde = f'<a class="btn grande" href="{h(passos[0]["url"])}">Rever o curso desde o início →</a>', '<p class="okmsg">✓ Concluiu todos os passos deste curso.</p>'
    else:
        cont, onde = "", ""
    hours = " · ".join(x for x in [f'{fmt_h(c["hours_video"])} h de vídeo' if c["hours_video"] else "",
                                   f'{fmt_h(c["hours_class"])} h presenciais' if c["hours_class"] else ""] if x)
    staff = (f' <a class="btn ghost" href="/admin/relatorio/{slug}">Relatório de turma</a>' if r.is_staff() else "")
    docx = [m for m in r.con.execute("SELECT num, manual_docx FROM modules WHERE course_id=? AND active=1 AND manual_docx IS NOT NULL ORDER BY num", (c["id"],))]
    extras = "".join(f'<a href="/media/{slug}/{h(m["manual_docx"])}?descarregar=1">Descarregar o manual do Módulo {m["num"]} (Word)</a>' for m in docx if m["manual_docx"])
    return r.render(c["title"], f"""<p class="crumbs"><a href="/">Os meus cursos</a></p>
<section class="hero curso-topo"><div><span class="eyebrow">O SEU CURSO</span><h1>{h(c['title'])}</h1><p class="lead">{h(c['subtitle'])}</p>
<div class="actions">{cont}{staff}</div>{onde}</div>
<aside class="card progresso-card"><div class="progresso-topo"><div><h3>O seu progresso</h3><p><b>{p['pct']}%</b>{f" · {p['lessons_done']}/{p['lessons']} aulas" if p['lessons'] else ""}{f" · {p['quizzes_done']}/{p['quizzes']} questionários" if p['quizzes'] else ""}</p></div>{ring_svg(p['pct'], 64)}</div>{bar(p['pct'])}{cert_html}</aside></section>
<section class="card"><h2>O seu percurso</h2><p class="muted">Siga os passos pela ordem. Cada passo abre quando terminar o anterior.</p>{path_html(passos)}</section>
<details class="card sobre-curso"><summary>Sobre este curso</summary><p>{h(c['description'])}</p><p class="muted">{hours}</p><p class="actions">{extras}</p></details>""")


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
        raise Redirect(f"/apresentador?seguinte=/cursos/{slug}/aula/{lslug}")
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
    if lslug in course_flow(slug).get("legendas_na_imagem", []):
        track = ""   # as legendas já estão na imagem do vídeo; uma segunda faixa repetia o texto
    poster = f' poster="/media/{slug}/{h(l["poster"])}"' if l["poster"] else ""
    if medium["key"] != "original" and not l["poster"]:
        poster = f' poster="/static/presenters/{medium["key"]}.png"'
    sub_rel = medium["subtitles"] if medium["key"] != "original" else l["subtitles"]
    sub_file = (COURSES_DIR / slug / sub_rel) if sub_rel else None
    cues = parse_subtitles(sub_file.read_text(encoding="utf-8-sig")) if sub_file and sub_file.is_file() else []
    if cues:
        transcript = "".join(
            f'<button type="button" class="cue" data-start="{ts_seconds(a):.2f}" data-end="{ts_seconds(b):.2f}">'
            f'<span class="cue-time">{fmt_ts(ts_seconds(a))}</span><span class="cue-text">{h(t)}</span></button>'
            for a, b, t in cues if t)
    else:
        transcript_text = l["transcript"] or ""
        transcript = "".join(f"<p>{h(t)}</p>" for t in transcript_text.split("\n") if t)
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
    voz = voz_dados(slug, lslug)
    guia = selected_presenter(r, c["id"]) or "helena"
    if voz:
        nome = PRESENTERS[guia]["name"]
        assistant = f"""<section class="card voz" id="voz" data-lesson="{l['id']}"><div class="voz-topo">
<img src="/static/presenters/{guia}.png" alt=""><div><span class="eyebrow">GUIA POR VOZ</span><h2>Pergunte {"à" if guia == "helena" else "ao"} {nome}</h2>
<p class="muted">Carregue no microfone, faça a pergunta em voz alta e carregue outra vez para enviar.</p></div></div>
<div class="voz-palco"><canvas class="voz-onda" width="220" height="220" aria-hidden="true"></canvas>
<button type="button" class="voz-mic" aria-pressed="false"><span class="voz-icone" aria-hidden="true">🎙</span><span class="voz-rotulo">Falar</span></button></div>
<p class="voz-estado muted" aria-live="polite"></p><ol class="voz-conversa"><li class="voz-resposta voz-saudacao">{h(voz["linhas"]["saudacao"])} <button type="button" class="linkbtn">▶ Ouvir</button></li></ol>
<form class="voz-escrever"><input name="q" maxlength="300" placeholder="Ou escreva a pergunta…" aria-label="Escrever a pergunta"><button class="btn small ghost">Perguntar</button></form></section>"""
    elif ollama_available():
        assistant = f"""<section class="card"><h2>Assistente de estudo</h2>
<p class="muted">Faça uma pergunta sobre esta aula. O assistente responde com base no vídeo e no manual.</p>
<form id="ask"><textarea name="q" rows="2" required placeholder="Ex.: Qual é a diferença entre hardware e software?"></textarea>
<button class="btn small">Perguntar</button></form><div id="answer" class="answer" hidden></div></section>"""
    passos = course_path(r, c)
    aqui = f"/cursos/{slug}/aula/{lslug}"
    n = next((p["n"] for p in passos if p["url"] == aqui), None)
    feita = bool(st and st["completed"])
    cartao = next_step_card(passos, aqui, feita, "Veja a aula até ao fim para abrir o passo seguinte.")
    demo = ""
    amostra = COURSES_DIR / slug / "video/amostra-windows-atc.mp4"
    if slug == "informatica" and lslug == "aula-1-1" and amostra.is_file():
        demo = f"""<section class="card demo"><span class="eyebrow">DEMONSTRAÇÃO · 32 SEGUNDOS</span><h2>Primeiros passos no Windows</h2>
<p class="muted">A Helena e o Miguel mostram quatro ecrãs do Windows 11, com legendas no próprio vídeo. Simulação com imagens editadas.</p>
<div class="player"><video class="aula-video" controls playsinline preload="none" poster="/media/{slug}/video/amostra-windows-atc.png">
<source src="/media/{slug}/video/amostra-windows-atc.mp4" type="video/mp4">O seu navegador não suporta vídeo.</video></div></section>"""
    prev_link = f'<a class="anterior" href="/cursos/{slug}/aula/{h(prev["slug"])}">← Aula anterior: {h(prev["title"])}</a>' if prev else ""
    return r.render(l["title"], f"""<p class="crumbs"><a href="/">Os meus cursos</a> › <a href="/cursos/{slug}">{h(c['title'])}</a>{f" › Passo {n} de {len(passos)}" if n else ""}</p>
<div class="aula-topo"><div><span class="eyebrow">{f"PASSO {n} DE {len(passos)} · " if n else ""}MÓDULO {m['num']}</span><h1>{h(l['title'])}</h1></div><div class="aula-controlos">{som_escolha()}<button type="button" class="cinema-btn" id="cinema-toggle" aria-pressed="false" title="Expandir leitor de vídeo">⤢ Modo cinema</button></div></div>
<div class="player"><video id="v" class="aula-video" controls preload="metadata" playsinline{poster} data-lesson="{l['id']}" data-media="{medium['key']}" data-pos="{pos}" data-seen="{h(seen)}">
<source src="/media/{slug}/{h(medium['video'])}">{track}O seu navegador não suporta vídeo.</video></div>
<p id="status" class="{'okmsg' if feita else 'muted'}">{'✓ Aula concluída' if feita else 'Veja a aula até ao fim para a marcar como concluída.'}</p>
{cartao}{guide_message(slug, selected_presenter(r, c["id"]), course_flow(slug).get("aulas", {}).get(lslug, []))}{demo}
<div class="grid2"><section class="card"><h2>Sobre esta aula</h2><p>{h(l['summary'])}</p>
<details><summary>Ler o texto da aula</summary><div class="transcript">{transcript or '<p class="muted">Sem transcrição.</p>'}</div></details>
<p class="actions">{f'<a class="btn ghost small" href="/cursos/{slug}/modulo/{m["num"]}/manual">Ler o manual do módulo</a>' if m['manual_json'] else ''}</p>{prev_link}</section>
{assistant}</div>
<details class="card" id="perguntas"{" open" if r.is_staff() else ""}><summary><b>Perguntas ao formador</b> <span class="muted">· {len(comments)} {"pergunta" if len(comments) == 1 else "perguntas"}</span></summary><p class="muted">Deixe aqui a sua dúvida. O formador responde nesta página.</p>
<ul class="comments">{thread(None) or '<li class="muted">Ainda não há perguntas sobre esta aula.</li>'}</ul>
<form method="post" action="/cursos/{slug}/aula/{lslug}/comentar">{csrf_field(r.csrf)}
<textarea name="body" rows="3" required placeholder="Escreva a sua pergunta…"></textarea><button class="btn small">Publicar pergunta</button></form></details>
<script src="/static/player.js?v=5"></script>{'<script src="/static/voz.js?v=2"></script>' if voz else ''}""")


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


@route("POST", r"/api/voz/(\d+)", "user")
def voice_api(r, lid):
    """Pergunta por voz (áudio) ou escrita (JSON); o guia escolhido responde com texto e áudio."""
    l = r.con.execute("SELECT l.*, c.slug cslug FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=?", (int(lid),)).fetchone()
    if not l:
        raise HttpError(404)
    c = r.course_for(l["cslug"])
    dados = voz_dados(l["cslug"], l["slug"])
    if not dados:
        raise HttpError(404, "Esta aula ainda não tem guia por voz.")
    presenter = selected_presenter(r, c["id"]) or "helena"
    linha = str(r.data.get("linha", ""))
    hoje = datetime.now().strftime("%Y-%m-%d")
    if linha:   # frases fixas (saudação): geradas uma vez, não contam para o limite
        if linha not in dados["linhas"]:
            raise HttpError(400)
        texto, pergunta, fonte, stt = dados["linhas"][linha], "", "linha", 0
    else:
        usadas = r.con.execute("SELECT COUNT(*) FROM voice_log WHERE user_id=? AND created LIKE ? AND source<>'linha'",
                               (r.user["id"], hoje + "%")).fetchone()[0]
        if usadas >= VOZ_LIMITE_DIA:
            raise HttpError(429, "Atingiu o limite de perguntas por voz de hoje. Escreva a dúvida na secção Perguntas e dúvidas.")
        audio, stt = r.data.get("_audio"), 0
        if audio is not None:
            if len(audio) > 2_000_000:
                raise HttpError(413, "Gravação demasiado longa. Faça uma pergunta mais curta.")
            stt = len(audio)
            try:
                pergunta = voz_transcrever(audio, r.data.get("_audio_type") or "audio/webm")
            except (OSError, ValueError):
                raise HttpError(503, "Não foi possível ouvir a pergunta agora. Tente de novo ou escreva-a.")
        else:
            pergunta = str(r.data.get("q", "")).strip()[:300]
        m = r.con.execute("SELECT * FROM modules WHERE id=?", (l["module_id"],)).fetchone()
        texto, fonte = voz_responder(r.con, l, m, l["cslug"], dados, pergunta)
    try:
        chave, pagos = voz_falar(l["cslug"], presenter, texto)
        audio_url = f"/api/voz/audio/{l['cslug']}/{presenter}/{chave}.mp3"
    except (OSError, ValueError):
        audio_url, pagos = None, 0   # sem rede: a resposta escrita continua a aparecer
    r.con.execute("INSERT INTO voice_log(user_id,lesson_id,presenter,question,source,stt_bytes,tts_chars,created) VALUES(?,?,?,?,?,?,?,?)",
                  (r.user["id"], l["id"], presenter, pergunta[:300], fonte, stt, pagos, now()))
    r.send(200, json.dumps({"pergunta": pergunta, "resposta": texto, "audio": audio_url, "fonte": fonte},
                           ensure_ascii=False), "application/json; charset=utf-8")


@route("GET", r"/api/voz/audio/([a-z0-9-]+)/(helena|miguel)/([0-9a-f]{20})\.mp3", "user")
def voice_audio(r, slug, presenter, chave):
    f = voz_ficheiro(slug, presenter, chave)
    if not f:
        raise HttpError(404)
    r.serve_file(f, ctype="audio/mpeg")


# -- manual online ----------------------------------------------------------

def instruction_examples(slug):
    path = COURSES_DIR / slug / "manual/exemplos-atc.json"
    if not path.is_file():
        raise HttpError(404)
    return json.loads(path.read_text(encoding="utf-8"))


@route("GET", r"/cursos/([a-z0-9-]+)/exemplos", "user")
def examples_page(r, slug):
    c = r.course_for(slug, need_access=False)
    if getattr(r, "con", None) is not None and getattr(r, "user", None):
        onboarding_mark(r, f"exemplos:{slug}")
    data = instruction_examples(slug)
    # Captures can be replaced during review; avoid displaying cached earlier frames.
    for section in data["sections"]:
        for block in section["blocks"]:
            if "figure" in block:
                stamp = (COURSES_DIR / slug / "manual/figures" / block["figure"]).stat().st_mtime_ns
                block["figure"] += f"?v={stamp}"
    cards = "".join(f'<section class="card manual instruction-example"><span class="eyebrow">EXEMPLO ATC · {i:02d}</span>'
                    f'<h2>{h(s["title"])}</h2>{render_blocks(s["blocks"], f"/amostras-office/{slug}")}</section>'
                    for i, s in enumerate(data["sections"], 1))
    return r.render(data["title"], f'''<style>.instruction-example{{margin:24px 0}}.instruction-example figure img{{width:100%;height:auto}}
@media print{{.sidebar,.topbar,.crumbs,.actions{{display:none!important}}main{{margin:0!important;padding:0!important}}.instruction-example{{break-inside:avoid}}}}</style>
<p class="crumbs"><a href="/#catalogo">Catálogo</a> › {h(c['title'])}</p><span class="eyebrow">MANUAL DE AMOSTRA · ATC</span>
<h1>{h(data['title'])}</h1><p class="lead">{h(data['intro'])}</p>{cards}
<p class="muted">Exemplos de formação. O curso completo mantém a disponibilidade indicada no catálogo.</p>''')


@route("GET", r"/amostras-office/([a-z0-9-]+)/([a-z0-9.-]+)", "user")
def example_image(r, slug, filename):
    r.course_for(slug, need_access=False)
    data = instruction_examples(slug)
    allowed = {b["figure"] for s in data["sections"] for b in s["blocks"] if "figure" in b}
    if filename not in allowed:
        raise HttpError(404)
    r.serve_file(COURSES_DIR / slug / "manual/figures" / filename)

def render_blocks(blocks, figbase, presenter=None):
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
            figure = (b.get("variants") or {}).get(presenter) or b["figure"]  # imagem do guia escolhido, se existir
            out.append(f'<figure><img src="{figbase}/{h(figure)}" alt="{h(b.get("caption", ""))}" loading="lazy">'
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
    presenter = selected_presenter(r, c["id"])
    onboarding_mark(r, f"manual:{slug}:{int(num)}")
    parts = []
    for mod in data.get("modules", []):
        toc = "".join(f'<li><a href="#s{i}">{h(s["title"])}</a></li>' for i, s in enumerate(mod.get("sections", [])))
        parts.append(f'<h1>Módulo {mod["num"]} · {h(mod["title"])}</h1><p class="lead">{md(mod.get("intro", ""))}</p>')
        if mod.get("objectives"):
            parts.append('<div class="box obj"><b>Objetivos</b><ul>' +
                         "".join(f"<li>{md(o)}</li>" for o in mod["objectives"]) + "</ul></div>")
        parts.append(f'<nav class="toc"><b>Neste módulo</b><ol>{toc}</ol></nav>')
        for i, s in enumerate(mod.get("sections", [])):
            parts.append(f'<h2 id="s{i}">{h(s["title"])}</h2>{render_blocks(s.get("blocks", []), figbase, presenter)}')
        ex = mod.get("exercise")
        if ex:
            parts.append(f'<div class="box exercise"><h2>{h(ex["title"])}</h2><p class="muted">Duração: {ex.get("minutes", "")} min · '
                         f'Ficheiro: {h(ex.get("file", ""))}</p><ol>' + "".join(f"<li>{md(t)}</li>" for t in ex["tasks"]) + "</ol></div>")
        if mod.get("summary"):
            parts.append("<h2>Resumo</h2><ul>" + "".join(f"<li>{md(s)}</li>" for s in mod["summary"]) + "</ul>")
    if data.get("glossary"):
        parts.append("<h2>Glossário</h2><dl class='gloss'>" +
                     "".join(f"<dt>{h(t)}</dt><dd>{md(d)}</dd>" for t, d in data["glossary"]) + "</dl>")
    foot = f'<a class="btn ghost" href="/media/{slug}/{h(m["manual_docx"])}?descarregar=1">Descarregar em Word</a>' if m["manual_docx"] else ""
    passos = course_path(r, c) if r.user else []
    aqui = f"/cursos/{slug}/modulo/{int(num)}/manual"
    n = next((p["n"] for p in passos if p["url"] == aqui), None)
    cartao = next_step_card(passos, aqui, True, "", "Quando terminar de ler, siga para o passo seguinte.")
    return r.render(f"Manual · Módulo {num}", f"""<p class="crumbs"><a href="/">Os meus cursos</a> › <a href="/cursos/{slug}">{h(c['title'])}</a>{f" › Passo {n} de {len(passos)}" if n else " › Manual"}</p>
{guide_message(slug, presenter, [course_flow(slug).get("manual")])}<article class="card manual">{''.join(parts)}<div class="actions">{foot}</div></article>{cartao}""")


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
    if c["status"] == "amostra":
        raise HttpError(403, "Este é um curso de amostra e não emite certificado.")
    if not course_progress(r.con, r.user["id"], c["id"])["complete"]:
        raise HttpError(403, "Ainda não concluiu todas as aulas e questionários deste curso.")
    code = "ATC-" + secrets.token_hex(4).upper()
    r.con.execute("INSERT INTO certificates VALUES(?,?,?,?)", (code, r.user["id"], c["id"], now()))
    raise Redirect(f"/certificado/{code}")


def cert_matrix_svg(code):
    bits = bin(int(hashlib.sha256(code.encode()).hexdigest(), 16))[2:].zfill(256)
    rects = ['<rect x="0" y="0" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>',
             '<rect x="1.5" y="1.5" width="2" height="2" fill="currentColor"/>',
             '<rect x="8" y="0" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>',
             '<rect x="9.5" y="1.5" width="2" height="2" fill="currentColor"/>',
             '<rect x="0" y="8" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>',
             '<rect x="1.5" y="9.5" width="2" height="2" fill="currentColor"/>']
    idx = 0
    for y in range(13):
        for x in range(13):
            if (x < 6 and y < 6) or (x > 6 and y < 6) or (x < 6 and y > 6):
                continue
            if bits[idx % len(bits)] == "1":
                rects.append(f'<rect x="{x}" y="{y}" width=".92" height=".92" rx=".15" fill="currentColor"/>')
            idx += 1
    return f'<svg class="cert-qr" viewBox="-1 -1 15 15" aria-hidden="true">{"".join(rects)}</svg>'


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
    esquema = "https" if r.headers.get("X-Forwarded-Proto") == "https" else "http"   # atrás do nginx com HTTPS
    verify = f"{esquema}://{r.headers.get('Host', 'localhost')}/verificar?codigo={code}"
    rosette = "".join(f'<ellipse cx="200" cy="200" rx="170" ry="62" transform="rotate({deg} 200 200)" fill="none" stroke="currentColor" stroke-width="0.7"/>' for deg in range(0, 180, 15))
    return f"""<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><title>Certificado {h(code)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/static/atc.css?v=17"></head>
<body class="certbody"><div class="noprint certbar"><a href="/">← Voltar</a> <button onclick="print()" class="btn small">Imprimir / guardar PDF</button></div>
<div class="cert"><div class="certin">
<svg class="cert-guilloche" viewBox="0 0 400 400" aria-hidden="true">{rosette}<circle cx="200" cy="200" r="182" fill="none" stroke="currentColor" stroke-width="0.8" stroke-dasharray="3 3"/></svg>
<span class="cert-corner tl" aria-hidden="true"></span><span class="cert-corner tr" aria-hidden="true"></span><span class="cert-corner bl" aria-hidden="true"></span><span class="cert-corner br" aria-hidden="true"></span>
<img src="/static/logo-600.png" alt="ATC"><p class="k">Certificado de conclusão</p>
<p class="cert-lead">Certifica-se que</p><h1>{h(row['name'])}</h1><p class="cert-lead">concluiu com aproveitamento o curso</p><h2>{h(row['title'])}</h2>
<p class="cert-desc">{f"com a duração de {fmt_h(hours)} horas, " if hours else ""}na plataforma de formação online da ATC – Angbu Training Centre, em Cabinda, Angola.</p>
<div class="certfoot"><div><span>{date}</span><small>Data de emissão</small></div>
<div class="cert-seal-col"><div class="cert-seal" aria-hidden="true"><svg viewBox="0 0 80 80"><circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2"/><circle cx="40" cy="40" r="29" fill="none" stroke="currentColor" stroke-width="1"/><text x="40" y="38" text-anchor="middle" font-size="11" font-weight="700" letter-spacing="2" fill="currentColor">ATC</text><text x="40" y="49" text-anchor="middle" font-size="6.5" letter-spacing="1.4" fill="currentColor">CABINDA</text></svg></div><span>A Direção da ATC</span><small>Angbu Training Centre</small></div>
<div class="cert-verify"><a href="/verificar?codigo={h(code)}" class="cert-qr-wrap" title="Verificar autenticidade">{cert_matrix_svg(code)}<div><span>{h(code)}</span><small>Código · {h(verify)}</small></div></a></div></div></div></div></body></html>"""


@route("GET", "/verificar")
def verify_page(r):
    code = r.query.get("codigo", "").strip().upper()
    res = ""
    if code:
        row = r.con.execute("""SELECT ce.issued, u.name, co.title FROM certificates ce JOIN users u ON u.id=ce.user_id
                               JOIN courses co ON co.id=ce.course_id WHERE ce.code=?""", (code,)).fetchone()
        res = (f'<p class="ok-box">✓ Certificado válido: <b>{h(row["name"])}</b> concluiu <b>{h(row["title"])}</b> em '
               f'{fmt_date(row["issued"])[:10]}.</p>' if row else '<p class="error">Não existe nenhum certificado com este código.</p>')
    res = res.replace('class="ok-box"', 'class="verify-ok"').replace('class="error"', 'class="entry-error"')
    return public_page("Verificar certificado", f"""{public_nav()}
<main class="entry"><section class="entry-show" aria-label="Certificados ATC">
  <span class="label">Certificados ATC</span><h2 class="serif">Cada certificado tem um <em>código único.</em></h2>
  <p class="lead-show">Introduza o código impresso no certificado para confirmar quem o recebeu, o curso e a data de emissão.</p></section>
<section class="entry-form"><div><span class="label">Verificação pública</span><h1 class="serif">Verificar <em>certificado.</em></h1>
  <p class="lead">Não precisa de conta para verificar.</p>{res}
  <form><label class="field"><span class="label">Código do certificado</span><input name="codigo" value="{h(code)}" placeholder="ATC-XXXXXXXX" required autocomplete="off"></label>
  <button class="btn btn-solid">Verificar <span class="arr">→</span></button></form></div></section></main>""")


# ---------------------------------------------------------------------------
# Gestão (formadores e administradores)
# ---------------------------------------------------------------------------

def admin_tabs(active, admin):
    tabs = [("/admin", "Resumo"), ("/admin/utilizadores", "Utilizadores"), ("/admin/perguntas", "Perguntas dos formandos"), ("/admin/pagamentos", "Pagamentos")]
    if admin:
        tabs += [("/admin/codigos", "Códigos de acesso"), ("/admin/cursos", "Cursos")]
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
        demo = (f'<section class="card warnbox"><b>Modo de demonstração ativo.</b> As contas de teste (formando, formador e admin) continuam ativas com as palavras-passe iniciais. '
                f'Antes de abrir aos formandos, altere as palavras-passe e desative este aviso.'
                f'<form method="post" action="/admin/demo-off">{csrf_field(r.csrf)}<button class="btn small">Desativar aviso</button></form></section>')
    ai = ("ligado (" + h(OLLAMA_MODEL) + ")") if ollama_available() else f"desligado (Ollama não encontrado em {h(OLLAMA_URL)} com o modelo {h(OLLAMA_MODEL)})"
    return r.render("Gestão", f"""<h1>Gestão da formação</h1>{admin_tabs('/admin', r.user['role'] == 'admin')}{demo}
<div class="stats"><div><b>{n_users}</b>formandos</div><div><b>{n_active}</b>ativos nos últimos 7 dias</div>
<div><b>{n_certs}</b>certificados emitidos</div><div><a href="/admin/perguntas"><b>{n_open}</b>perguntas por responder</a></div></div>
<section class="card"><h2>Cursos</h2><div class="tablewrap"><table><thead><tr><th>Curso</th><th>Formandos</th><th>Certificados</th><th></th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
{f'<p class="muted">Assistente de estudo local: {"ligado" if ollama_available() else "desligado"}.</p>' if r.user["role"] == "admin" else ""}""")


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
                    f'<a href="/cursos/{q["cs"]}/aula/{q["ls"]}#perguntas">{h(q["lt"])}</a> · {fmt_date(q["created"])} · '
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
<section class="card"><h2>Atualizar cursos</h2><p>Os cursos vivem na pasta <code>cursos/</code> do servidor, uma subpasta por curso com um
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
