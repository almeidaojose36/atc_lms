#!/usr/bin/env python3
"""Refaz a voz dos vídeos dos avatares a partir do TEXTO (ElevenLabs TTS).

Motivo: a conversão voz-para-voz (converter_videos.py) copia a pronúncia do áudio
original, que varia de clipe para clipe (por vezes brasileira). O TTS a partir do
texto mantém o sotaque estável. O áudio novo é depois ajustado, oração a oração,
aos tempos da fala original (palavras com marcas de tempo do ElevenLabs Scribe)
para a sincronização labial ficar o mais próxima possível.

Resultados: producao/videos/avatar-video-voz-texto/<Apresentador>/
"""
import json, pathlib, re, subprocess, sys, tempfile

RAIZ = pathlib.Path(__file__).resolve().parents[1]
ORIGEM = RAIZ / "videos" / "avatar-video"
DESTINO = RAIZ / "videos" / "avatar-video-voz-texto"
VOZES = {"Helena": ("JGnWZj684pcXmK2SxYIv", True), "Miguel": ("FbFkkfp4Iv6U5Q1WC4C2", False)}
API = "https://api.elevenlabs.io/v1"
TEMPO_MIN, TEMPO_MAX = 0.75, 1.30   # limites do ajuste de velocidade por oração

def run(*a, **k): return subprocess.run([str(x) for x in a], check=True, **k)

def curl(url, saida=None, *campos, json_body=None):
    cmd = ["curl", "-sS", "--fail-with-body"]
    if saida: cmd += ["-o", str(saida)]
    for c in campos: cmd += ["-F", c]
    if json_body is not None: cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(json_body)]
    return run(*cmd, url, capture_output=saida is None, text=saida is None)

def scribe(ficheiro):
    r = curl(f"{API}/speech-to-text", None, "model_id=scribe_v1", f"file=@{ficheiro}")
    d = json.loads(r.stdout)
    return d["text"], [w for w in d["words"] if w["type"] == "word"]

def oracoes(texto):
    """Lista de contagens de palavras por oração (corta em . ? ! , ; :)."""
    texto = re.sub(r"\[[^\]]*\]", " ", texto)
    partes = [p for p in re.split(r"(?<=[.?!,;:])\s+", texto.strip()) if p.strip()]
    return [len(p.split()) for p in partes], re.sub(r"\s+", " ", texto).strip()

def montar(orig_w, tts_w, contagens, tts_audio, orig_dur, dst_wav):
    filtros, rotulos, i = [], [], 0
    for n, c in enumerate(contagens):
        o = orig_w[i:i + c]; t = tts_w[i:i + c]; i += c
        o0, o1, t0, t1 = o[0]["start"], o[-1]["end"], t[0]["start"], t[-1]["end"]
        r = max(TEMPO_MIN, min(TEMPO_MAX, (t1 - t0) / max(o1 - o0, 0.05)))
        a, b = max(t0 - 0.04, 0), t1 + 0.06
        filtros.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,atempo={r:.4f},"
                       f"adelay={int(o0*1000)}|{int(o0*1000)}[s{n}]")
        rotulos.append(f"[s{n}]")
    filtros.append("".join(rotulos) + f"amix=inputs={len(rotulos)}:normalize=0,apad=whole_dur={orig_dur:.3f}[out]")
    run("ffmpeg", "-y", "-loglevel", "error", "-i", tts_audio, "-filter_complex", ";".join(filtros),
        "-map", "[out]", "-t", f"{orig_dur:.3f}", dst_wav)

def dur(f):
    return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f,
                     capture_output=True, text=True).stdout)

for nome, (voz, isolar) in VOZES.items():
    for src in sorted((ORIGEM / nome).glob("*.mp4")):
        dst = DESTINO / nome / src.name
        if dst.exists(): continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-b:a", "64k", t / "o.mp3")
            texto_o, orig_w = scribe(t / "o.mp3")
            contagens, texto = oracoes(texto_o)
            curl(f"{API}/text-to-speech/{voz}?output_format=mp3_44100_128", t / "t.mp3",
                 json_body={"text": texto, "model_id": "eleven_multilingual_v2", "language_code": "pt"})
            audio = t / "t.mp3"
            if isolar:
                curl(f"{API}/audio-isolation", t / "i.mp3", f"audio={'@'}{audio}")
                audio = t / "i.mp3"
            _, tts_w = scribe(audio)
            if sum(contagens) != len(orig_w) or len(tts_w) != len(orig_w):
                print("AVISO palavras diferentes", nome, src.name, sum(contagens), len(orig_w), len(tts_w), flush=True)
                contagens = [min(len(orig_w), len(tts_w))]
                orig_w, tts_w = orig_w[:contagens[0]], tts_w[:contagens[0]]
            montar(orig_w, tts_w, contagens, audio, dur(src), t / "final.wav")
            run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-i", t / "final.wav", "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k",
                "-shortest", dst)
        print("ok", nome, src.name, flush=True)
