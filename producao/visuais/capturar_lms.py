#!/usr/bin/env python3
"""Captura ecrãs reais do LMS (1920x1080) para usar como b-roll nos vídeos dos apresentadores.

Requer o LMS a correr em http://localhost:8080 (python3 atc_lms.py) e `pip install playwright`.
Usa a conta de demonstração do formando. Resultados em producao/visuais/lms-real/.
"""
import pathlib, re
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).parent / "lms-real"
OUT.mkdir(exist_ok=True)
BASE = "http://localhost:8080"

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    def shot(nome, url=None, full=False):
        if url: pg.goto(BASE + url)
        pg.wait_for_load_state("networkidle")
        pg.screenshot(path=str(OUT / f"{nome}.png"), full_page=full)
        print("ok", nome, pg.url, flush=True)
    shot("01-entrar", "/entrar")
    pg.fill("input[name=email]", "formando@atc.ao"); pg.fill("input[name=pw]", "formando123")
    pg.click("form .btn"); pg.wait_for_load_state("networkidle")
    shot("02-inicio")
    shot("03-catalogo", "/#catalogo")
    shot("04-curso", "/cursos/informatica")
    hrefs = pg.eval_on_selector_all("a", "els=>[...new Set(els.map(e=>e.getAttribute('href')))]")
    shot("05-apresentador", "/cursos/informatica/apresentador")
    shot("06-conta", "/conta")
    shot("07-introducao", "/cursos/informatica/introducao")
    aulas = [h for h in hrefs if h and re.match(r"/cursos/informatica/aula/", h)]
    print("links", [h for h in hrefs if h and h.startswith("/cursos")])
    if aulas: shot("08-aula", aulas[0])
    shot("09-manual", "/cursos/informatica/modulo/1/manual")
    shot("10-questionario", "/cursos/informatica/modulo/1/questionario")
    b.close()
