#!/usr/bin/env python3
"""Converte a voz dos vídeos dos avatares (ElevenLabs speech-to-speech).

Helena -> Claudia (+ Voice Isolator para retirar eco); Miguel -> Marcos.
Os originais não são alterados: os resultados vão para
producao/videos/avatar-video-novas-vozes/<Apresentador>/.
A chave é injectada pelo ambiente (segredo de rede).
"""
import pathlib, subprocess, tempfile, sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
ORIGEM = RAIZ / "videos" / "avatar-video"
DESTINO = RAIZ / "videos" / "avatar-video-novas-vozes"
VOZES = {"Helena": ("JGnWZj684pcXmK2SxYIv", True), "Miguel": ("FbFkkfp4Iv6U5Q1WC4C2", False)}
API = "https://api.elevenlabs.io/v1"

def run(*a): subprocess.run(a, check=True)

def curl(url, saida, *campos):
    cmd = ["curl", "-sS", "--fail-with-body", "-o", str(saida)]
    for c in campos: cmd += ["-F", c]
    run(*cmd, url)

for nome, (voz, isolar) in VOZES.items():
    for src in sorted((ORIGEM / nome).glob("*.mp4")):
        dst = DESTINO / nome / src.name
        if dst.exists(): continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", "44100", t / "o.wav")
            curl(f"{API}/speech-to-speech/{voz}?output_format=mp3_44100_128", t / "n.mp3",
                 f"audio=@{t/'o.wav'}", "model_id=eleven_multilingual_sts_v2",
                 "remove_background_noise=true",
                 'voice_settings={"stability":0.6,"similarity_boost":0.85}')
            audio = t / "n.mp3"
            if isolar:
                curl(f"{API}/audio-isolation", t / "i.mp3", f"audio=@{audio}")
                audio = t / "i.mp3"
            run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-i", audio, "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k",
                "-shortest", dst)
        print("ok", nome, src.name, flush=True)
