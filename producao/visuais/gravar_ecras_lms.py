#!/usr/bin/env python3
"""Grava percursos reais no LMS (1920x1080, com cursor visível) para usar como b-roll.

Requer o LMS em http://localhost:8080 e `pip install playwright`. Não submete formulários,
por isso não altera a base de dados. Resultados: producao/visuais/lms-real/gravacoes/<nome>.mp4
Uso: python3 gravar_ecras_lms.py [nome ...]
"""
import pathlib, subprocess, sys, tempfile, shutil
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080"
OUT = pathlib.Path(__file__).parent / "lms-real" / "gravacoes"
OUT.mkdir(parents=True, exist_ok=True)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

CURSOR_JS = """
(() => {
  const c = document.createElement('div');
  c.id = '__cur';
  c.style.cssText = 'position:fixed;left:0;top:0;width:30px;height:30px;z-index:2147483647;pointer-events:none;transition:none;';
  c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#fff" stroke="#0B2137" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  const add = () => document.documentElement.appendChild(c);
  (document.documentElement ? add() : document.addEventListener('DOMContentLoaded', add));
  const move = e => { c.style.transform = `translate(${e.clientX}px,${e.clientY}px)`; };
  window.addEventListener('mousemove', move, true);
  window.addEventListener('mousedown', () => { c.style.filter = 'drop-shadow(0 0 10px #DA6D24)'; }, true);
  window.addEventListener('mouseup', () => { c.style.filter = ''; }, true);
})();
"""

class Rec:
    def __init__(self, pg): self.pg = pg; self.x, self.y = 720, 405
    def glide(self, x, y, steps=28):
        self.pg.mouse.move(x, y, steps=steps); self.x, self.y = x, y
    def center(self, sel):
        el = self.pg.locator(sel).first
        el.scroll_into_view_if_needed()
        b = el.bounding_box(); return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    def goto_el(self, sel, steps=28):
        x, y = self.center(sel); self.glide(x, y, steps)
    def click(self, sel):
        self.goto_el(sel); self.pg.wait_for_timeout(250); self.pg.mouse.down(); self.pg.wait_for_timeout(90); self.pg.mouse.up()
    def wait(self, ms): self.pg.wait_for_timeout(ms)
    def scroll(self, dy, steps=20, step_ms=40):
        for _ in range(steps): self.pg.mouse.wheel(0, dy / steps); self.pg.wait_for_timeout(step_ms)

def catalogo(r):      # escolher o primeiro curso e fazer perguntas
    r.pg.goto(BASE + "/"); r.wait(700)
    r.goto_el("#catalogo h2"); r.scroll(520); r.wait(500)
    r.click('a.course[href="/cursos/informatica"]'); r.pg.wait_for_load_state("networkidle"); r.wait(900)
    r.scroll(380); r.wait(500)
    r.click('a[href="/cursos/informatica/aula/aula-1-1"]'); r.pg.wait_for_load_state("networkidle"); r.wait(700)
    r.goto_el("#perguntas h2"); r.scroll(500); r.wait(500)
    r.click('#perguntas textarea'); r.pg.keyboard.type("Posso rever esta aula quando quiser?", delay=55); r.wait(900)

def perfil(r):        # preencher o perfil e escolher o apresentador (sem submeter)
    r.pg.goto(BASE + "/conta"); r.wait(800)
    r.click('textarea[name=goal]'); r.pg.keyboard.press("Control+A"); r.pg.keyboard.type("Usar o computador com confiança no meu trabalho.", delay=45); r.wait(500)
    r.click('input[name=occupation]'); r.pg.keyboard.press("Control+A"); r.pg.keyboard.type("Secretariado", delay=60); r.wait(500)
    r.click('label:has(input[name=color][value=navy])'); r.wait(500)
    r.pg.goto(BASE + "/cursos/informatica/apresentador"); r.wait(900)
    r.click('.presenter-option >> nth=0'); r.wait(900)
    r.click('.presenter-option >> nth=1'); r.wait(900)

def visao(r):         # visão geral da plataforma: início e curso
    r.pg.goto(BASE + "/"); r.wait(900)
    r.scroll(260); r.wait(300)
    r.click('a[href="/cursos/informatica"]'); r.pg.wait_for_load_state("networkidle"); r.wait(800)
    r.scroll(300); r.wait(600)

def manual(r):        # abrir o manual online e percorrê-lo
    r.pg.goto(BASE + "/cursos/informatica"); r.wait(800)
    r.click('a[href="/cursos/informatica/modulo/1/manual"]'); r.pg.wait_for_load_state("networkidle"); r.wait(900)
    r.scroll(700, steps=40); r.wait(300); r.scroll(700, steps=40); r.wait(400)

def curso(r):         # conteúdos do curso
    r.pg.goto(BASE + "/cursos/informatica"); r.wait(1000)
    r.goto_el(".module h2"); r.scroll(320, steps=30); r.wait(500)
    r.goto_el('a[href="/cursos/informatica/aula/aula-1-2"]'); r.wait(700)
    r.scroll(300, steps=30); r.wait(500)

def aula(r):          # lição em vídeo: reproduzir e pausar
    r.pg.goto(BASE + "/cursos/informatica/aula/aula-1-1"); r.wait(1000)
    r.goto_el("video"); r.wait(500)
    r.scroll(260, steps=24); r.wait(700)
    r.goto_el("#perguntas h2"); r.wait(600)

ROTEIROS = dict(catalogo=catalogo, perfil=perfil, visao=visao, manual=manual, curso=curso, aula=aula)

def main(nomes):
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1440, "height": 810})
        pg = ctx.new_page(); pg.goto(BASE + "/entrar")
        pg.fill("input[name=email]", "formando@atc.ao"); pg.fill("input[name=pw]", "formando123"); pg.click("form .btn")
        pg.wait_for_load_state("networkidle"); estado = ctx.storage_state(); ctx.close()
        for nome in nomes:
            tmp = pathlib.Path(tempfile.mkdtemp())
            ctx = b.new_context(viewport={"width": 1440, "height": 810}, storage_state=estado,
                                record_video_dir=str(tmp), record_video_size={"width": 1440, "height": 810})
            ctx.add_init_script(CURSOR_JS)
            pg = ctx.new_page(); r = Rec(pg)
            pg.goto(BASE + "/"); pg.mouse.move(720, 450); pg.wait_for_timeout(600)
            t0 = 0.9
            ROTEIROS[nome](r)
            pg.wait_for_timeout(300)
            video = pg.video; ctx.close(); webm = pathlib.Path(video.path())
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t0), "-i", webm, "-r", "24", "-c:v", "libx264",
                            "-crf", "16", "-pix_fmt", "yuv420p", OUT / f"{nome}.mp4"], check=True)
            shutil.rmtree(tmp, ignore_errors=True)
            print("ok", nome, flush=True)
        b.close()

if __name__ == "__main__":
    main(sys.argv[1:] or list(ROTEIROS))
