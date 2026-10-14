"""Locução angolana de uma aula: as falas do guia (uma por legenda) ao ritmo natural, com a imagem ajustada.

As vozes de Helena e Miguel falam mais devagar do que a locução original. Em vez de acelerar as falas,
cada troço do vídeo entre duas legendas é abrandado o necessário para a fala caber, por isso o ecrã
continua sincronizado com o que se ouve. As legendas são re-cronometradas para a nova locução.

Passo 1 (montar):  python3 montar_aula_voz.py montar <video.mp4> <legendas.vtt|srt> <pasta-das-falas> <saida-sem-extensao>
                   → <saida>.video.mp4 (imagem, sem som), <saida>.wav (locução) e <saida>.vtt
Passo 2 (juntar):  python3 montar_aula_voz.py juntar <saida>.video.mp4 <locucao.wav|mp3> <final.mp4>
Entre os dois passos, a locução da Helena passa pelo isolador de voz da ElevenLabs (tem eco).
"""
import json, re, subprocess, sys
from pathlib import Path

PAUSA = 0.25        # silêncio mínimo entre duas falas (s)
MAX_ABRANDAR = 2.5  # um troço de vídeo nunca fica mais de 2,5 vezes mais lento


def tempos(f):
    t = Path(f).read_text(encoding="utf-8-sig")
    cues = re.findall(r"(\d\d:\d\d:\d\d[.,]\d+) --> (\d\d:\d\d:\d\d[.,]\d+)\s*\n(.+?)(?:\n\n|\Z)", t, re.S)
    seg = lambda x: (lambda h, m, s: int(h) * 3600 + int(m) * 60 + float(s))(*x.replace(",", ".").split(":"))
    return [(seg(a), seg(b), " ".join(c.split())) for a, b, c in cues]


def duracao(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))


def vtt_tempo(s):
    h, r = divmod(s, 3600); m, r = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{r:06.3f}"


def montar(video, legendas, pasta, saida):
    cues, total = tempos(legendas), duracao(video)
    falas = sorted(Path(pasta).glob("*.mp3"))
    assert len(falas) == len(cues), (len(falas), len(cues))
    d = [duracao(f) for f in falas]
    orig = [c[0] for c in cues] + [total]
    novo = [orig[0]]
    for i in range(len(cues)):
        alvo = max(novo[i] + (orig[i + 1] - orig[i]), novo[i] + d[i] + PAUSA)       # a fala tem de caber
        alvo = min(alvo, novo[i] + (orig[i + 1] - orig[i]) * MAX_ABRANDAR)
        novo.append(alvo)
    if novo[-1] - novo[-2] < d[-1] + 0.5:
        novo[-1] = novo[-2] + d[-1] + 0.5
    # Imagem: início igual, cada troço [orig_i, orig_i+1] esticado para [novo_i, novo_i+1].
    pontos = [(0.0, orig[0])] + [(orig[i], orig[i + 1]) for i in range(len(cues))]
    filtros, nomes = [], []
    for k, (a, b) in enumerate(pontos):
        fator = 1.0 if k == 0 else (novo[k] - novo[k - 1]) / (b - a)
        filtros.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=(PTS-STARTPTS)*{fator:.5f}[v{k}]")
        nomes.append(f"[v{k}]")
    filtros.append("".join(nomes) + f"concat=n={len(nomes)}:v=1:a=0,fps=30[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-filter_complex", ";".join(filtros), "-map", "[v]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p", "-an", f"{saida}.video.mp4"], check=True)
    # Locução: cada fala ao ritmo natural, no seu novo início.
    entradas = sum((["-i", str(f)] for f in falas), [])
    partes = [f"[{i}]aresample=48000,adelay={int(novo[i] * 1000)}|{int(novo[i] * 1000)}[a{i}]" for i in range(len(falas))]
    mix = "".join(f"[a{i}]" for i in range(len(falas))) + f"amix=inputs={len(falas)}:normalize=0,apad,atrim=0:{novo[-1]:.3f}[out]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", ";".join(partes + [mix]), "-map", "[out]",
                    "-ac", "1", "-ar", "48000", f"{saida}.wav"], check=True)
    # Legendas novas.
    linhas = ["WEBVTT", ""]
    for i, (_, _, txt) in enumerate(cues):
        fim = min(novo[i] + d[i] + 0.2, novo[i + 1] - 0.05)
        linhas += [vtt_tempo(novo[i]) + " --> " + vtt_tempo(fim), txt, ""]
    Path(f"{saida}.vtt").write_text("\n".join(linhas), encoding="utf-8")
    print(json.dumps({"original": round(total, 1), "novo": round(novo[-1], 1), "falas": len(cues)}))


def juntar(video, locucao, final):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(locucao), "-map", "0:v", "-map", "1:a",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", str(final)], check=True)


if __name__ == "__main__":
    {"montar": montar, "juntar": juntar}[sys.argv[1]](*sys.argv[2:])
