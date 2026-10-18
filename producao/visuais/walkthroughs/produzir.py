#!/usr/bin/env python3
"""Walkthroughs da ATC Formação: formando, formador e administração (1920x1080, locução da Helena).

Cada execução é autónoma: cria uma base de demonstração nova (preparar_dados.py), arranca o LMS numa porta própria,
grava cada secção no Google Chrome com o Playwright (cursor visível, cliques reais), aplica zooms suaves nos pontos
de interesse, junta títulos de capítulo, cartões de abertura e fecho, a locução (locucao/<video>/) e a música.
Requer: Google Chrome instalado, pip install playwright opencv-python-headless numpy, ffmpeg.
Uso: python3 produzir.py <formando|formador|admin> <saida.mp4>
"""
import json, math, os, pathlib, re, shutil, sqlite3, subprocess, sys, tempfile, time
import cv2, numpy as np
from playwright.sync_api import sync_playwright

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
VIDEO, SAIDA = sys.argv[1], pathlib.Path(sys.argv[2]).resolve()
ROTEIRO = json.loads((AQUI / "roteiros.json").read_text(encoding="utf-8"))[VIDEO]
SECOES = ROTEIRO["secoes"]
VW, VH = 1600, 900                   # janela gravada
OW, OH, FPS = 1920, 1080, 25         # saída
PORTA = 8095
BASE = f"http://127.0.0.1:{PORTA}"
TMP = pathlib.Path(tempfile.mkdtemp(prefix=f"walk-{VIDEO}-"))
DADOS = TMP / "dados"
MUSICA = AQUI.parent / "walkthrough" / "musica" / "fundo.mp3"

def run(*a, **k): return subprocess.run([str(x) for x in a], check=True, **k)
def dur(f): return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f, capture_output=True, text=True).stdout)

CURSOR_JS = """(() => {
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;left:0;top:0;width:30px;height:30px;z-index:2147483647;pointer-events:none;';
  c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#fff" stroke="#0B2137" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  const add = () => document.documentElement.appendChild(c);
  (document.documentElement ? add() : document.addEventListener('DOMContentLoaded', add));
  window.addEventListener('mousemove', e => { c.style.transform = `translate(${e.clientX}px,${e.clientY}px)`; }, true);
  window.addEventListener('mousedown', () => { c.style.filter = 'drop-shadow(0 0 10px #DA6D24)'; }, true);
  window.addEventListener('mouseup', () => { c.style.filter = ''; }, true);
})();"""
SEM_SOM = "document.addEventListener('play', e => { e.target.muted = true; }, true);"   # o som dos guias entra na montagem

def ficheiro_local(url):
    """URL de um vídeo do LMS → ficheiro no disco (para usar o áudio do guia na montagem)."""
    p = re.sub(r"^https?://[^/]+", "", url).split("?")[0]
    m = re.match(r"/plataforma/(helena|miguel)/(.+)$", p)
    if m: return RAIZ / "plataforma" / "apresentadores" / m[1] / m[2]
    m = re.match(r"/media/([a-z0-9-]+)/(.+)$", p)
    if m: return RAIZ / "cursos" / m[1] / m[2]
    return None

# ---------- gravação ----------
class Gravador:
    """Movimentos suaves do rato, pontos a destacar (zoom), cortes de espera e momentos em que o guia fala."""
    def __init__(self, pg, t0, dv):
        self.pg, self.t0, self.dv = pg, t0, dv
        self.x, self.y, self.focos, self.falas, self.cortes = VW / 2, VH / 2, [], [], []
    def t(self): return time.time() - self.t0
    def esperar(self, ms): self.pg.wait_for_timeout(ms)
    def mover(self, x, y, ms=750):
        n = max(int(ms / 16), 8); x0, y0 = self.x, self.y
        for i in range(1, n + 1):
            p = i / n; e = p * p * p * (p * (6 * p - 15) + 10)
            self.pg.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e); self.pg.wait_for_timeout(16)
        self.x, self.y = x, y
    def centro(self, sel):
        el = self.pg.locator(sel).first; el.scroll_into_view_if_needed(); b = el.bounding_box()
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    def ir_a(self, sel, ms=750): self.mover(*self.centro(sel), ms=ms)
    def foco(self, sel=None, xy=None, zoom=1.25, segura=1.2, antes=0.0):
        x, y = xy or self.centro(sel); self.focos.append({"t": self.t() + antes, "x": x, "y": y, "z": zoom, "hold": segura})
    def clicar(self, sel, zoom=1.25, segura=0.9, espera=280):
        x, y = self.centro(sel); self.foco(xy=(x, y), zoom=zoom, segura=segura, antes=0.75)
        self.mover(x, y); self.esperar(espera); self.pg.mouse.down(); self.esperar(80); self.pg.mouse.up()
    def pronto(self, t_ini):
        try:
            self.pg.wait_for_function("Array.from(document.querySelectorAll('video[autoplay]')).every(v=>v.readyState>=2)", timeout=15000)
        except Exception:
            pass
        self.esperar(250); self.cortes.append((t_ini, self.t()))
    def submeter(self, sel, zoom=1.2):
        with self.pg.expect_navigation(wait_until="domcontentloaded"): self.clicar(sel, zoom=zoom)
        self.pronto(self.t() - 0.05)
    def escrever(self, sel, texto, zoom=1.25, delay=22):
        self.clicar(sel, zoom=zoom, segura=max(1.0, len(texto) * delay / 1000 + 0.4)); self.pg.keyboard.press("Meta+A")
        self.pg.keyboard.type(texto, delay=delay)
    def rolar(self, dy, ms=900):
        n = max(int(ms / 30), 6)
        for _ in range(n): self.pg.mouse.wheel(0, dy / n); self.pg.wait_for_timeout(30)
    def rolar_ate(self, sel, y_alvo=420, ms=1000):
        b = self.pg.locator(sel).first.bounding_box(); self.rolar(b["y"] + b["height"] / 2 - y_alvo, ms); self.esperar(200)
    def ir(self, url):
        t = self.t(); self.pg.goto(BASE + url, wait_until="domcontentloaded"); self.pronto(t)
    def tocar(self, sel):
        self.pg.evaluate("(s)=>{const v=document.querySelector(s); if(v){v.muted=true; v.play()}}", sel)
    def util(self): return self.t() - sum(b - a for a, b in self.cortes)
    def falar(self, sel, segundos):
        """O guia fala depois da locução: o clip recomeça e o áudio original entra na montagem."""
        while self.util() < self.dv + 0.8: self.esperar(40)
        src = self.pg.evaluate("""(s)=>{const v=document.querySelector(s); v.hidden=false; v.pause(); v.currentTime=0; v.muted=true; v.play();
                                  return v.currentSrc}""", sel)
        self.falas.append({"t": self.t(), "src": src, "dur": segundos})

def db():
    return sqlite3.connect(DADOS / "atc.db")

# --- Formando ---
EMAIL_NOVO = "carla.domingos@exemplo.ao"

def f1(g):   # página inicial: hero e um pouco do percurso A+ com o scroll
    g.ir("/"); g.esperar(600)
    g.foco("h1", zoom=1.15, segura=4.2, antes=0.2); g.mover(VW * 0.33, VH * 0.62, ms=900); g.esperar(3800)
    g.rolar(VH * 0.9, 1400); g.esperar(900); g.rolar(VH * 1.3, 2200); g.esperar(400)
    g.rolar(VH * 0.8, 1600); g.esperar(1200)

def f2(g):   # criar conta
    g.ir("/registar"); g.esperar(400)
    g.escrever("input[name=name]", "Carla Domingos"); g.escrever("input[name=phone]", "923 555 018")
    g.escrever("input[name=email]", EMAIL_NOVO)
    g.clicar("select[name=province]", zoom=1.25); g.pg.select_option("select[name=province]", "Cabinda"); g.esperar(300)
    g.escrever("input[name=pw]", "Formacao2026", delay=30)
    g.submeter(".entry-form .btn", zoom=1.2); g.esperar(300)

def f3(g):   # planos, código de acesso e métodos de pagamento
    g.foco(".plans", zoom=1.12, segura=3.0, antes=0.1)
    for k in range(3): g.ir_a(f".plan >> nth={k}", ms=650); g.esperar(450)
    g.rolar_ate(".code-box", 520, ms=800); g.foco(".code-box", zoom=1.2, segura=1.8); g.esperar(1900)
    g.rolar(-900, 700); g.submeter(".plan.best .btn", zoom=1.25)
    g.foco(".pay-form", zoom=1.12, segura=3.2, antes=0.2)
    for k in (1, 2, 3, 0): g.ir_a(f".pay-opt >> nth={k}", ms=550); g.esperar(320)
    g.submeter(".pay-actions .btn", zoom=1.25)

def f4(g):   # Multicaixa Express: confirmar e acesso ativo
    g.foco(".pay-box", zoom=1.2, segura=2.4, antes=0.2); g.esperar(2200)
    g.submeter(".pay-sim .btn >> nth=0", zoom=1.3)
    g.foco(".pay-status", zoom=1.25, segura=2.8, antes=0.2); g.esperar(2800)

def f5(g):   # escolher o guia; a Helena dá as boas-vindas
    g.ir("/comecar/guia"); g.esperar(400)
    g.foco(".presenter-options", zoom=1.15, segura=4.0, antes=0.2)
    g.ir_a(".presenter-option >> nth=1", ms=900); g.esperar(900)
    g.clicar(".presenter-option >> nth=0", zoom=1.3, segura=6.0)
    g.falar(".presenter-option video", 6.5); g.esperar(6800)
    g.submeter(".presenter-submit .btn", zoom=1.2); g.esperar(400)

def f6(g):   # aula com o vídeo do guia e a demonstração
    g.ir("/cursos/informatica/aula/aula-1-1"); g.esperar(300)
    g.pg.evaluate("(()=>{const v=document.querySelector('#v'); if(v){v.muted=true; v.currentTime=62; v.play()}})()")
    g.foco("#v", zoom=1.15, segura=4.2, antes=0.2); g.ir_a("#v", ms=900); g.esperar(4200)
    g.rolar_ate(".guide-clips", 430, ms=900); g.foco(".guide-clips", zoom=1.2, segura=2.0); g.esperar(2200)

def f7(g):   # dúvida escrita na aula e pergunta em voz
    g.rolar_ate("#voz", 380, ms=1000); g.foco(".voz-mic", zoom=1.35, segura=2.0); g.ir_a(".voz-mic", ms=700); g.esperar(1800)
    g.rolar_ate("#perguntas summary", 420, ms=900); g.clicar("#perguntas summary", zoom=1.3, segura=1.0); g.esperar(400)
    g.escrever("#perguntas > form textarea", "Posso usar o painel tátil do portátil em vez do rato?", zoom=1.3)
    g.submeter("#perguntas > form .btn", zoom=1.25); g.esperar(300)

def f8(g):   # manual ilustrado
    g.ir("/cursos/informatica/modulo/1/manual"); g.esperar(300)
    g.mover(VW * 0.6, VH * 0.55, ms=500)
    figs = g.pg.locator("figure img")
    if figs.count():
        g.rolar_ate("figure img >> nth=0", 430, ms=1600); g.foco("figure img >> nth=0", zoom=1.3, segura=2.6); g.esperar(2800)
    g.rolar(900, 1700); g.esperar(600)

def f9(g):   # questionário certo à primeira e certificado (formanda já com as aulas concluídas)
    g.ir("/cursos/informatica/modulo/1/questionario"); g.esperar(300)
    with db() as con:
        certas = {row[0]: row[1] for row in con.execute("SELECT id, correct FROM questions")}
    nomes = g.pg.evaluate("[...new Set([...document.querySelectorAll('.quiz input[type=radio]')].map(i=>i.name))]")
    for k, nome in enumerate(nomes):
        sel = f"input[name={nome}][value='{certas[int(nome[1:])]}']"
        g.pg.locator(sel).scroll_into_view_if_needed()
        x, y = g.centro(sel); g.mover(x, y, ms=420 if k else 800); g.esperar(90); g.pg.mouse.click(x, y)
        if k == 0: g.foco(xy=(x, y), zoom=1.2, segura=1.2, antes=-0.4)
    g.submeter(".quiz > .btn", zoom=1.2)
    g.foco("main", zoom=1.1, segura=1.6, antes=0.1); g.esperar(1200)
    g.submeter("a.btn:has-text('Obter o certificado')", zoom=1.3)
    g.submeter(f"form[action$='/certificado'] button", zoom=1.3)
    g.foco(".cert", zoom=1.12, segura=3.2, antes=0.2); g.esperar(3400)

# --- Formador ---
def t1(g):
    g.ir("/admin"); g.esperar(300); g.foco(".stats", zoom=1.2, segura=3.2, antes=0.2)
    g.ir_a(".stats > div >> nth=3", ms=900); g.esperar(2400)

def t2(g):
    g.ir("/admin"); g.esperar(200)
    g.submeter(".tabs a:has-text('Perguntas')", zoom=1.2)
    g.foco("main", zoom=1.12, segura=2.6, antes=0.2); g.esperar(1800)
    g.submeter("main a[href*='/aula/'] >> nth=0", zoom=1.3); g.esperar(500)
    g.rolar_ate("#perguntas .comments > li >> nth=0", 360, ms=900)
    g.foco("#perguntas .comments > li >> nth=0", zoom=1.3, segura=1.8); g.esperar(1400)
    g.clicar("details.reply summary >> nth=0", zoom=1.35, segura=1.0); g.esperar(400)
    g.escrever("details.reply textarea >> nth=0", "Boa pergunta! Fica na pasta Ambiente de Trabalho do seu utilizador. Pode vê-la no Explorador de Ficheiros.", zoom=1.3, delay=12)
    g.submeter("details.reply .btn >> nth=0", zoom=1.3); g.esperar(300)
    g.rolar_ate("#perguntas .comments", 380, ms=700); g.foco("#perguntas .comments", zoom=1.25, segura=2.0); g.esperar(1800)

def t3(g):
    g.ir("/admin/relatorio/informatica"); g.esperar(300)
    g.foco("table", zoom=1.12, segura=3.4, antes=0.2); g.mover(VW * 0.45, VH * 0.55, ms=900); g.rolar(260, 1200); g.esperar(1600)
    g.rolar(-400, 700); g.clicar("a:has-text('Exportar')", zoom=1.35, segura=1.6); g.esperar(1400)

def t4(g):
    g.ir("/admin/utilizadores"); g.esperar(300)
    g.rolar_ate("textarea[name=lines]", 460, ms=1300)
    linhas = "Nádia Sebastião;nadia.sebastiao@exemplo.ao;atc2026;informatica\nPaulo Kuanza;paulo.kuanza@exemplo.ao;atc2026;informatica\nMarta Ndongala;marta.ndongala@exemplo.ao;atc2026;informatica"
    g.escrever("textarea[name=lines]", linhas, zoom=1.3, delay=6)
    g.submeter("form[action$='/lote'] .btn", zoom=1.25)
    g.foco("main", zoom=1.1, segura=2.4, antes=0.2); g.esperar(2200)

def t5(g):
    g.ir("/admin/pagamentos"); g.esperar(300)
    g.foco("table", zoom=1.12, segura=2.6, antes=0.2); g.ir_a("tr:has-text('Pagamento na loja')", ms=900); g.esperar(1800)
    g.submeter("tr:has-text('Pagamento na loja') button:has-text('Confirmar')", zoom=1.35)
    g.foco("tr:has-text('Pagamento na loja')", zoom=1.3, segura=2.4, antes=0.2); g.esperar(2400)

# --- Administração ---
def a1(g):
    g.ir("/admin"); g.esperar(300); g.foco(".tabs", zoom=1.25, segura=2.6, antes=0.2)
    g.ir_a(".tabs a >> nth=5", ms=1100); g.esperar(800); g.ir_a(".stats", ms=800); g.esperar(1500)

def a2(g):
    g.ir("/admin"); g.esperar(200)
    g.submeter(".tabs a:has-text('Utilizadores')", zoom=1.2)
    g.foco("table", zoom=1.12, segura=2.2, antes=0.2); g.esperar(1600)
    g.submeter("a:has-text('Joana Mbala')", zoom=1.3)
    g.foco("main", zoom=1.12, segura=3.6, antes=0.2); g.ir_a("select[name=role]", ms=900); g.esperar(1400)
    g.ir_a("input[type=checkbox]", ms=700); g.esperar(1200)

def a3(g):
    g.ir("/admin/pagamentos"); g.esperar(300)
    g.foco("table", zoom=1.12, segura=3.0, antes=0.2); g.ir_a("tr:has-text('Transferência')", ms=900); g.esperar(1200)
    g.submeter("tr:has-text('Transferência') a:has-text('Ver comprovativo')", zoom=1.35)
    g.foco(xy=(VW / 2, VH * 0.45), zoom=1.35, segura=2.8, antes=0.1); g.esperar(2800)
    t = g.t(); g.pg.go_back(wait_until="domcontentloaded"); g.pronto(t)
    g.submeter("tr:has-text('Transferência') button:has-text('Confirmar')", zoom=1.35)
    g.foco("tr:has-text('Transferência')", zoom=1.3, segura=2.2, antes=0.2); g.esperar(2200)

def a4(g):
    g.ir("/admin/codigos"); g.esperar(300)
    g.escrever("input[name=label]", "Internet Angbu — novembro", zoom=1.3)
    g.clicar("select[name=plan_id]", zoom=1.3); g.pg.select_option("select[name=plan_id]", index=1); g.esperar(300)
    g.escrever("input[name=n]", "200", zoom=1.3)
    g.submeter(".code-gen .btn", zoom=1.3)
    g.foco("table", zoom=1.2, segura=2.6, antes=0.2); g.ir_a("a:has-text('Descarregar CSV') >> nth=0", ms=900); g.esperar(2200)

def a5(g):
    g.ir("/admin/cursos"); g.esperar(300); g.foco("table", zoom=1.15, segura=3.0, antes=0.2)
    g.mover(VW * 0.62, VH * 0.4, ms=900); g.esperar(2200)
    with db() as con:
        code = con.execute("SELECT code FROM certificates ORDER BY issued LIMIT 1").fetchone()[0]
    g.ir("/verificar"); g.esperar(300)
    g.escrever("input[name=codigo]", code, zoom=1.3)
    g.submeter(".entry-form .btn", zoom=1.25)
    g.foco(xy=(VW * 0.56, VH * 0.5), zoom=1.08, segura=3.2, antes=0.2); g.ir_a(".verify-ok", ms=700); g.esperar(3000)

# --- Galeria 3D ---
def g_carregar(g, slug=None):
    t = g.t()
    if slug: g.pg.evaluate("(s)=>{location.hash=s}", slug)
    g.esperar(150)
    g.pg.wait_for_function("document.getElementById('g-carregar').hidden && document.querySelectorAll('.g-marca').length>0", timeout=60000)
    g.esperar(200); g.cortes.append((t, g.t()))

def g_parar(g):   # pára a rotação automática para os números ficarem quietos
    g.pg.evaluate("()=>{const b=document.getElementById('g-rodar'); if(b.getAttribute('aria-pressed')==='true') b.click()}"); g.esperar(900)

def g1(g):
    g.ir("/galeria#placa-mae"); g_carregar(g)
    g.foco(".g-palco", zoom=1.12, segura=4.0, antes=0.2); g.mover(VW * 0.4, VH * 0.55, ms=1200); g.esperar(4200)

def g2(g):
    g.clicar(".g-aba[data-slug='placa-grafica'], .g-aba[data-slug='cooler']", zoom=1.2, segura=0.8); g_carregar(g)
    x, y = g.centro("#g-canvas")
    g.foco(xy=(x, y), zoom=1.15, segura=5.0, antes=0.1)
    g.mover(x - 120, y, ms=600); g.pg.mouse.down()
    for k in range(60): g.pg.mouse.move(x - 120 + k * 6, y + (k % 30) * 0.8); g.esperar(22)
    g.pg.mouse.up(); g.x, g.y = x + 240, y; g.esperar(300)
    g.mover(x, y, ms=500)
    for _ in range(8): g.pg.mouse.wheel(0, -120); g.esperar(70)
    g.esperar(1200)
    for _ in range(8): g.pg.mouse.wheel(0, 120); g.esperar(70)
    g.esperar(600)

def g3(g):
    g.clicar(".g-aba[data-slug='placa-mae']", zoom=1.2, segura=0.8); g_carregar(g); g.esperar(800); g_parar(g)
    g.clicar(".g-marca >> nth=0", zoom=1.35, segura=1.4); g.esperar(1400)
    g.foco(".g-info", zoom=1.3, segura=2.4, antes=0.1); g.esperar(2200)
    g.clicar("#g-seg", zoom=1.35, segura=1.6); g.esperar(1800)
    g.clicar("#g-seg", zoom=1.35, segura=1.6); g.esperar(1800)

def g4(g):
    for slug in ("teclado", "rato", "monitor", "auscultadores"):
        g.clicar(f".g-aba[data-slug='{slug}']", zoom=1.18, segura=0.7); g_carregar(g)
        g.foco(".g-palco", zoom=1.1, segura=1.6, antes=0.1); g.esperar(1500)

def g5(g):
    g.clicar(".g-aba[data-slug='caixa']", zoom=1.2, segura=0.7); g_carregar(g)
    g.clicar("#g-ecra", zoom=1.3, segura=0.9); g.esperar(1200); g_parar(g)
    g.clicar(".g-marca >> nth=1", zoom=1.2, segura=1.2); g.esperar(2600)
    g.clicar(".g-marca >> nth=0", zoom=1.2, segura=1.2); g.esperar(2400)
    g.pg.keyboard.press("Escape"); g.esperar(400)

def g6(g):
    g.ir("/cursos/informatica/aula/aula-1-1")
    if "/apresentador" in g.pg.url:          # escolhe a Helena fora de cena (o carregamento é cortado)
        t = g.t(); g.pg.check("input[name=presenter][value=helena]")
        with g.pg.expect_navigation(wait_until="domcontentloaded"): g.pg.click(".presenter-submit .btn")
        g.pronto(t)
    g.esperar(400)
    g.rolar_ate("a:has-text('Ver em 3D')", 430, ms=1100)
    g.foco("a:has-text('Ver em 3D')", zoom=1.35, segura=1.8, antes=0.1); g.esperar(1600)
    with g.pg.expect_navigation(wait_until="domcontentloaded"): g.clicar("a:has-text('Ver em 3D')", zoom=1.35)
    g_carregar(g); g.foco(".g-palco", zoom=1.1, segura=2.2, antes=0.1); g.esperar(2400)

PLANO = {
    "formando": {"f1": (None, f1), "f2": (None, f2), "f3": ("seguir", f3), "f4": ("seguir", f4), "f5": ("seguir", f5),
                 "f6": ("seguir", f6), "f7": ("seguir", f7), "f8": ("seguir", f8), "f9": (("joana.mbala@exemplo.ao", "demo-formando-2026"), f9)},
    "formador": {k: (("formador@atc.ao", "formador123") if k == "t1" else "seguir", f) for k, f in
                 {"t1": t1, "t2": t2, "t3": t3, "t4": t4, "t5": t5}.items()},
    "admin": {k: (("admin@atc.ao", "admin123") if k == "a1" else "seguir", f) for k, f in
              {"a1": a1, "a2": a2, "a3": a3, "a4": a4, "a5": a5}.items()},
    "galeria": {k: (("formando@atc.ao", "formando123") if k == "g1" else "seguir", f) for k, f in
                {"g1": g1, "g2": g2, "g3": g3, "g4": g4, "g5": g5, "g6": g6}.items()},
}[VIDEO]

def sessao(b, email, pw):
    ctx = b.new_context(viewport={"width": VW, "height": VH}); pg = ctx.new_page()
    pg.goto(BASE + "/entrar"); pg.fill("input[name=email]", email); pg.fill("input[name=pw]", pw)
    with pg.expect_navigation(): pg.click(".entry-form .btn")
    estado = ctx.storage_state(); ctx.close(); return estado

def gravar():
    resultado = {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required", "--hide-scrollbars", f"--window-size={VW},{VH}"])
        estado, ultimo = None, None
        for s in SECOES:
            if s["id"] not in PLANO: continue
            quem, fn = PLANO[s["id"]]
            if isinstance(quem, tuple): estado = sessao(b, *quem)
            elif quem is None and s["id"] == "f1": estado = None
            pasta = TMP / s["id"]; pasta.mkdir()
            kw = dict(viewport={"width": VW, "height": VH}, record_video_dir=str(pasta), record_video_size={"width": VW, "height": VH})
            if estado and quem is not None: kw["storage_state"] = estado
            ctx = b.new_context(**kw); ctx.add_init_script(CURSOR_JS); ctx.add_init_script(SEM_SOM)
            vo = AQUI / "locucao" / VIDEO / f"{s['id']}.mp3"
            t0 = time.time(); pg = ctx.new_page(); g = Gravador(pg, t0, dur(vo) if vo.is_file() else 0.0)
            if quem == "seguir" and ultimo:      # continua onde a secção anterior terminou; o carregamento é cortado
                pg.goto(ultimo, wait_until="domcontentloaded"); g.pronto(0.0)
            pg.mouse.move(VW / 2, VH / 2)
            fn(g)
            while g.util() < g.dv + 1.3: g.esperar(50)     # a gravação cobre sempre a locução (nunca se abranda o vídeo)
            ultimo = pg.url
            estado = ctx.storage_state(); video = pg.video; ctx.close()
            resultado[s["id"]] = (pathlib.Path(video.path()), g.focos, g.falas, g.cortes)
            print("gravado", s["id"], f"{len(g.focos)} focos", flush=True)
        b.close()
    return resultado

# ---------- zoom e composição ----------
def suave(a, b, x):
    x = min(max((x - a) / (b - a), 0.0), 1.0); return x * x * (3 - 2 * x)

def peso(f, t):
    return suave(f["t"] - 0.55, f["t"], t) * (1 - suave(f["t"] + f["hold"], f["t"] + f["hold"] + 0.6, t))

CW, CH, BARRA = 1600, 900, 44
CX0, CY0 = (OW - CW) // 2, (OH - CH - BARRA) // 2
_yy, _xx = np.mgrid[0:270, 0:480].astype(np.float32)
_BASE = (np.dstack([40 + 26 * _xx / 480, 24 + 16 * _yy / 270, 8 + 5 * _yy / 270])).astype(np.float32)   # BGR: tinta ATC
_LUZES = [(90, 60, 70, 40, .23, .17, 0.0, 70, (46, 122, 224), .45), (400, 210, 60, 50, .19, .27, 1.7, 85, (120, 84, 30), .40),
          (300, 40, 90, 30, .13, .21, 3.1, 55, (62, 138, 240), .28)]

def fundo(t):
    img = _BASE.copy()
    for cx0, cy0, ax, ay, fx, fy, ph, r, cor, alfa in _LUZES:
        cx = cx0 + ax * math.sin(fx * t + ph); cy = cy0 + ay * math.cos(fy * t + ph)
        g = (np.exp(-((_xx - cx) ** 2 + (_yy - cy) ** 2) / (2 * r * r)) * alfa)[..., None]
        img = img * (1 - g) + np.array(cor, np.float32) * g
    return cv2.resize(img, (OW, OH), interpolation=cv2.INTER_CUBIC)

def _mascara(w, h, r):
    m = np.zeros((h, w), np.uint8); cv2.rectangle(m, (r, 0), (w - r, h), 255, -1); cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)): cv2.circle(m, (cx, cy), r, 255, -1, cv2.LINE_AA)
    return m.astype(np.float32) / 255

MASCARA = _mascara(CW, CH + BARRA, 16)[..., None]
_s = np.zeros((OH, OW), np.float32); _s[CY0 + 22:CY0 + 22 + CH + BARRA, CX0 + 6:CX0 + 6 + CW] = 1
SOMBRA = (cv2.GaussianBlur(_s, (0, 0), 28) * 0.6)[..., None]
BARRA_IMG = np.full((BARRA, CW, 3), (30, 24, 20), np.uint8)
for k, cor in enumerate(((88, 95, 255), (46, 189, 254), (64, 201, 40))):
    cv2.circle(BARRA_IMG, (26 + 22 * k, BARRA // 2), 7, cor, -1, cv2.LINE_AA)
cv2.rectangle(BARRA_IMG, (CW // 2 - 220, 10), (CW // 2 + 220, BARRA - 10), (52, 44, 38), -1)
cv2.putText(BARRA_IMG, "lms.grupoangbu.com", (CW // 2 - 92, BARRA // 2 + 7), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (205, 214, 222), 1, cv2.LINE_AA)

def compor(conteudo, t):
    bg = fundo(t) * (1 - SOMBRA)
    cartao = np.vstack([BARRA_IMG, conteudo]).astype(np.float32)
    zona = bg[CY0:CY0 + CH + BARRA, CX0:CX0 + CW]
    bg[CY0:CY0 + CH + BARRA, CX0:CX0 + CW] = zona * (1 - MASCARA) + cartao * MASCARA
    return np.clip(bg, 0, 255).astype(np.uint8)

def renderizar_zoom(entrada, focos, saida, t_fundo=0.0, cortes=()):
    cfr = TMP / (saida.stem + "-cfr.mp4")
    run("ffmpeg", "-y", "-loglevel", "error", "-i", entrada, "-r", str(FPS), "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", cfr)
    cap = cv2.VideoCapture(str(cfr)); W = int(cap.get(3)); H = int(cap.get(4)); escala = W / VW
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OW}x{OH}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", str(saida)], stdin=subprocess.PIPE)
    i = 0; cxp, cyp, zp = VW / 2, VH / 2, 1.0
    while True:
        ok, fr = cap.read()
        if not ok: break
        t = i / FPS; i += 1
        if any(a <= t < b for a, b in cortes): continue
        ws = [(peso(f, t), f) for f in focos]; wmax = max([w for w, _ in ws] + [0])
        if wmax > 1e-3:
            soma = sum(w for w, _ in ws)
            cx = sum(w * f["x"] for w, f in ws) / soma; cy = sum(w * f["y"] for w, f in ws) / soma
            z = 1 + max(w * (f["z"] - 1) for w, f in ws)
            cx = VW / 2 + (cx - VW / 2) * wmax; cy = VH / 2 + (cy - VH / 2) * wmax
        else:
            cx, cy, z = VW / 2, VH / 2, 1.0
        cxp += (cx - cxp) * 0.3; cyp += (cy - cyp) * 0.3; zp += (z - zp) * 0.3
        cw, ch = W / zp, H / zp
        x0 = min(max(cxp * escala - cw / 2, 0), W - cw); y0 = min(max(cyp * escala - ch / 2, 0), H - ch)
        M = np.float32([[CW / cw, 0, -x0 * CW / cw], [0, CH / ch, -y0 * CH / ch]])
        enc.stdin.write(compor(cv2.warpAffine(fr, M, (CW, CH), flags=cv2.INTER_AREA), t_fundo + t).tobytes())
    enc.stdin.close(); enc.wait(); cap.release()

# ---------- grafismos (estilo da página inicial: tinta, Instrument Serif e Geist) ----------
LOGO = (RAIZ / "static" / "logo-600.png").as_uri()
FONTE = lambda n: (RAIZ / "static" / "fonts" / n).as_uri()   # URI codificado: a pasta do projeto tem espaços
FONTES = f"""@font-face{{font-family:IS;src:url('{FONTE("InstrumentSerif.woff2")}')}}
@font-face{{font-family:IS;font-style:italic;src:url('{FONTE("InstrumentSerif-Italic.woff2")}')}}
@font-face{{font-family:GS;src:url('{FONTE("Geist.woff2")}');font-weight:100 900}}"""

def png_html(html, destino, w, h):
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--allow-file-access-from-files"])
        pagina = TMP / f"{destino.stem}.html"; pagina.write_text(html, encoding="utf-8")
        pg = b.new_page(viewport={"width": w, "height": h}); pg.goto(pagina.as_uri()); pg.wait_for_function("document.fonts.status==='loaded'"); pg.wait_for_timeout(300)
        pg.locator("#p").screenshot(path=str(destino), omit_background=True); b.close()

def capitulo_png(texto, destino):
    num, titulo = texto.split(" / ", 1)
    png_html(f"""<html><head><style>{FONTES}html,body{{margin:0;background:transparent}}
#p{{position:absolute;display:flex;align-items:center;gap:22px;padding:20px 32px 20px 22px;background:rgba(7,17,27,.9);border:1px solid rgba(236,230,218,.18);
border-radius:999px;box-shadow:0 18px 40px rgba(0,0,0,.35);backdrop-filter:blur(10px)}}
.n{{font:600 22px GS,sans-serif;letter-spacing:.14em;color:#07111b;background:#ece6da;border-radius:999px;padding:10px 16px}}
.t{{color:#ece6da;font:400 46px/1 IS,serif;white-space:nowrap}}</style></head>
<body><div id="p"><div class="n">{num}</div><div class="t">{titulo}</div></div></body></html>""", destino, 1600, 300)

CSS_FUNDO = """html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#07111b}
.luz{position:absolute;border-radius:50%;filter:blur(110px);opacity:.5}
.l1{width:760px;height:760px;background:#e07a2e;left:-260px;bottom:-320px;opacity:.28;animation:m1 8s ease-in-out infinite alternate}
.l2{width:680px;height:680px;background:#1d4a72;right:-180px;top:-260px;animation:m2 9s ease-in-out infinite alternate}
@keyframes m1{to{transform:translate(160px,-90px)}}@keyframes m2{to{transform:translate(-160px,110px)}}
.c{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:#ece6da}
img{width:120px;opacity:0;transform:translateY(16px);animation:up .9s cubic-bezier(.16,1,.3,1) .2s forwards}
.k{font:500 22px GS,sans-serif;letter-spacing:.24em;text-transform:uppercase;color:#a8a399;margin-top:34px;opacity:0;animation:up .9s cubic-bezier(.16,1,.3,1) .5s forwards}
h1{font:400 128px/1 IS,serif;margin:22px 0 0;opacity:0;transform:translateY(30px);animation:up 1s cubic-bezier(.16,1,.3,1) .7s forwards}
h1 em{font-style:italic;color:#f2b483}
p{font:400 32px/1.4 GS,sans-serif;color:#c9c3b7;margin:22px 0 0;opacity:0;animation:up 1s cubic-bezier(.16,1,.3,1) 1.05s forwards}
.risco{width:0;height:1px;background:#ece6da55;margin-top:40px;animation:w 1.2s cubic-bezier(.16,1,.3,1) 1.3s forwards}
@keyframes up{to{opacity:1;transform:none}}@keyframes w{to{width:420px}}"""

def gravar_html(html, destino, segundos):
    pagina = TMP / f"{destino.stem}.html"; pagina.write_text(html, encoding="utf-8")
    pasta = TMP / f"{destino.stem}-rec"; pasta.mkdir()
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--allow-file-access-from-files", "--window-size=1920,1080"])
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(pasta), record_video_size={"width": 1920, "height": 1080})
        pg = ctx.new_page(); pg.goto(pagina.as_uri()); pg.wait_for_timeout(int(segundos * 1000) + 600)   # as fontes carregam do disco antes da animação
        v = pg.video; ctx.close(); webm = v.path(); b.close()
    run("ffmpeg", "-y", "-loglevel", "error", "-ss", "0.5", "-i", webm, "-t", f"{segundos:.2f}", "-r", str(FPS),
        "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", destino)

def gravar_cartao(kicker, titulo, sub, destino, segundos):
    html = (f"<html><head><style>{FONTES}{CSS_FUNDO}</style></head><body><div class='luz l1'></div><div class='luz l2'></div>"
            f"<div class='c'><img src='{LOGO}'><div class='k'>{kicker}</div><h1>{titulo}</h1><p>{sub}</p><div class='risco'></div></div></body></html>")
    gravar_html(html, destino, segundos)

# ---------- montagem ----------
TRANS = 0.6

def main():
    servidor = subprocess.Popen([sys.executable, str(AQUI / "preparar_dados.py"), str(DADOS)])
    servidor.wait()
    srv = subprocess.Popen([sys.executable, str(RAIZ / "atc_lms.py"), "servir", "--host", "127.0.0.1", "--porta", str(PORTA)],
                           env=dict(os.environ, ATC_DADOS=str(DADOS)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    try:
        gravacoes = gravar()
    finally:
        srv.terminate()
    abertura = TMP / "abertura.mp4"
    gravar_cartao("ATC Formação · walkthrough", ROTEIRO["titulo"].replace("Para ", "Para <em>") + "</em>", ROTEIRO["subtitulo"], abertura, 3.6)
    pecas, vozes, falas = [abertura], [], []
    for k, s in enumerate(SECOES):
        vo = AQUI / "locucao" / VIDEO / f"{s['id']}.mp3"; dv = dur(vo) if s["texto"] else 0.0
        if s["texto"]: vozes.append((len(pecas), vo))
        if s["id"] not in gravacoes:              # fecho
            fim = TMP / "fim.mp4"
            gravar_cartao("Angbu Training Centre · Cabinda", "Aprender hoje.<br><em>Ir mais longe amanhã.</em>" if VIDEO == "formando" else ("Galeria <em>3D.</em>" if VIDEO == "galeria" else "ATC <em>Formação.</em>"),
                          "lms.grupoangbu.com", fim, dv + 2.4)
            pecas.append(fim); continue
        webm, focos, fs, cortes = gravacoes[s["id"]]
        z = TMP / f"{s['id']}-zoom.mp4"; renderizar_zoom(webm, focos, z, t_fundo=k * 17.0, cortes=cortes)
        fs = [dict(f, t=f["t"] - sum(min(b, f["t"]) - a for a, b in cortes if a < f["t"])) for f in fs]
        dr = dur(z)
        if fs:   # o guia fala: acelera o que vem antes; a fala fica em velocidade real
            pre = min(f["t"] for f in fs) - 0.4; antes = min(max(dv + 0.8, pre / 1.8), pre); fator = pre / antes
            alvo = antes + dr - pre
            falas += [dict(f, k=len(pecas), t=antes + f["t"] - pre) for f in fs]
            fc = (f"[0:v]split[a][b];[a]trim=0:{pre:.3f},setpts=(PTS-STARTPTS)/{fator:.4f}[a1];"
                  f"[b]trim=start={pre:.3f},setpts=PTS-STARTPTS[b1];[a1][b1]concat=n=2:v=1,"
                  f"tpad=stop_mode=clone:stop_duration=6,trim=duration={alvo:.3f},setpts=PTS-STARTPTS[v0]")
        else:
            alvo = min(max(dr, dv + 1.6), dv + 4.0); fator = max(1.0, min(dr / alvo, 1.8))
            fc = f"[0:v]setpts=PTS/{fator:.4f},tpad=stop_mode=clone:stop_duration=8,trim=duration={alvo:.3f},setpts=PTS-STARTPTS[v0]"
        peca = TMP / f"{s['id']}-final.mp4"; ultimo = "[v0]"; entradas = ["-i", z]
        if s["capitulo"]:
            png = TMP / f"{s['id']}-cap.png"; capitulo_png(s["capitulo"], png)
            entradas += ["-loop", "1", "-i", png]
            fc += (f";[1:v]format=rgba,fade=t=in:st=0.5:d=0.35:alpha=1,fade=t=out:st=4.0:d=0.4:alpha=1[c];"
                   f"{ultimo}[c]overlay=x='if(lt(t,1.05),-w+(w+90)*(t-0.5)/0.55,90)':y=H-h-56:enable='between(t,0.5,4.4)':shortest=1[v1]")
            ultimo = "[v1]"
        run("ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", fc, "-map", ultimo, "-t", f"{alvo:.3f}",
            "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), peca)
        pecas.append(peca)
        print(s["id"], f"gravação {dr:.1f}s -> {alvo:.1f}s (x{fator:.2f}), locução {dv:.1f}s, falas {len(fs)}", flush=True)
    duracoes = [dur(p) for p in pecas]; inicios = [0.0]
    for d in duracoes[:-1]: inicios.append(inicios[-1] + d - TRANS)
    total = inicios[-1] + duracoes[-1]
    entradas = sum((["-i", p] for p in pecas), []); fc, ultimo = [], "[0:v]"
    tipos = ["fade", "smoothleft", "smoothup", "smoothleft", "fade"]
    for k in range(1, len(pecas)):
        tr = "fade" if k in (1, len(pecas) - 1) else tipos[k % len(tipos)]
        fc.append(f"{ultimo}[{k}:v]xfade=transition={tr}:duration={TRANS}:offset={inicios[k]:.3f}[x{k}]"); ultimo = f"[x{k}]"
    video = TMP / "video.mp4"
    run("ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", ";".join(fc), "-map", ultimo,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", video)
    entradas, fc, n, rotulos = ["-i", video, "-stream_loop", "2", "-i", MUSICA], [], 2, []
    for k, (i_peca, vo) in enumerate(vozes):
        ms = int((inicios[i_peca] + 0.55) * 1000); entradas += ["-i", vo]
        fc.append(f"[{n}:a]adelay={ms}|{ms},aformat=sample_rates=44100:channel_layouts=stereo[v{k}]"); rotulos.append(f"[v{k}]"); n += 1
    for j, f in enumerate(falas):
        origem = ficheiro_local(f["src"])
        if not origem or not origem.is_file(): continue
        ms = int((inicios[f["k"]] + f["t"]) * 1000); entradas += ["-i", origem]
        fc.append(f"[{n}:a]atrim=0:{f['dur']:.2f},afade=t=out:st={f['dur'] - 0.25:.2f}:d=0.25,volume=0.85,"
                  f"adelay={ms}|{ms},aformat=sample_rates=44100:channel_layouts=stereo[g{j}]"); rotulos.append(f"[g{j}]"); n += 1
    fc.append("".join(rotulos) + f"amix=inputs={len(rotulos)}:normalize=0,apad=whole_dur={total:.2f},asplit=2[voz][chave]")
    fc.append(f"[1:a]atrim=0:{total:.2f},afade=t=in:d=1.0,afade=t=out:st={total - 2.5:.2f}:d=2.5,volume=0.32,aformat=sample_rates=44100:channel_layouts=stereo[mus]")
    fc.append("[mus][chave]sidechaincompress=threshold=0.015:ratio=12:attack=25:release=450[musd]")
    fc.append("[voz][musd]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    run("ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", "-movflags", "+faststart", SAIDA)
    print("ok", SAIDA, f"{total:.1f}s")
    shutil.rmtree(TMP, ignore_errors=True)

if __name__ == "__main__":
    main()
