#!/usr/bin/env python3
"""Grava um vídeo do percurso do formando (escolha do guia, passos de entrada, curso, manual, troca de guia).

O Chromium do Playwright não reproduz H.264, por isso os vídeos do LMS são servidos em WebM durante a gravação
(pasta WEBM, criada por ffmpeg) e o áudio dos clips é misturado depois, nos instantes em que cada um começou.
Requer o LMS em http://localhost:8080 com um formando sem guia escolhido.
Uso: python3 gravar_percurso_guia.py <pasta-webm> <saida.mp4>
"""
import json, pathlib, re, subprocess, sys, tempfile, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gravar_ecras_lms import CURSOR_JS, Rec, CHROME

RAIZ = pathlib.Path(__file__).resolve().parents[2]
BASE = "http://localhost:8080"
WEBM = pathlib.Path(sys.argv[1]); SAIDA = pathlib.Path(sys.argv[2])

def webm_para(url):
    m = re.search(r"/plataforma/(helena|miguel)/([a-z0-9-]+)\.mp4", url)
    if m: return WEBM / f"plataforma-{m[1]}-{m[2]}.webm"
    m = re.search(r"/media/informatica/apresentadores/(helena|miguel)/([a-z0-9-]+)\.mp4", url)
    if m: return WEBM / f"informatica-{m[1]}-{m[2]}.webm"
    if url.endswith("/media/informatica/video/aula-1-1.mp4"): return WEBM / "informatica-video-aula-1-1.webm"
    return None

def original_de(url):
    m = re.search(r"/plataforma/(helena|miguel)/([a-z0-9-]+)\.mp4", url)
    if m: return RAIZ / "plataforma" / "apresentadores" / m[1] / f"{m[2]}.mp4"
    m = re.search(r"/media/informatica/apresentadores/(helena|miguel)/([a-z0-9-]+)\.mp4", url)
    if m: return RAIZ / "cursos" / "informatica" / "apresentadores" / m[1] / f"{m[2]}.mp4"
    return None

def interceptar(route):
    req = route.request; url = req.url
    alvo = webm_para(url)
    if alvo and alvo.is_file():
        route.fulfill(status=200, body=alvo.read_bytes(), headers={"Content-Type": "video/webm", "Accept-Ranges": "none"})
    else:
        route.continue_()

eventos = []
def tocar(pg, indice, segundos, t0):
    src = pg.evaluate("(i)=>{const v=document.querySelectorAll('video')[i]; v.play(); return v.currentSrc}", indice)
    eventos.append((time.time() - t0, src, segundos))
    pg.wait_for_timeout(int(segundos * 1000))
    pg.evaluate("(i)=>document.querySelectorAll('video')[i].pause()", indice)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
    tmp = pathlib.Path(tempfile.mkdtemp())
    ctx = b.new_context(viewport={"width": 1440, "height": 810}, record_video_dir=str(tmp), record_video_size={"width": 1440, "height": 810})
    ctx.add_init_script(CURSOR_JS)
    ctx.add_init_script("document.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('source[type=\"video/mp4\"]').forEach(s=>s.type='video/webm');document.querySelectorAll('video').forEach(v=>v.load())})")
    ctx.route(re.compile(r".*\.mp4$"), interceptar)
    t0 = time.time(); pg = ctx.new_page(); r = Rec(pg)
    pg.goto(BASE + "/entrar"); pg.mouse.move(720, 450); pg.wait_for_timeout(1200)
    # 1. início de sessão
    r.click("input[name=email]"); pg.keyboard.type("formando@atc.ao", delay=55); r.click("input[name=pw]"); pg.keyboard.type("formando123", delay=55)
    r.click("form .btn"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1200)
    # 2. escolher o guia (Miguel)
    r.goto_el(".presenter-option >> nth=0"); pg.wait_for_timeout(700); r.click(".presenter-option >> nth=1"); pg.wait_for_timeout(900)
    r.click("form .btn"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(800)
    # 3. boas-vindas
    tocar(pg, 0, 6, t0); r.click(".onboard-copy form .btn"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(600)
    # 4. perfil
    tocar(pg, 0, 4, t0)
    r.click("textarea[name=goal]"); pg.keyboard.press("Control+A"); pg.keyboard.type("Usar o computador com confiança no trabalho.", delay=40)
    r.click("input[name=occupation]"); pg.keyboard.press("Control+A"); pg.keyboard.type("Secretariado", delay=55); pg.wait_for_timeout(400)
    r.click(".profile-editor .btn"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(600)
    # 5. passeio
    tocar(pg, 0, 4, t0); r.click(".onboard-copy form .btn"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(600)
    # 6. primeiro curso
    tocar(pg, 0, 4, t0); r.goto_el(".course-pick >> nth=0"); pg.wait_for_timeout(500); r.click(".course-pick >> nth=0 >> .btn"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(700)
    # 7. introdução do curso (dois clips)
    tocar(pg, 0, 4, t0); tocar(pg, 1, 4, t0)
    r.click(".guide-intro .actions .btn"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(900)
    # 8. aula 1.1, com os clips do guia antes do vídeo da aula
    pg.goto(BASE + "/cursos/informatica/aula/aula-1-1"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(800)
    tocar(pg, 0, 4, t0); tocar(pg, 1, 4, t0); r.scroll(520, steps=30); pg.wait_for_timeout(1200); r.scroll(-520, steps=20)
    # 9. manual (figura do guia)
    pg.goto(BASE + "/cursos/informatica/modulo/1/manual"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(700)
    tocar(pg, 0, 3, t0); r.goto_el("#s1"); r.scroll(420, steps=30); pg.wait_for_timeout(1800)
    # 10. mudar de guia para a Helena: a figura muda
    r.click(".guide-chip"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(700)
    r.click(".presenter-option >> nth=0"); pg.wait_for_timeout(700); r.click("form .btn"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(800)
    pg.wait_for_timeout(1500)   # início, já com a Helena no cabeçalho
    pg.goto(BASE + "/cursos/informatica/modulo/1/manual"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(600)
    r.goto_el("#s1"); r.scroll(420, steps=30); pg.wait_for_timeout(2200)
    video = pg.video; ctx.close(); webm = pathlib.Path(video.path()); b.close()

# áudio dos clips, nos instantes em que começaram a tocar
entradas, filtros, n = [], [], 0
for inicio, src, dur in eventos:
    f = original_de(src.replace("video/webm", ""))
    if not f or not f.is_file(): continue
    entradas += ["-i", f]; atraso = int((inicio + 0.35) * 1000)
    filtros.append(f"[{n + 1}:a]atrim=0:{dur},asetpts=PTS-STARTPTS,afade=t=out:st={max(dur - 0.15, 0)}:d=0.15,adelay={atraso}|{atraso}[a{n}]"); n += 1
duracao = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", webm],
                               capture_output=True, text=True).stdout)
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", webm, *entradas]
if n:
    cmd += ["-filter_complex", ";".join(filtros) + ";" + "".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={duracao:.2f}[a]", "-map", "0:v", "-map", "[a]"]
cmd += ["-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-t", f"{duracao:.2f}", SAIDA]
subprocess.run([str(x) for x in cmd], check=True)
print("ok", SAIDA, n, "clips com áudio")
