#!/usr/bin/env python3
"""Vídeo de apresentação do percurso do formando (60–90 s), com locução, zooms nos cliques e capítulos.

1. Locução: locucao/<id>.mp3 (ElevenLabs, voz da Helena), texto em locucao.json.
2. Gravação: uma gravação Playwright por secção (1440x810 com densidade 2, cursor visível, vídeos do LMS sem som).
3. Zoom: cada clique/foco registado gera um zoom suave sobre esse ponto (recorte e escala com OpenCV).
4. Montagem: secções ajustadas à locução, títulos de capítulo, cartão final, áudio normalizado.
Requer o LMS em http://localhost:8080 com o formando demo sem guia escolhido e a pasta WebM dos clips.
Uso: python3 produzir_walkthrough.py <pasta-webm> <saida.mp4>
"""
import json, math, pathlib, re, shutil, subprocess, sys, tempfile, time
import cv2, numpy as np
from playwright.sync_api import sync_playwright

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
sys.path.insert(0, str(AQUI.parent))
from gravar_ecras_lms import CURSOR_JS, CHROME
BASE = "http://localhost:8080"
VW, VH, DSF = 1440, 810, 2            # viewport CSS e densidade (gravação a 2880x1620)
OW, OH, FPS = 1920, 1080, 25           # saída
WEBM = pathlib.Path(sys.argv[1]); SAIDA = pathlib.Path(sys.argv[2])
TMP = pathlib.Path(tempfile.mkdtemp(prefix="walk-"))
SECOES = json.loads((AQUI / "locucao.json").read_text(encoding="utf-8"))

def run(*a, **k): return subprocess.run([str(x) for x in a], check=True, **k)
def dur(f): return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f, capture_output=True, text=True).stdout)

# ---------- gravação ----------
def webm_para(url):
    m = re.search(r"/plataforma/(helena|miguel)/([a-z0-9-]+)\.mp4", url)
    if m: return WEBM / f"plataforma-{m[1]}-{m[2]}.webm"
    m = re.search(r"/media/informatica/apresentadores/(helena|miguel)/([a-z0-9-]+)\.mp4", url)
    if m: return WEBM / f"informatica-{m[1]}-{m[2]}.webm"
    if url.endswith("/media/informatica/video/aula-1-1.mp4"): return WEBM / "informatica-video-aula-1-1.webm"

def interceptar(route):
    alvo = webm_para(route.request.url)
    if alvo and alvo.is_file():
        route.fulfill(status=200, body=alvo.read_bytes(), headers={"Content-Type": "video/webm", "Accept-Ranges": "none"})
    else:
        route.continue_()

INIT_VIDEO = """document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('source[type="video/mp4"]').forEach(s=>s.type='video/webm');
  document.querySelectorAll('video').forEach(v=>{v.muted=true;v.load()});});"""

class Gravador:
    """Movimentos suaves do rato e registo dos pontos a destacar (para o zoom)."""
    def __init__(self, pg, t0):
        self.pg, self.t0, self.x, self.y, self.focos = pg, t0, VW / 2, VH / 2, []
    def t(self): return time.time() - self.t0
    def mover(self, x, y, ms=650):
        n = max(int(ms / 16), 8); x0, y0 = self.x, self.y
        for i in range(1, n + 1):
            p = i / n; e = p * p * (3 - 2 * p)
            self.pg.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e); self.pg.wait_for_timeout(16)
        self.x, self.y = x, y
    def centro(self, sel):
        el = self.pg.locator(sel).first; el.scroll_into_view_if_needed(); b = el.bounding_box()
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    def foco(self, sel=None, xy=None, zoom=1.7, segura=1.2, antes=0.0):
        x, y = xy or self.centro(sel); self.focos.append({"t": self.t() + antes, "x": x, "y": y, "z": zoom, "hold": segura})
    def clicar(self, sel, zoom=1.7, segura=1.0, espera=350):
        x, y = self.centro(sel); self.foco(xy=(x, y), zoom=zoom, segura=segura, antes=0.7)
        self.mover(x, y); self.pg.wait_for_timeout(espera); self.pg.mouse.down(); self.pg.wait_for_timeout(80); self.pg.mouse.up()
    def escrever(self, sel, texto, zoom=1.8):
        self.clicar(sel, zoom=zoom, segura=1.4); self.pg.keyboard.press("Control+A"); self.pg.keyboard.type(texto, delay=22)
    def rolar(self, dy, ms=900):
        n = max(int(ms / 30), 6)
        for i in range(n): self.pg.mouse.wheel(0, dy / n); self.pg.wait_for_timeout(30)
    def tocar(self, i=0):
        self.pg.evaluate("(i)=>{const v=document.querySelectorAll('video')[i]; if(v){v.muted=true; v.play()}}", i)
    def esperar(self, ms): self.pg.wait_for_timeout(ms)
    def ir(self, url): self.pg.goto(BASE + url); self.pg.wait_for_load_state("networkidle"); self.esperar(400)

def s1(g):   # entrada: começa com zoom no logótipo e afasta
    g.ir("/entrar"); g.foco(".login.card img", zoom=2.2, segura=1.6, antes=-1.0); g.esperar(2200)
    g.escrever("input[name=email]", "formando@atc.ao"); g.escrever("input[name=pw]", "formando123")
    g.clicar("form .btn", zoom=1.6); g.pg.wait_for_load_state("networkidle"); g.esperar(1500)

def s2(g):   # guia e perfil
    g.ir("/comecar/guia"); g.esperar(600)
    g.mover(*g.centro(".presenter-option >> nth=0")); g.esperar(500)
    g.clicar(".presenter-option >> nth=1", zoom=1.5, segura=1.3); g.esperar(500)
    g.clicar("form .btn", zoom=1.6); g.pg.wait_for_load_state("networkidle"); g.esperar(500)
    g.tocar(0); g.esperar(1600); g.clicar(".onboard-copy form .btn"); g.pg.wait_for_load_state("networkidle"); g.esperar(400)
    g.tocar(0); g.escrever("textarea[name=goal]", "Usar o computador com confiança no trabalho.")
    g.escrever("input[name=occupation]", "Secretariado"); g.clicar(".profile-editor .btn"); g.pg.wait_for_load_state("networkidle"); g.esperar(900)

def s3(g):   # catálogo e escolha do curso
    g.ir("/comecar/passeio"); g.clicar(".onboard-copy form .btn", zoom=1.4); g.pg.wait_for_load_state("networkidle"); g.esperar(500)
    g.foco(".course-picks", zoom=1.35, segura=4.5); g.mover(*g.centro(".course-pick >> nth=1")); g.esperar(700)
    g.mover(*g.centro(".course-pick >> nth=2")); g.esperar(700); g.rolar(260); g.esperar(800); g.rolar(-260); g.esperar(400)
    g.clicar(".course-pick >> nth=0 >> .btn", zoom=1.6); g.pg.wait_for_load_state("networkidle"); g.esperar(400)
    g.tocar(0); g.foco(".guide-clips", zoom=1.25, segura=2.5); g.esperar(2800)

def s4(g):   # aula e manual
    g.ir("/cursos/informatica/aula/aula-1-1"); g.tocar(0); g.foco(".guide-clips", zoom=1.3, segura=2.4); g.esperar(2600)
    g.rolar(560); g.tocar(2); g.esperar(400); g.foco("#v", zoom=1.3, segura=2.0); g.esperar(2400)
    g.ir("/cursos/informatica/modulo/1/manual"); g.esperar(300)
    g.mover(*g.centro("#s1")); g.rolar(380); g.esperar(300)
    g.foco("figure >> nth=1", zoom=1.45, segura=2.2); g.esperar(2600)

def s5(g):   # progresso e certificado
    g.ir("/"); g.foco(".featured", zoom=1.4, segura=2.6); g.mover(*g.centro(".feature-progress")); g.esperar(2800)
    g.ir("/cursos/informatica"); g.foco("aside.card", zoom=1.7, segura=3.0); g.mover(*g.centro("aside.card")); g.esperar(3400)

ROTEIRO = {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "s5": s5}

def gravar():
    resultado = {}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        estado = None
        for s in SECOES:
            pasta = TMP / s["id"]; pasta.mkdir()
            kw = dict(viewport={"width": VW, "height": VH}, device_scale_factor=DSF,
                      record_video_dir=str(pasta), record_video_size={"width": VW * DSF, "height": VH * DSF})
            if estado: kw["storage_state"] = estado
            ctx = b.new_context(**kw); ctx.add_init_script(CURSOR_JS); ctx.add_init_script(INIT_VIDEO)
            ctx.route(re.compile(r".*\.mp4(\?.*)?$"), interceptar)
            t0 = time.time(); pg = ctx.new_page(); g = Gravador(pg, t0)
            pg.mouse.move(VW / 2, VH / 2)
            ROTEIRO[s["id"]](g)
            estado = ctx.storage_state(); video = pg.video; ctx.close()
            resultado[s["id"]] = (pathlib.Path(video.path()), g.focos)
            print("gravado", s["id"], len(g.focos), "focos", flush=True)
        b.close()
    return resultado

# ---------- zoom ----------
def suave(a, b, x):
    x = min(max((x - a) / (b - a), 0.0), 1.0); return x * x * (3 - 2 * x)

def peso(f, t):
    return suave(f["t"] - 0.55, f["t"], t) * (1 - suave(f["t"] + f["hold"], f["t"] + f["hold"] + 0.6, t))

# fundo animado (azul ATC com luzes suaves em movimento) e janela com sombra
CW, CH, BARRA = 1600, 900, 44
CX0, CY0 = (OW - CW) // 2, (OH - CH - BARRA) // 2
_yy, _xx = np.mgrid[0:270, 0:480].astype(np.float32)
_BASE = (np.dstack([55 + 37 * _xx / 480, 33 + 25 * _yy / 270, 11 + 7 * _yy / 270])).astype(np.float32)   # BGR navy -> azul
_LUZES = [(90, 60, 70, 40, .23, .17, 0.0, 70, (36, 109, 218), .55),     # laranja ATC
          (400, 210, 60, 50, .19, .27, 1.7, 85, (138, 111, 30), .45),   # azul petróleo
          (300, 40, 90, 30, .13, .21, 3.1, 55, (62, 138, 240), .35)]   # laranja claro

def fundo(t):
    img = _BASE.copy()
    for cx0, cy0, ax, ay, fx, fy, ph, r, cor, alfa in _LUZES:
        cx = cx0 + ax * math.sin(fx * t + ph); cy = cy0 + ay * math.cos(fy * t + ph)
        g = (np.exp(-((_xx - cx) ** 2 + (_yy - cy) ** 2) / (2 * r * r)) * alfa)[..., None]
        img = img * (1 - g) + np.array(cor, np.float32) * g
    return cv2.resize(img, (OW, OH), interpolation=cv2.INTER_CUBIC)

def _mascara_arredondada(w, h, r):
    m = np.zeros((h, w), np.uint8); cv2.rectangle(m, (r, 0), (w - r, h), 255, -1); cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)): cv2.circle(m, (cx, cy), r, 255, -1, cv2.LINE_AA)
    return m.astype(np.float32) / 255

MASCARA = _mascara_arredondada(CW, CH + BARRA, 18)[..., None]
_sombra = np.zeros((OH, OW), np.float32); _sombra[CY0 + 22:CY0 + 22 + CH + BARRA, CX0 + 6:CX0 + 6 + CW] = 1
SOMBRA = (cv2.GaussianBlur(_sombra, (0, 0), 28) * 0.55)[..., None]
BARRA_IMG = np.full((BARRA, CW, 3), (245, 241, 238), np.uint8)
for k, cor in enumerate(((88, 95, 255), (46, 189, 254), (64, 201, 40))):
    cv2.circle(BARRA_IMG, (26 + 22 * k, BARRA // 2), 7, cor, -1, cv2.LINE_AA)
cv2.rectangle(BARRA_IMG, (CW // 2 - 220, 10), (CW // 2 + 220, BARRA - 10), (228, 224, 220), -1)
cv2.putText(BARRA_IMG, "atc-formacao.ao", (CW // 2 - 78, BARRA // 2 + 7), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (90, 80, 70), 1, cv2.LINE_AA)

def compor(conteudo, t):
    bg = fundo(t) * (1 - SOMBRA)
    cartao = np.vstack([BARRA_IMG, conteudo]).astype(np.float32)
    zona = bg[CY0:CY0 + CH + BARRA, CX0:CX0 + CW]
    bg[CY0:CY0 + CH + BARRA, CX0:CX0 + CW] = zona * (1 - MASCARA) + cartao * MASCARA
    return np.clip(bg, 0, 255).astype(np.uint8)

def renderizar_zoom(entrada, focos, saida, t_fundo=0.0):
    cfr = TMP / (saida.stem + "-cfr.mp4")
    run("ffmpeg", "-y", "-loglevel", "error", "-i", entrada, "-r", str(FPS), "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", cfr)
    cap = cv2.VideoCapture(str(cfr)); W = int(cap.get(3)); H = int(cap.get(4)); escala = W / VW
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OW}x{OH}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", str(saida)], stdin=subprocess.PIPE)
    i = 0; cx_prev, cy_prev, z_prev = VW / 2, VH / 2, 1.0
    while True:
        ok, fr = cap.read()
        if not ok: break
        t = i / FPS; i += 1
        ws = [(peso(f, t), f) for f in focos]; wmax = max([w for w, _ in ws] + [0])
        if wmax > 1e-3:
            soma = sum(w for w, _ in ws)
            cx = sum(w * f["x"] for w, f in ws) / soma; cy = sum(w * f["y"] for w, f in ws) / soma
            z = 1 + max(w * (f["z"] - 1) for w, f in ws)
            cx = VW / 2 + (cx - VW / 2) * wmax; cy = VH / 2 + (cy - VH / 2) * wmax
        else:
            cx, cy, z = VW / 2, VH / 2, 1.0
        cx_prev += (cx - cx_prev) * 0.35; cy_prev += (cy - cy_prev) * 0.35; z_prev += (z - z_prev) * 0.35
        cw, ch = W / z_prev, H / z_prev
        x0 = min(max(cx_prev * escala - cw / 2, 0), W - cw); y0 = min(max(cy_prev * escala - ch / 2, 0), H - ch)
        M = np.float32([[CW / cw, 0, -x0 * CW / cw], [0, CH / ch, -y0 * CH / ch]])
        conteudo = cv2.warpAffine(fr, M, (CW, CH), flags=cv2.INTER_AREA)
        enc.stdin.write(compor(conteudo, t_fundo + t).tobytes())
    enc.stdin.close(); enc.wait(); cap.release()

# ---------- grafismos ----------
def png_html(html, destino, w, h, transparente=True):
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--allow-file-access-from-files"])
        pg = b.new_page(viewport={"width": w, "height": h}); pg.set_content(html); pg.wait_for_timeout(500)
        alvo = pg.locator("#p") if transparente else pg
        alvo.screenshot(path=str(destino), omit_background=transparente); b.close()

FONTES = f"""@font-face{{font-family:RS;src:url(file://{RAIZ}/static/fonts/RobotoSlab.woff2)}}
@font-face{{font-family:MS;src:url(file://{RAIZ}/static/fonts/Montserrat.woff2)}}"""

def capitulo_png(texto, destino):
    num, titulo = texto.split(" / ", 1)
    png_html(f"""<html><head><style>{FONTES}html,body{{margin:0;background:transparent}}
#p{{position:absolute;display:flex;align-items:stretch;background:rgba(11,33,55,.95);border-radius:12px;overflow:hidden;box-shadow:0 12px 34px rgba(0,0,0,.3)}}
.n{{background:#DA6D24;color:#fff;font:700 40px/1 MS,sans-serif;padding:22px 24px;display:flex;align-items:center}}
.t{{color:#F4F1E6;font:700 40px/1 RS,serif;padding:22px 30px;white-space:nowrap}}</style></head>
<body><div id="p"><div class="n">{num}</div><div class="t">{titulo}</div></div></body></html>""", destino, 1600, 300)

CSS_FUNDO = """html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#0B2137}
.bg{position:absolute;inset:0;background:linear-gradient(120deg,#0B2137,#123A5C 55%,#0B2137);background-size:200% 200%;animation:g 6s ease-in-out infinite alternate}
@keyframes g{to{background-position:100% 50%}}
.luz{position:absolute;border-radius:50%;filter:blur(90px);opacity:.55}
.l1{width:620px;height:620px;background:#DA6D24;left:-120px;top:-160px;animation:m1 7s ease-in-out infinite alternate}
.l2{width:560px;height:560px;background:#1E6F8A;right:-120px;bottom:-180px;animation:m2 8s ease-in-out infinite alternate}
.l3{width:360px;height:360px;background:#F08A3E;right:420px;top:-120px;opacity:.35;animation:m1 9s ease-in-out infinite alternate-reverse}
@keyframes m1{to{transform:translate(160px,120px)}}@keyframes m2{to{transform:translate(-180px,-100px)}}
.c{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:#F4F1E6}
img{width:250px;opacity:0;transform:scale(.6);animation:in .9s cubic-bezier(.2,1.3,.4,1) .25s forwards}
h1{font:700 96px/1.05 RS,serif;margin:30px 0 14px;opacity:0;transform:translateY(30px);animation:up .8s ease-out .8s forwards}
p{font:600 38px/1.3 MS,sans-serif;color:#F08A3E;margin:0;opacity:0;transform:translateY(24px);animation:up .8s ease-out 1.25s forwards}
small{display:block;margin-top:34px;font:500 26px MS,sans-serif;color:#D5DEE6;opacity:0;animation:up .8s ease-out 1.7s forwards}
.risco{width:0;height:6px;background:#DA6D24;border-radius:3px;margin-top:26px;animation:w .9s ease-out 1.5s forwards}
@keyframes in{to{opacity:1;transform:none}}@keyframes up{to{opacity:1;transform:none}}@keyframes w{to{width:220px}}"""

def gravar_cartao(titulo, subtitulo, nota, destino, segundos):
    html = (f"<html><head><style>{FONTES}{CSS_FUNDO}</style></head><body><div class='bg'></div><div class='luz l1'></div><div class='luz l2'></div>"
            f"<div class='luz l3'></div><div class='c'><img src='file://{RAIZ}/static/logo-600.png'><h1>{titulo}</h1><p>{subtitulo}</p>"
            f"<div class='risco'></div><small>{nota}</small></div></body></html>")
    pagina = TMP / f"{destino.stem}.html"; pagina.write_text(html, encoding="utf-8")
    pasta = TMP / f"{destino.stem}-rec"; pasta.mkdir()
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--allow-file-access-from-files"])
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(pasta), record_video_size={"width": 1920, "height": 1080})
        pg = ctx.new_page(); pg.goto(pagina.as_uri()); pg.wait_for_timeout(int(segundos * 1000) + 500)
        v = pg.video; ctx.close(); webm = v.path(); b.close()
    run("ffmpeg", "-y", "-loglevel", "error", "-ss", "0.45", "-i", webm, "-t", f"{segundos:.2f}", "-r", str(FPS),
        "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", destino)

# ---------- montagem ----------
TRANS = 0.7
TIPOS = ["circleopen", "smoothleft", "smoothleft", "smoothup", "smoothleft", "fadeblack"]
MUSICA = AQUI / "musica" / "fundo.mp3"

def main():
    gravacoes = gravar()
    abertura = TMP / "abertura.mp4"
    gravar_cartao("ATC Formação", "O seu percurso de aprendizagem, passo a passo", "Angbu Training Centre · Luanda", abertura, 3.6)
    pecas, vozes = [abertura], []
    for k, s in enumerate(SECOES):
        webm, focos = gravacoes[s["id"]]
        z = TMP / f"{s['id']}-zoom.mp4"; renderizar_zoom(webm, focos, z, t_fundo=k * 17.0)
        vo = AQUI / "locucao" / f"{s['id']}.mp3"; dv = dur(vo); dr = dur(z)
        alvo = min(max(dr, dv + 2.2), dv + 6.0)
        fator = min(dr / alvo, 1.6)
        peca = TMP / f"{s['id']}-final.mp4"
        fc = f"[0:v]setpts=PTS/{fator:.4f},tpad=stop_mode=clone:stop_duration=6,trim=duration={alvo:.3f},setpts=PTS-STARTPTS[v0]"; ultimo = "[v0]"
        entradas = ["-i", z]
        if s["capitulo"]:
            png = TMP / f"{s['id']}-cap.png"; capitulo_png(s["capitulo"], png)
            entradas += ["-loop", "1", "-i", png]
            fc += (f";[1:v]format=rgba,fade=t=in:st=0.6:d=0.35:alpha=1,fade=t=out:st=3.8:d=0.4:alpha=1[c];"
                   f"{ultimo}[c]overlay=x='if(lt(t,1.15),-w+(w+90)*(t-0.6)/0.55,90)':y=H-h-60:enable='between(t,0.6,4.2)':shortest=1[v1]")
            ultimo = "[v1]"
        run("ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", fc, "-map", ultimo, "-t", f"{alvo:.3f}",
            "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), peca)
        pecas.append(peca); vozes.append(vo)
        print(s["id"], f"gravação {dr:.1f}s -> {alvo:.1f}s (x{fator:.2f}), locução {dv:.1f}s", flush=True)
    fim = TMP / "fim.mp4"
    gravar_cartao("Comece hoje a aprender", "ATC Formação", "Aprender hoje. Ir mais longe amanhã.", fim, 4.2)
    pecas.append(fim)
    # transições entre todas as peças
    duracoes = [dur(p) for p in pecas]; inicios = [0.0]
    for d in duracoes[:-1]: inicios.append(inicios[-1] + d - TRANS)
    total = inicios[-1] + duracoes[-1]
    entradas = sum((["-i", p] for p in pecas), []); fc, ultimo = [], "[0:v]"
    for k in range(1, len(pecas)):
        fc.append(f"{ultimo}[{k}:v]xfade=transition={TIPOS[k - 1]}:duration={TRANS}:offset={inicios[k]:.3f}[x{k}]"); ultimo = f"[x{k}]"
    video = TMP / "video.mp4"
    run("ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", ";".join(fc), "-map", ultimo,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", video)
    # locução (começa 0,6 s depois de cada secção) e música por baixo, a baixar quando há voz
    entradas, fc = ["-i", video, "-i", MUSICA], []
    for k, vo in enumerate(vozes):
        t = inicios[k + 1] + 0.6; ms = int(t * 1000); entradas += ["-i", vo]
        fc.append(f"[{k + 2}:a]adelay={ms}|{ms},aformat=channel_layouts=stereo[v{k}]")
    fc.append("".join(f"[v{k}]" for k in range(len(vozes))) + f"amix=inputs={len(vozes)}:normalize=0,apad=whole_dur={total:.2f},asplit=2[voz][chave]")
    fc.append(f"[1:a]atrim=0:{total:.2f},afade=t=in:d=1.2,afade=t=out:st={total - 2.5:.2f}:d=2.5,volume=0.32,aformat=channel_layouts=stereo[mus]")
    fc.append("[mus][chave]sidechaincompress=threshold=0.02:ratio=9:attack=30:release=500[musd]")
    fc.append("[voz][musd]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    run("ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", SAIDA)
    print("ok", SAIDA, f"{total:.1f}s")
    shutil.rmtree(TMP, ignore_errors=True)

if __name__ == "__main__":
    main()
