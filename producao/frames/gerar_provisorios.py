"""Fotogramas PROVISÓRIOS para a página inicial (até chegarem os vídeos reais).

Gera duas sequências WebP, 1280 px (computador) e 720 px (telemóvel):
  static/frames/aplus/0001.webp …   e   static/frames/aplus/m/0001.webp …   (PC a montar-se)
  static/frames/netplus/0001.webp … e   static/frames/netplus/m/0001.webp … (pacotes pela rede)
Para usar vídeos reais, ver converter.sh nesta pasta.
Uso: python3 producao/frames/gerar_provisorios.py
"""
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
N, W, H, SS = 120, 1280, 720, 2          # fotogramas, tamanho final, supersampling
BG0, BG1 = (10, 30, 50), (13, 40, 66)
ORANGE, ORANGE_L = (240, 138, 62), (255, 200, 150)


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


@lru_cache(None)
def _background():
    im = Image.new("RGB", (W * SS, H * SS), BG0)
    glow = Image.new("RGB", im.size, BG0)
    d = ImageDraw.Draw(glow)
    for r in range(0, 520 * SS, 8 * SS):  # brilho radial suave
        k = 1 - r / (520 * SS)
        c = tuple(int(BG0[i] + (BG1[i] + 18 - BG0[i]) * k * k) for i in range(3))
        d.ellipse([W * SS / 2 - r * 1.6, H * SS * .45 - r, W * SS / 2 + r * 1.6, H * SS * .45 + r], fill=c)
    return glow.filter(ImageFilter.GaussianBlur(40))


def background():
    return _background().copy()


def glow_layer(size, draw_fn, blur):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def save(im, name, i):
    for sub, w in (("", W), ("m/", 720)):
        out = ROOT / f"static/frames/{name}/{sub}{i:04d}.webp"
        out.parent.mkdir(parents=True, exist_ok=True)
        im.resize((w, round(H * w / W)), Image.LANCZOS).save(out, "WEBP", quality=70, method=6)


# --- A+: o computador monta-se --------------------------------------------------
S, OX, OY = 1.25, 240, 35          # escala e deslocação do desenho (viewBox 640×520)
PARTS = [  # (retângulo montado x, y, w, h, cor, contorno, deslocação explodida dx, dy, extra)
    ("cpu", (296, 108, 44, 44), (201, 211, 221), None, (-236, 236)),
    ("ram", (352, 94, 27, 78), (59, 130, 214), (156, 196, 242), (-208, 252)),
    ("placa", (246, 72, 148, 262), (22, 77, 64), (47, 138, 111), (-226, -32)),
    ("ssd", (298, 344, 62, 16), (232, 238, 245), None, (186, -112)),
    ("gpu", (252, 226, 136, 34), (30, 42, 54), ORANGE, (226, -168)),
    ("psu", (246, 384, 148, 70), (44, 57, 70), (95, 116, 135), (230, -6)),
]
DRAW_ORDER = ["placa", "cpu", "ram", "gpu", "ssd", "psu"]


def box(x, y, w, h):
    return [(OX + x * S) * SS, (OY + y * S) * SS, (OX + (x + w) * S) * SS, (OY + (y + h) * S) * SS]


def aplus(t):
    im = background().convert("RGBA")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box(230, 50, 180, 420), radius=18 * S * SS, fill=(15, 44, 72), outline=(70, 95, 120), width=2 * SS)
    pos = {}
    for k, (pid, (x, y, w, h), *_rest) in enumerate(PARTS):
        dx, dy = _rest[2]
        a = ease((t - (0.06 + k * 0.11)) / 0.22)
        bob = (1 - a) * 6 * __import__("math").sin(t * 12 + k)
        pos[pid] = (x + dx * (1 - a), y + dy * (1 - a) + bob, w, h, a)
    for pid in DRAW_ORDER:
        _, _, fill, line, _ = next(p for p in PARTS if p[0] == pid)
        x, y, w, h, a = pos[pid]
        if a < 1:  # brilho laranja enquanto a peça está solta
            im.alpha_composite(glow_layer(im.size, lambda g: g.rounded_rectangle(box(x - 4, y - 4, w + 8, h + 8), radius=10 * SS, fill=ORANGE + (int(90 * (1 - a)),)), 14 * SS))
            d = ImageDraw.Draw(im)
        if pid == "ram":
            for xx in (x, x + 16):
                d.rounded_rectangle(box(xx, y, 11, h), radius=2 * SS, fill=fill, outline=line, width=SS)
            continue
        d.rounded_rectangle(box(x, y, w, h), radius=6 * S * SS, fill=fill, outline=line, width=2 * SS if line else 0)
        if pid == "cpu":
            d.rounded_rectangle(box(x + 10, y + 10, 24, 24), radius=3 * SS, fill=ORANGE)
        if pid in ("gpu", "psu"):
            for cx in ((x + 38, x + 88) if pid == "gpu" else (x + 44,)):
                r = 11 if pid == "gpu" else 22
                cy = y + h / 2
                d.ellipse(box(cx - r, cy - r, 2 * r, 2 * r), fill=(11, 26, 40), outline=(159, 180, 201), width=2 * SS)
        if pid == "placa":
            for yy in (20, 32):
                d.line([((OX + (x + 16) * S) * SS, (OY + (y + yy) * S) * SS), ((OX + (x + 56) * S) * SS, (OY + (y + yy) * S) * SS)], fill=(143, 211, 181), width=2 * SS)
    p = ease((t - 0.86) / 0.12)  # a tampa fecha
    if p > 0:
        off = (1 - p) * 240
        panel = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(panel).rounded_rectangle(box(230 + off, 50, 180, 420), radius=18 * S * SS, fill=(159, 195, 230, int(40 * p)), outline=(255, 255, 255, int(110 * p)), width=2 * SS)
        im.alpha_composite(panel)
    return im.convert("RGB")


# --- N+: pacotes pela rede ------------------------------------------------------
NS, NX, NY = 1.7, 36, 80
NODES = [(70, 250), (215, 250), (355, 165), (505, 105), (640, 215)]
SEGS = [((70, 250), (215, 250), (215, 250), (215, 250)), ((215, 250), (285, 250), (295, 165), (355, 165)),
        ((355, 165), (425, 165), (440, 105), (505, 105)), ((505, 105), (575, 105), (600, 215), (640, 215))]


def bez(p0, p1, p2, p3, u):
    return tuple((1 - u) ** 3 * p0[i] + 3 * (1 - u) ** 2 * u * p1[i] + 3 * (1 - u) * u * u * p2[i] + u ** 3 * p3[i] for i in range(2))


PTS = [bez(*s, j / 60) for s in SEGS for j in range(61)]
P = lambda q: ((NX + q[0] * NS) * SS, (NY + q[1] * NS) * SS)


def netplus(t):
    im = background().convert("RGBA")
    d = ImageDraw.Draw(im)
    for a, b in zip(PTS[::4], PTS[2::4]):  # trilho tracejado
        d.line([P(a), P(b)], fill=(60, 82, 105), width=2 * SS)
    n = int(len(PTS) * ease(t / 0.7))
    if n > 1:
        line = [P(q) for q in PTS[:n]]
        im.alpha_composite(glow_layer(im.size, lambda g: g.line(line, fill=ORANGE + (200,), width=8 * SS, joint="curve"), 10 * SS))
        d = ImageDraw.Draw(im)
        d.line(line, fill=ORANGE, width=4 * SS, joint="curve")
    lit = [k for k, nd in enumerate(NODES) if min(range(len(PTS)), key=lambda j: (PTS[j][0] - nd[0]) ** 2 + (PTS[j][1] - nd[1]) ** 2) < n]
    for k, (x, y) in enumerate(NODES):
        on = k in lit
        if on:
            im.alpha_composite(glow_layer(im.size, lambda g: g.ellipse([P((x - 30, y - 30))[0], P((x - 30, y - 30))[1], P((x + 30, y + 30))[0], P((x + 30, y + 30))[1]], fill=ORANGE + (70,)), 18 * SS))
            d = ImageDraw.Draw(im)
        r = 24
        d.rounded_rectangle([*P((x - r, y - r)), *P((x + r, y + r))], radius=10 * SS, fill=(58, 36, 20) if on else (15, 44, 72), outline=ORANGE if on else (159, 180, 201), width=2 * SS)
    for j in range(4):  # vários pacotes depois do caminho completo
        u = (t * 2.2 - j * 0.28)
        if t < 0.08 or u < 0:
            continue
        idx = int((u % 1) * (len(PTS) - 1)) if t > 0.7 else min(n - 1, int(u * (len(PTS) - 1)))
        if idx < 0 or (t <= 0.7 and j > 0):
            continue
        cx, cy = P(PTS[idx])
        im.alpha_composite(glow_layer(im.size, lambda g: g.ellipse([cx - 22 * SS, cy - 22 * SS, cx + 22 * SS, cy + 22 * SS], fill=ORANGE + (230,)), 12 * SS))
        d = ImageDraw.Draw(im)
        d.ellipse([cx - 9 * SS, cy - 9 * SS, cx + 9 * SS, cy + 9 * SS], fill=ORANGE_L, outline=(255, 255, 255), width=2 * SS)
    return im.convert("RGB")


if __name__ == "__main__":
    for name, fn in (("aplus", aplus), ("netplus", netplus)):
        for i in range(N):
            save(fn(i / (N - 1)), name, i + 1)
        print(name, "ok")
