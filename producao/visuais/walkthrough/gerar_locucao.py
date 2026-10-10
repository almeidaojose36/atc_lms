#!/usr/bin/env python3
"""Gera locucao/<id>.mp3 a partir de locucao.json (voz Claudia + isolador de voz da ElevenLabs).
A chave é injetada pelo proxy da rede; não é preciso (nem se deve) colocá-la aqui."""
import json, pathlib, sys, requests
AQUI = pathlib.Path(__file__).resolve().parent
VOZ = "JGnWZj684pcXmK2SxYIv"
API = "https://api.elevenlabs.io/v1"
ids = set(sys.argv[1:])
for s in json.loads((AQUI / "locucao.json").read_text(encoding="utf-8")):
    if not s["texto"] or (ids and s["id"] not in ids): continue
    r = requests.post(f"{API}/text-to-speech/{VOZ}?output_format=mp3_44100_192", timeout=120, json={
        "text": s["texto"], "model_id": "eleven_multilingual_v2", "language_code": "pt",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.15, "speed": 1.05}})
    r.raise_for_status()
    iso = requests.post(f"{API}/audio-isolation", files={"audio": ("v.mp3", r.content, "audio/mpeg")}, timeout=180)
    iso.raise_for_status()
    (AQUI / "locucao" / f"{s['id']}.mp3").write_bytes(iso.content)
    print("ok", s["id"], flush=True)
