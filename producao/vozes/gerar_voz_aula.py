#!/usr/bin/env python3
"""Pré-gera o áudio do guia por voz (respostas frequentes e frases fixas) para uma aula, nas vozes da Helena e do Miguel.
O áudio fica em cursos/<curso>/voz/audio/<guia>/<chave>.mp3 e vai com o curso: os formandos nunca pagam por estas respostas.
Só gera o que ainda não existe. A chave da ElevenLabs vem do ambiente (ATC_ELEVEN_KEY) ou do proxy da rede.
Uso: python3 producao/vozes/gerar_voz_aula.py informatica aula-1-1
"""
import shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import atc_lms as app

curso, aula = sys.argv[1], sys.argv[2]
dados = app.voz_dados(curso, aula)
destino = app.COURSES_DIR / curso / "voz" / "audio"
textos = list(dados["linhas"].values()) + [p["resposta"] for p in dados["perguntas"]]
total = 0
for guia in app.VOZES:
    for t in textos:
        chave, pagos = app.voz_falar(curso, guia, t, destino=destino)
        total += pagos
        f = destino / guia / f"{chave}.mp3"
        if pagos and shutil.which("ffmpeg"):   # o isolador devolve 320 kbps: reduzir para 128 kbps mono
            tmp = f.with_suffix(".tmp.mp3")
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(f), "-ac", "1", "-b:a", "128k", str(tmp)], check=True)
            tmp.replace(f)
        print(guia, chave, "gerado" if pagos else "já existia", flush=True)
print(f"{total} caracteres gerados")
