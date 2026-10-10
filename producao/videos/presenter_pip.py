#!/usr/bin/env python3
"""Gera um vídeo circular («picture-in-picture») do apresentador a partir de um clip do Flow.

Segue a cara do apresentador ao longo do clip (cascata Haar do OpenCV), recorta à volta
e aplica uma máscara circular com aro branco. Serve para manter o apresentador visível
quando os planos desenhados são substituídos por ecrãs reais do LMS.
Uso: python3 presenter_pip.py <clip.mp4> <pasta-de-saída-png> [tamanho=360]
"""
import pathlib, sys
import cv2, numpy as np

def seguir_cara(video):
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    cascata = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    frames, caras = [], []
    while True:
        ok, f = cap.read()
        if not ok: break
        frames.append(f)
    h, w = frames[0].shape[:2]; esc = 960 / w
    ultimo = None
    for i, f in enumerate(frames):
        if i % 2 == 0:
            g = cv2.cvtColor(cv2.resize(f, None, fx=esc, fy=esc), cv2.COLOR_BGR2GRAY)
            d = cascata.detectMultiScale(g, 1.1, 5, minSize=(28, 28))
            if len(d): ultimo = max(d, key=lambda r: r[2] * r[3]) / esc
        caras.append(None if ultimo is None else np.array(ultimo, float))
    primeiro = next(c for c in caras if c is not None)
    caras = [c if c is not None else primeiro for c in caras]
    # suavização que respeita cortes de plano (saltos grandes não se misturam)
    suav, ref = [], None
    for c in caras:
        if ref is None or np.abs(c[:2] - ref[:2]).max() > 0.12 * w: ref = c.copy()
        else: ref = 0.75 * ref + 0.25 * c
        suav.append(ref.copy())
    return frames, suav, fps

def gerar(video, saida, tam=360):
    saida = pathlib.Path(saida); saida.mkdir(parents=True, exist_ok=True)
    frames, caras, fps = seguir_cara(video)
    h, w = frames[0].shape[:2]
    yy, xx = np.mgrid[0:tam, 0:tam]
    r = np.hypot(xx - tam / 2 + .5, yy - tam / 2 + .5)
    mascara = np.clip((tam / 2 - 7 - r) * 1.0 + .5, 0, 1)      # interior
    aro = np.clip((tam / 2 - 1 - r) + .5, 0, 1) - mascara       # aro branco de 6 px
    for i, (f, (x, y, fw, fh)) in enumerate(zip(frames, caras)):
        lado = float(np.clip(fw * 2.7, 280, 720))
        cx, cy = x + fw / 2, y + fh * 0.62
        x0 = int(np.clip(cx - lado / 2, 0, w - lado)); y0 = int(np.clip(cy - lado / 2, 0, h - lado)); l = int(lado)
        c = cv2.resize(f[y0:y0 + l, x0:x0 + l], (tam, tam), interpolation=cv2.INTER_AREA).astype(float)
        rgba = np.zeros((tam, tam, 4))
        rgba[..., :3] = c * mascara[..., None] + 255 * aro[..., None]
        rgba[..., 3] = (mascara + aro) * 255
        cv2.imwrite(str(saida / f"{i:04d}.png"), rgba.astype(np.uint8))
    return fps, len(frames)

if __name__ == "__main__":
    print(gerar(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 360))
