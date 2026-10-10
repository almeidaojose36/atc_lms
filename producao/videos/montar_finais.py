#!/usr/bin/env python3
"""Monta os vídeos finais dos apresentadores.

1. Base: a versão com a voz escolhida de cada clip (ver VOZ_BASE).
2. B-roll: substitui os planos desenhados por gravações reais do LMS
   (producao/visuais/lms-real/gravacoes) e junta um grafismo com nome/título onde pedido.
3. H8: corta a repetição da frase final.
Resultado: producao/videos/avatar-video-final/<ID>.mp4 (os originais não são alterados).
"""
import json, pathlib, re, subprocess, sys, tempfile
from playwright.sync_api import sync_playwright

V = pathlib.Path(__file__).resolve().parent
GRAV = V.parent / "visuais" / "lms-real" / "gravacoes"
FINAL = V / "avatar-video-final"; GRAF = V / "grafismos"
FINAL.mkdir(exist_ok=True); GRAF.mkdir(exist_ok=True)
API = "https://api.elevenlabs.io/v1"
NOMES = {"H": "Helena", "M": "Miguel"}

# pasta da versão com a voz escolhida (STS = avatar-video-novas-vozes, texto = avatar-video-voz-texto-v2)
VOZ_BASE = {c: "avatar-video-novas-vozes" for c in "H1 H2 H3 H4 H5 H6 H7 H8 M1 M2 M5 M6 M7".split()}
VOZ_BASE.update({c: "avatar-video-voz-texto-v2" for c in "H9 M3 M4 M8".split()})

# (início, fim, [(gravação, de, até), ...]) substitui esse intervalo por ecrãs reais do LMS
# (início, fim, [(gravação, de, até), ...], entrada, saída): substitui esse intervalo por ecrãs reais do LMS.
# "corte" = mudança seca (quando o plano original também muda de forma seca); "fade" = dissolução de 0,2 s.
CORTES = {
    "H1": [(1.0, 7.5, [("catalogo", .8, 3.3), ("catalogo", 4.0, 5.5), ("catalogo", 10.0, 12.5)], "fade", "fade")],
    "M2": [(0.5, 10.0, [("catalogo", .8, 3.8), ("catalogo", 4.0, 6.0), ("catalogo", 8.0, 9.0), ("catalogo", 10.0, 12.5)], "fade", "fade")],
    "H5": [(1.2, 9.0, [("perfil", .6, 5.6), ("perfil", 8.2, 11.0)], "fade", "fade")],
    "M7": [(1.2, 9.0, [("perfil", .6, 5.6), ("perfil", 8.2, 11.0)], "fade", "fade")],
    "H6": [(2.85, 6.05, [("visao", .8, 2.3), ("visao", 2.9, 4.4)], "corte", "corte")],
    "M1": [(3.1, 7.4, [("visao", .8, 3.0), ("visao", 3.0, 5.2)], "corte", "fade")],
    "H8": [(0.75, 5.95, [("manual", 1.0, 3.7), ("manual", 4.2, 7.0)], "corte", "corte")],
    "M4": [(2.0, 8.0, [("curso", .8, 3.4), ("curso", 3.4, 6.0)], "fade", "corte")],
    "H9": [(4.5, 10.0, [("aula", .8, 5.3)], "fade", "corte")],
    "M8": [(4.5, 10.0, [("aula", .8, 5.3)], "fade", "corte")],
}
# grafismo (nome/título): clip -> (palavra que dispara, título, subtítulo, duração)
GRAFISMOS = {
    "H4": ("Helena", "Helena", "Guia virtual · ATC Angbu Training Centre", 7.0),
    "M5": ("Miguel", "Miguel", "Guia virtual · ATC Angbu Training Centre", 7.0),
    "H7": ("Informática", "Informática na Ótica do Utilizador", "Curso prático · ATC Angbu Training Centre", 7.0),
    "M6": ("informática", "Informática na Ótica do Utilizador", "Curso prático · ATC Angbu Training Centre", 7.0),
}

def run(*a, **k): return subprocess.run([str(x) for x in a], check=True, **k)
def dur(f): return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f, capture_output=True, text=True).stdout)

def base_path(cid):
    quem = NOMES[cid[0]]
    origem = sorted((V / "avatar-video" / quem).glob("*.mp4"))[int(cid[1:]) - 1].name
    return V / VOZ_BASE[cid] / quem / origem, origem

def palavras(video):
    with tempfile.TemporaryDirectory() as t:
        run("ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vn", "-ac", "1", "-b:a", "64k", pathlib.Path(t) / "a.mp3")
        r = run("curl", "-sS", "--fail-with-body", "-F", "model_id=scribe_v1", "-F", f"file=@{pathlib.Path(t)/'a.mp3'}", f"{API}/speech-to-text", capture_output=True, text=True)
    return [w for w in json.loads(r.stdout)["words"] if w["type"] == "word"]

def grafismo_png(titulo, sub, destino):
    html = f"""<html><head><style>
@font-face{{font-family:RS;src:url(file://{V.parents[1]}/static/fonts/RobotoSlab.woff2)}}
@font-face{{font-family:MS;src:url(file://{V.parents[1]}/static/fonts/Montserrat.woff2)}}
html,body{{margin:0;background:transparent}}
.p{{position:absolute;left:0;top:0;display:flex;background:rgba(11,33,55,.94);border-radius:10px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.28)}}
.b{{width:12px;background:#DA6D24}}
.t{{padding:20px 34px 22px 28px}}
h1{{margin:0;font:700 54px/1.1 RS,serif;color:#F4F1E6;white-space:nowrap}}
p{{margin:8px 0 0;font:500 27px/1.2 MS,sans-serif;color:#F08A3E;white-space:nowrap}}
</style></head><body><div class="p" id="p"><div class="b"></div><div class="t"><h1>{titulo}</h1><p>{sub}</p></div></div></body></html>"""
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox", "--allow-file-access-from-files"])
        pg = b.new_page(viewport={"width": 1920, "height": 400}); pg.set_content(html); pg.wait_for_timeout(400)
        pg.locator("#p").screenshot(path=str(destino), omit_background=True); b.close()

def fragmento(segs, alvo, destino):
    ins, filt = [], []
    for i, (nome, a, b) in enumerate(segs):
        ins += ["-i", GRAV / f"{nome}.mp4"]
        filt.append(f"[{i}:v]trim={a}:{b},setpts=PTS-STARTPTS,scale=1920:1080,fps=24[s{i}]")
    soma = sum(b - a for _, a, b in segs)
    filt.append("".join(f"[s{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0,setpts=PTS*{alvo/soma:.5f}[o]")
    run("ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", ";".join(filt), "-map", "[o]", "-an",
        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-t", f"{alvo:.3f}", destino)

def montar(cid):
    base, origem = base_path(cid)
    destino = FINAL / f"{cid}.mp4"
    entradas, filt, ultimo, n = ["-i", base], [], "[0:v]", 1
    corte_fim = None
    if cid == "H8":   # remove a repetição final: "todas as tarefas realizadas" dito duas vezes
        w = palavras(base); txt = [x["text"].lower() for x in w]
        idx = [i for i, t in enumerate(txt) if t == "todas"]
        if len(idx) >= 2:
            fim = next(i for i in range(idx[0], idx[1]) if txt[i].startswith("realizad"))
            corte_fim = w[fim]["end"] + 0.02
            print("H8: corta em", corte_fim, flush=True)
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        for (a, b, segs, entra, sai) in CORTES.get(cid, []):
            frag = t / f"f{n}.mp4"; fragmento(segs, b - a, frag)
            entradas += ["-i", frag]
            fades = ""
            if entra == "fade": fades += ",fade=t=in:st=0:d=0.2:alpha=1"
            if sai == "fade": fades += f",fade=t=out:st={b-a-0.2:.2f}:d=0.2:alpha=1"
            filt.append(f"[{n}:v]format=yuva420p{fades},setpts=PTS+{a}/TB[b{n}]")
            filt.append(f"{ultimo}[b{n}]overlay=enable='between(t,{a},{b})':eof_action=pass[v{n}]")
            ultimo = f"[v{n}]"; n += 1
        if cid in GRAFISMOS:
            gatilho, titulo, sub, d = GRAFISMOS[cid]
            w = palavras(base); ini = next((x["start"] for x in w if x["text"].lower().startswith(gatilho.lower())), 1.0)
            ini = max(ini - 0.3, 0.3)
            png = GRAF / f"{cid}-nome.png"; grafismo_png(titulo, sub, png)
            entradas += ["-loop", "1", "-i", png]
            filt.append(f"[{n}:v]format=rgba,fade=t=out:st={ini+d-0.3:.2f}:d=0.3:alpha=1[g{n}]")
            filt.append(f"{ultimo}[g{n}]overlay=x='if(lt(t,{ini+0.45}),-w+(w+100)*(t-{ini})/0.45,100)':y=H-h-110:enable='between(t,{ini},{ini+d})':eof_action=pass[v{n}]")
            ultimo = f"[v{n}]"; n += 1
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *entradas]
        if filt: cmd += ["-filter_complex", ";".join(filt), "-map", ultimo]
        else: cmd += ["-map", "0:v"]
        if corte_fim:
            cmd += ["-map", "0:a", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-af", f"afade=t=out:st={corte_fim-0.15:.3f}:d=0.15", "-c:a", "aac", "-b:a", "192k", "-t", f"{corte_fim:.3f}"]
        else:
            cmd += ["-map", "0:a", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy"]
        if corte_fim: pass
        else: cmd += ["-shortest"]
        run(*cmd, destino)
    return origem

if __name__ == "__main__":
    ids = sys.argv[1:] or [f"H{i}" for i in range(1, 10)] + [f"M{i}" for i in range(1, 9)]
    mapa = json.loads((FINAL / "mapa.json").read_text()) if (FINAL / "mapa.json").exists() else {}
    for cid in ids:
        mapa[cid] = {"origem": montar(cid), "voz": VOZ_BASE[cid], "brolls_lms": bool(CORTES.get(cid)), "grafismo": cid in GRAFISMOS}
        print("ok", cid, flush=True)
    (FINAL / "mapa.json").write_text(json.dumps(mapa, ensure_ascii=False, indent=1))
