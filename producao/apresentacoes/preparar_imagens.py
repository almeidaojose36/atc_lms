#!/usr/bin/env python3
"""Prepara as imagens das apresentações a partir das fotografias dos avatares (producao/visuais/manual-avatares).

- cenas: o apresentador de um lado e espaço de estúdio limpo do outro, para o texto do diapositivo
  (a fotografia é reduzida e o fundo cinzento é prolongado; o lado do texto é clareado ou escurecido)
- avatares redondos (rosto) para as dicas
- figuras SVG animadas dos manuais rasterizadas num momento em que tudo está visível
Uso: python3 preparar_imagens.py   (escreve em _build/)
"""
import glob, json, pathlib
import cv2, numpy as np

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
FOTOS = sorted(f for f in glob.glob(str(RAIZ / "producao/visuais/manual-avatares/*/*")) if f.lower().endswith((".jpg", ".png")))
BUILD = AQUI / "_build"; BUILD.mkdir(exist_ok=True)
NOME = lambda i: pathlib.Path(FOTOS[i]).name

# índice da fotografia → (guia, farda, lado do apresentador)
CENAS = {
    "camisa":  {"helena": {"dir": 28, "esq": 5}, "miguel": {"dir": 36, "esq": 32}},
    "blazer":  {"helena": {"dir": 40, "esq": 31}, "miguel": {"dir": 41, "esq": 34}},
    "polo":    {"helena": {"dir": 37, "esq": 4},  "miguel": {"dir": 38, "esq": 33}},
    "casaco":  {"helena": {"dir": 30, "esq": 26}, "miguel": {"dir": 29, "esq": 27}},
}
RETRATOS = {"camisa": {"helena": 63, "miguel": 67}, "blazer": {"helena": 61, "miguel": 68},
            "polo": {"helena": 62, "miguel": 64}, "casaco": {"helena": 66, "miguel": 59}}
OW, OH = 1920, 1080
CLARO, ESCURO = np.array([246, 244, 242], np.float32), np.array([55, 33, 11], np.float32)   # BGR


def mascara_pessoa(im):
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    bg = cv2.GaussianBlur(cv2.resize(cv2.resize(g, (16, 9), interpolation=cv2.INTER_AREA), (g.shape[1], g.shape[0]),
                                     interpolation=cv2.INTER_CUBIC), (0, 0), 20)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    m = ((np.abs(g - bg) > 28) | (hsv[..., 1] > 60)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    return cv2.dilate(m, np.ones((25, 25), np.uint8))


def placa_limpa(im, m):
    """Fundo de estúdio sem a pessoa (inpainting em baixa resolução e desfocagem)."""
    p = cv2.resize(im, (344, 192), interpolation=cv2.INTER_AREA)
    mp = cv2.resize(m * 255, (344, 192), interpolation=cv2.INTER_NEAREST)
    p = cv2.inpaint(p, mp, 9, cv2.INPAINT_TELEA)
    p = cv2.GaussianBlur(p, (0, 0), 12)
    return cv2.resize(p, (OW, OH), interpolation=cv2.INTER_CUBIC).astype(np.float32)


def cena(i, lado, tom, escala=0.86):
    im = cv2.imread(FOTOS[i]); m = mascara_pessoa(im)
    plate = placa_limpa(im, m)
    big = cv2.resize(im, (OW, OH), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    w, h = int(OW * escala), int(OH * escala)
    small = cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA)
    x0 = OW - w if lado == "dir" else 0; y0 = OH - h
    alfa = np.ones((h, w), np.float32)
    f = 70   # bordas interiores esbatidas para fundir com o fundo prolongado
    ramp = np.linspace(0, 1, f, dtype=np.float32)
    alfa[:f, :] *= ramp[:, None]
    if lado == "dir": alfa[:, :f] *= ramp[None, :]
    else: alfa[:, -f:] *= ramp[::-1][None, :]
    out = plate.copy()
    zona = out[y0:y0 + h, x0:x0 + w]
    out[y0:y0 + h, x0:x0 + w] = zona * (1 - alfa[..., None]) + small * alfa[..., None]
    # clarear/escurecer o lado do texto
    mm = cv2.resize(m, (w, h)); cols = np.where(mm.sum(0) > 6)[0]
    borda = (x0 + cols.min()) / OW if lado == "dir" else (x0 + cols.max()) / OW
    xs = np.linspace(0, 1, OW, dtype=np.float32)
    if lado == "dir":
        t = np.clip((borda - 0.02 - xs) / 0.14, 0, 1)
    else:
        t = np.clip((xs - borda - 0.02) / 0.14, 0, 1)
    forca = 0.55 if tom == "claro" else 0.9
    a = (t * t * (3 - 2 * t) * forca)[None, :, None]
    cor = CLARO if tom == "claro" else ESCURO
    out = out * (1 - a) + cor * a
    return np.clip(out, 0, 255).astype(np.uint8), round(borda, 3)


def avatar_redondo(i, destino, lado=600):
    im = cv2.imread(FOTOS[i])
    cc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    x, y, w, h = max(cc.detectMultiScale(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), 1.1, 6, minSize=(60, 60)), key=lambda r: r[2])
    s = int(w * 2.3); cx, cy = x + w // 2, y + int(h * 0.62)
    x0, y0 = max(0, cx - s // 2), max(0, cy - s // 2); s = min(s, im.shape[1] - x0, im.shape[0] - y0)
    rec = cv2.resize(im[y0:y0 + s, x0:x0 + s], (lado, lado), interpolation=cv2.INTER_AREA)
    a = np.zeros((lado, lado), np.uint8); cv2.circle(a, (lado // 2, lado // 2), lado // 2 - 2, 255, -1, cv2.LINE_AA)
    cv2.imwrite(str(destino), np.dstack([rec, a]))


def svgs():
    from playwright.sync_api import sync_playwright
    alvos = sorted(set(glob.glob(str(RAIZ / "cursos/*/manual/figures/*.svg"))))
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        for f in alvos:
            f = pathlib.Path(f)
            if f.stem.endswith("-original"): continue
            # SVG em linha, com as animações desligadas: fica o desenho estático completo
            svg = f.read_text(encoding="utf-8")
            pg.set_content("<html><head><style>html,body{margin:0}svg{width:1920px;height:1080px;display:block}"
                           "*{animation:none!important;transition:none!important}</style></head><body>" + svg + "</body></html>")
            pg.wait_for_timeout(300)
            d = BUILD / "svg" / f.parent.parent.parent.name; d.mkdir(parents=True, exist_ok=True)
            pg.screenshot(path=str(d / (f.stem + ".png")))
        b.close()


if __name__ == "__main__":
    info = {}
    (BUILD / "cenas").mkdir(exist_ok=True); (BUILD / "avatares").mkdir(exist_ok=True)
    for farda, guias in CENAS.items():
        for guia, lados in guias.items():
            for lado, i in lados.items():
                for tom in ("claro", "escuro"):
                    img, borda = cena(i, lado, tom)
                    nome = f"{farda}-{guia}-{lado}-{tom}.jpg"
                    cv2.imwrite(str(BUILD / "cenas" / nome), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
                    info[nome] = {"borda": borda, "fonte": NOME(i)}
    for farda, guias in RETRATOS.items():
        for guia, i in guias.items():
            avatar_redondo(i, BUILD / "avatares" / f"{farda}-{guia}.png")
    (BUILD / "cenas.json").write_text(json.dumps(info, indent=1, ensure_ascii=False))
    svgs()
    print("ok")
