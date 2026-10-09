#!/usr/bin/env python3
"""Gera 3 amostras de voz (ElevenLabs Voice Design) para a Helena ou o Miguel.

Uso: python3 desenhar_vozes_elevenlabs.py helena|miguel
A chave é injectada pelo ambiente (segredo de rede); nunca fica no código.
"""
import base64, json, sys, urllib.request, pathlib

URL = "https://api.elevenlabs.io/v1/text-to-voice/design"
PASTA = pathlib.Path(__file__).parent / "amostras"

DESCRICOES = {
    "helena": (
        "Adult African woman, 28-35, Angolan Portuguese accent (natural and subtle, "
        "not Brazilian, not Portugal-European). Medium to medium-low pitch, clean, warm "
        "and confident, audible smile. Professional, welcoming and patient e-learning "
        "guide for adult learners. Moderate pace around 130 words per minute, crisp "
        "articulation, short pauses between sentences, stable volume, discreet breaths. "
        "Not robotic, not an advertising voice, no exaggerated enthusiasm, no whisper, no hoarseness."
    ),
    "miguel": (
        "Adult African man, 30-38, Angolan Portuguese accent (natural and subtle, "
        "not Brazilian, not Portugal-European). Medium-low pitch, clear, calm and "
        "reassuring, audible smile. Professional, respectful and encouraging e-learning "
        "guide for adult learners, technically confident. Moderate pace around 125 words "
        "per minute, crisp articulation, short pauses between sentences, stable volume, "
        "discreet breaths. Not robotic, not an advertising voice, no exaggerated enthusiasm, no whisper, no hoarseness."
    ),
}
TEXTO = {
    "helena": ("Olá! Sou a Helena, a sua guia virtual da ATC, Angbu Training Centre. "
               "Hoje vamos conhecer o computador e dar os primeiros passos no Windows onze. "
               "Aprenda ao seu ritmo, faça pausas e pratique no seu computador. "
               "Se tiver uma dúvida, deixe-a na área de perguntas para o formador."),
    "miguel": ("Olá! Sou o Miguel, o seu guia virtual da ATC, Angbu Training Centre. "
               "Hoje vamos conhecer o computador e dar os primeiros passos no Windows onze. "
               "Aprenda ao seu ritmo, faça pausas e pratique no seu computador. "
               "Se tiver uma dúvida, deixe-a na área de perguntas para o formador."),
}

nome = sys.argv[1]
body = json.dumps({"voice_description": DESCRICOES[nome], "text": TEXTO[nome],
                   "model_id": "eleven_ttv_v3"}).encode()
req = urllib.request.Request(URL, body, {"Content-Type": "application/json"})
dados = json.load(urllib.request.urlopen(req))
PASTA.mkdir(exist_ok=True)
ids = {}
for i, p in enumerate(dados["previews"], 1):
    f = PASTA / f"{nome}-opcao-{i}.mp3"
    f.write_bytes(base64.b64decode(p["audio_base_64"]))
    ids[f.name] = p["generated_voice_id"]
    print(f.name, p["generated_voice_id"], round(p.get("duration_secs", 0), 1), "s")
(PASTA / f"{nome}-previews.json").write_text(json.dumps(ids, indent=2))
