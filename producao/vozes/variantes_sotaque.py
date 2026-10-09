#!/usr/bin/env python3
"""Gera variantes de voz-para-voz (ElevenLabs) para os clips com sotaque brasileiro.

Cada clip recebe 3 tentativas (definições e sementes diferentes). Resultados em
producao/videos/avatar-video-variantes/<ID>-<A|B|C>.mp4 (originais intactos).
"""
import pathlib, subprocess, tempfile, sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
ORIGEM = RAIZ / "videos" / "avatar-video"
DESTINO = RAIZ / "videos" / "avatar-video-variantes"
API = "https://api.elevenlabs.io/v1"
VOZES = {"Helena": ("JGnWZj684pcXmK2SxYIv", True), "Miguel": ("FbFkkfp4Iv6U5Q1WC4C2", False)}
# id -> ficheiro (ordem alfabética dentro de cada pasta: H1..H9, M1..M8)
VARIANTES = {
    "A": dict(stability=0.35, similarity_boost=0.75, seed=11),
    "B": dict(stability=0.60, similarity_boost=0.85, seed=22),
    "C": dict(stability=0.85, similarity_boost=0.90, seed=33),
}
ALVOS = sys.argv[1:]

def run(*a, **k): return subprocess.run([str(x) for x in a], check=True, **k)

def clip(cid):
    quem = {"H": "Helena", "M": "Miguel"}[cid[0]]
    return quem, sorted((ORIGEM / quem).glob("*.mp4"))[int(cid[1:]) - 1]

for cid in ALVOS:
    quem, src = clip(cid)
    voz, isolar = VOZES[quem]
    for nome, p in VARIANTES.items():
        dst = DESTINO / f"{cid}-{nome}.mp4"
        if dst.exists(): continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", "44100", t / "o.wav")
            vs = '{"stability":%s,"similarity_boost":%s}' % (p["stability"], p["similarity_boost"])
            run("curl", "-sS", "--fail-with-body", "-o", t / "n.mp3", "-F", f"audio=@{t/'o.wav'}",
                "-F", "model_id=eleven_multilingual_sts_v2", "-F", "remove_background_noise=true",
                "-F", f"seed={p['seed']}", "-F", f"voice_settings={vs}",
                f"{API}/speech-to-speech/{voz}?output_format=mp3_44100_128")
            audio = t / "n.mp3"
            if isolar:
                run("curl", "-sS", "--fail-with-body", "-o", t / "i.mp3", "-F", f"audio=@{audio}", f"{API}/audio-isolation")
                audio = t / "i.mp3"
            run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-i", audio, "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-shortest", dst)
        print("ok", dst.name, flush=True)
