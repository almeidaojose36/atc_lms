#!/usr/bin/env python3
"""Copia os clips aprovados para as pastas do LMS e gera legendas VTT e transcrições.

Plataforma (todos os cursos): plataforma/apresentadores/<apresentador>/<nome>.mp4
Curso Informática:           cursos/informatica/apresentadores/<apresentador>/<nome>.mp4
As legendas e o texto vêm do áudio final (ElevenLabs Scribe). Escreve também os ficheiros clips.json.
"""
import json, pathlib, re, shutil, subprocess, tempfile

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FINAL = RAIZ / "producao" / "videos" / "avatar-video-final"
API = "https://api.elevenlabs.io/v1"
APRES = {"helena": "H", "miguel": "M"}
# nome -> (clip da Helena, clip do Miguel, título)
PLATAFORMA = {
    "boas-vindas": ("H4", "M5", "Boas-vindas à plataforma"),
    "perfil": ("H5", "M7", "O seu perfil e o seu guia"),
    "passeio": ("H6", "M1", "Como funciona a plataforma"),
    "escolher-curso": ("H1", "M2", "Escolher o primeiro curso"),
}
INFORMATICA = {
    "curso-boas-vindas": ("H7", "M6", "Boas-vindas ao curso"),
    "curso-conteudos": ("H2", "M4", "O que vai aprender"),
    "aula-1-1-abertura": ("H3", "M3", "Abertura da primeira aula"),
    "ver-demonstracao": ("H9", "M8", "Como ver a demonstração"),
    "manual": ("H8", "M9", "O manual do curso"),
}

def transcrever(mp4):
    with tempfile.TemporaryDirectory() as t:
        a = pathlib.Path(t) / "a.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-vn", "-ac", "1", "-b:a", "64k", a], check=True)
        r = subprocess.run(["curl", "-sS", "--fail-with-body", "-F", "model_id=scribe_v1", "-F", f"file=@{a}", f"{API}/speech-to-text"],
                           capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    palavras = [w for w in d["words"] if w["type"] == "word"]
    texto = re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", " ", d["text"])).strip()
    return texto, palavras

def vtt(texto, palavras):
    """Uma legenda por oração (corta em . ? ! , ; :), com os tempos das palavras."""
    partes = [p for p in re.split(r"(?<=[.?!;:])\s+", texto) if p.strip()]
    def tc(s): return f"{int(s//3600):02d}:{int(s%3600//60):02d}:{s%60:06.3f}"
    out, i = ["WEBVTT", ""], 0
    for p in partes:
        n = len(p.split()); w = palavras[i:i + n]; i += n
        if not w: continue
        out += [f"{tc(max(w[0]['start'] - 0.05, 0))} --> {tc(w[-1]['end'] + 0.25)}", p.strip(), ""]
    return "\n".join(out)

def preparar(destino_base, mapa, chave):
    meta = {}
    for nome, (h, m, titulo) in mapa.items():
        meta[nome] = {"titulo": titulo, "texto": {}}
        for apresentador, cid in zip(("helena", "miguel"), (h, m)):
            origem = FINAL / f"{cid}.mp4"
            dst = destino_base / apresentador / f"{nome}.mp4"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, dst)
            texto, palavras = transcrever(origem)
            dst.with_suffix(".vtt").write_text(vtt(texto, palavras), encoding="utf-8")
            meta[nome]["texto"][apresentador] = texto
            print("ok", apresentador, nome, cid, flush=True)
    return meta

if __name__ == "__main__":
    plat = preparar(RAIZ / "plataforma" / "apresentadores", PLATAFORMA, "plataforma")
    (RAIZ / "plataforma" / "clips.json").write_text(json.dumps(plat, ensure_ascii=False, indent=1), encoding="utf-8")
    inf = preparar(RAIZ / "cursos" / "informatica" / "apresentadores", INFORMATICA, "informatica")
    (RAIZ / "cursos" / "informatica" / "apresentadores" / "clips.json").write_text(json.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
