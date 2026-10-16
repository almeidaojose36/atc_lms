#!/usr/bin/env python3
"""Locução da Helena para os walkthroughs: locucao/<video>/<id>.mp3 a partir de roteiros.json.

Voz ElevenLabs da Helena (Claudia) com o isolador de voz (a voz tem eco). Os ficheiros já gerados são reutilizados;
apague um mp3 para o gerar de novo. A chave vem de ATC_ELEVEN_KEY ou de ~/.config/atc-lms/elevenlabs.env.
Uso: python3 gerar_locucao.py [formando|formador|admin ...]
"""
import json, os, pathlib, subprocess, sys, tempfile, requests

AQUI = pathlib.Path(__file__).resolve().parent
VOZ, API = "JGnWZj684pcXmK2SxYIv", "https://api.elevenlabs.io/v1"
env = pathlib.Path.home() / ".config/atc-lms/elevenlabs.env"
CHAVE = os.environ.get("ATC_ELEVEN_KEY") or next((l.partition("=")[2].strip().strip("\"'") for l in env.read_text().splitlines()
                                                 if l.strip().startswith("ATC_ELEVEN_KEY=")), "") if env.is_file() else os.environ.get("ATC_ELEVEN_KEY", "")
assert CHAVE, "Configure ATC_ELEVEN_KEY."
H = {"xi-api-key": CHAVE}
roteiros = json.loads((AQUI / "roteiros.json").read_text(encoding="utf-8"))
for video in sys.argv[1:] or roteiros:
    pasta = AQUI / "locucao" / video
    pasta.mkdir(parents=True, exist_ok=True)
    for s in roteiros[video]["secoes"]:
        destino = pasta / f"{s['id']}.mp3"
        if not s["texto"] or destino.is_file():
            continue
        r = requests.post(f"{API}/text-to-speech/{VOZ}?output_format=mp3_44100_192", headers=H, timeout=120, json={
            "text": s["texto"], "model_id": "eleven_multilingual_v2", "language_code": "pt",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.15, "speed": 1.05}})
        r.raise_for_status()
        with tempfile.TemporaryDirectory() as t:   # o isolador precisa de pelo menos 4,6 s: falas curtas levam silêncio e voltam a ser cortadas
            bruto, longo, limpo = (pathlib.Path(t) / n for n in ("a.mp3", "b.mp3", "c.mp3"))
            bruto.write_bytes(r.content)
            d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(bruto)]))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(bruto), "-af", "apad=whole_dur=5.5", "-b:a", "192k", str(longo)], check=True)
            iso = requests.post(f"{API}/audio-isolation", headers=H, files={"audio": ("v.mp3", longo.read_bytes(), "audio/mpeg")}, timeout=180)
            iso.raise_for_status()
            limpo.write_bytes(iso.content)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(limpo), "-t", f"{d + 0.15:.2f}", "-b:a", "192k", str(destino)], check=True)
        print("ok", video, s["id"], flush=True)
