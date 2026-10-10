"""Rebuild the editable HyperFrames composition from the approved source frames."""
from pathlib import Path
from PIL import Image
import html
import json
import shutil

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
PACK = ROOT.parent / 'ecras-atc-personalizados'
ASSETS = ROOT / 'assets'
ASSETS.mkdir(exist_ok=True)
(ROOT / 'compositions').mkdir(exist_ok=True)
for name in ['helena.png', 'miguel.png']:
    shutil.copy2(REPO / 'static/presenters' / name, ASSETS / name)
shutil.copy2(REPO / 'static/logo-200.png', ASSETS / 'logo.png')
for font in ['Montserrat.woff2', 'RobotoSlab.woff2']:
    shutil.copy2(REPO / 'static/fonts' / font, ASSETS / font)
shutil.copy2(ROOT / 'node_modules/gsap/dist/gsap.min.js', ASSETS / 'gsap.min.js')

scenes = [
    ('scene-01-sessao', 'helena/01-opcoes-inicio-sessao.png', 'Helena', 'A sua conta', 'Conheça as opções de início de sessão.', ['Contas', 'Opções de início de sessão', 'PIN ou palavra-passe'], 'Nas Definições, abra Contas. Aqui encontra as opções de início de sessão, incluindo o PIN.', [(0.12, .49), (.56, .30)]),
    ('scene-02-documentos', 'miguel/02-menu-iniciar.png', 'Miguel', 'Os seus documentos', 'Encontre os ficheiros da formação.', ['Menu Iniciar', 'Recomendações', 'Manual do formando'], 'No menu Iniciar, encontre os documentos recentes. Abra o manual do formando para acompanhar a formação.', [(.40, .32), (.33, .50)]),
    ('scene-03-plano', 'comuns/02-bloco-notas.png', 'Helena', 'O plano da formação', 'Organize os passos antes de começar.', ['Iniciar sessão', 'Abrir aplicações', 'Guardar o trabalho'], 'No Bloco de notas, consulte o plano da formação. Organize os passos e guarde o seu trabalho.', [(.35, .31), (.37, .50)]),
    ('scene-04-encerrar', 'miguel/03-encerrar.png', 'Miguel', 'Terminar em segurança', 'Guarde o trabalho antes de encerrar.', ['Guardar os ficheiros', 'Menu Iniciar', 'Botão de energia'], 'Antes de encerrar, guarde os ficheiros. No menu Iniciar, use o botão de energia para terminar.', [(.39, .91), (.68, .83)]),
]

fontcss = "@font-face{font-family:ATCDisplay;src:url('assets/Montserrat.woff2')}@font-face{font-family:ATCBody;src:url('assets/RobotoSlab.woff2')}"
css = """*{box-sizing:border-box}html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#0C2337}#root{width:100%;height:100%;position:relative;overflow:hidden} .scene{position:absolute;inset:0;padding:48px 60px 38px;color:#F6F2EA;background:#0C2337;font-family:ATCBody,serif} .top{height:110px;display:flex;align-items:center;justify-content:space-between;font-family:ATCDisplay,sans-serif} .brand{display:flex;align-items:center;gap:22px;font-size:27px} .brand img{width:80px;height:80px;object-fit:contain} .step{font-size:25px;color:#F39445} .main{display:grid;grid-template-columns:1320px 420px;gap:60px;height:760px} .screen{position:relative;width:1320px;height:760px;display:flex;align-items:center;justify-content:center;background:#15364E;border-radius:16px;overflow:hidden} .screen img{display:block;object-fit:contain} .side{padding-top:30px} .presenter{display:flex;align-items:center;gap:18px;font-size:26px} .presenter img{width:78px;height:78px;object-fit:cover;object-position:center 25%;border-radius:50%} h1{font:700 54px/1.06 ATCDisplay,sans-serif;letter-spacing:-1.5px;margin:36px 0 22px} .instruction{font-size:27px;line-height:1.45;margin:0 0 24px} .checklist{display:flex;flex-direction:column;gap:18px} .item{display:flex;align-items:center;gap:14px;font-size:23px;line-height:1.4} .number{flex:none;display:flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:50%;background:#F39445;color:#0C2337;font:700 20px ATCDisplay,sans-serif} .caption{height:94px;display:flex;align-items:center;justify-content:center;margin-top:18px;padding:10px 25px;border-top:2px solid #F39445;font-size:29px;line-height:1.4;text-align:center} .foot{display:flex;justify-content:space-between;color:#D5DEE6;font:20px ATCDisplay,sans-serif;margin-top:8px} .pointer{position:absolute;left:0;top:0;width:58px;height:58px;z-index:10;pointer-events:none} .pointer svg{width:100%;height:100%;fill:#F6F2EA;stroke:#0C2337;stroke-width:1.4;stroke-linejoin:round} .focus{position:absolute;width:66px;height:66px;border:4px solid #F39445;border-radius:50%;pointer-events:none;z-index:9} """
slots=[]
story=['# STORYBOARD\n\nQuatro cenas de 8 segundos. Exportação silenciosa com legendas.\n']
script=['# Guião — Amostra Windows ATC\n\nCada cena contém todos os seus planos em **8 segundos**. Locução prevista: cerca de 6–7 segundos; medir a voz gerada e encurtar o texto se necessário. Não acelerar a voz para ultrapassar o limite.\n\nDireção de voz: português com sotaque angolano natural, vocabulário europeu, tom profissional e acolhedor. Sem voz gerada nesta exportação.\n']
vtt=['WEBVTT\n']
for i,(sid,source,presenter,title,instruction,steps,narration,points) in enumerate(scenes):
    filename=sid+'.png'
    shutil.copy2(PACK / source, ASSETS / filename)
    w,h=Image.open(ASSETS / filename).size
    scale=min(1320/w,760/h)
    iw,ih=round(w*scale),round(h*scale)
    ox,oy=(1320-iw)/2,(760-ih)/2
    positions=[(round(ox+x*iw),round(oy+y*ih)) for x,y in points]
    esc=html.escape
    items=''.join(f'<div class="item" id="{sid}-item-{k}"><span class="number">{k+1}</span><span>{esc(s)}</span></div>' for k,s in enumerate(steps))
    content=f'''<div class="scene"><div class="top"><div class="brand"><img src="assets/logo.png" alt="ATC"><span>INFORMÁTICA · WINDOWS 11</span></div><span class="step">{i+1:02d} / 04</span></div><div class="main"><div class="screen"><img id="{sid}-screen" src="assets/{filename}" width="{iw}" height="{ih}" alt="{esc(title)}"><div class="focus" id="{sid}-focus" data-layout-ignore></div><div class="pointer" id="{sid}-pointer" data-layout-ignore><svg viewBox="0 0 24 24"><path d="M5 3 L5 19 L9 15 L12 22 L15 20.5 L11.5 14 L18 14 Z"/></svg></div></div><div class="side"><div class="presenter"><img src="assets/{presenter.lower()}.png" alt="{presenter}"><span>{presenter} · ATC</span></div><h1>{esc(title)}</h1><p class="instruction">{esc(instruction)}</p><div class="checklist">{items}</div></div></div><div class="caption" data-layout-allow-caption-zone>{esc(narration)}</div><div class="foot"><span>ATC · Angbu Training Centre</span><span>Simulação pedagógica · Português (Portugal)</span></div></div>'''
    a,b=positions
    motion=f'''const tl=gsap.timeline({{paused:true}});tl.fromTo('#{sid} h1',{{scale:0.96,opacity:0}},{{scale:1,opacity:1,duration:.45,ease:'power3.out'}},0);tl.fromTo('#{sid} .item',{{x:20,opacity:0}},{{x:0,opacity:1,duration:.4,stagger:.1,ease:'power2.out'}},.3);tl.fromTo('#{sid}-pointer',{{x:{a[0]-100},y:{a[1]+80},opacity:0}},{{x:{a[0]-12},y:{a[1]-7},opacity:1,duration:.7,ease:'power3.out'}},.9);tl.fromTo('#{sid}-focus',{{x:{a[0]-33},y:{a[1]-33},scale:.8,opacity:0}},{{scale:1,opacity:1,duration:.3,ease:'power2.out'}},1.6);tl.to('#{sid}-focus',{{opacity:0,duration:.2}},3.3);tl.to('#{sid}-pointer',{{x:{b[0]-12},y:{b[1]-7},duration:.8,ease:'power2.inOut'}},3.4);tl.set('#{sid}-focus',{{x:{b[0]-33},y:{b[1]-33}}},4.2);tl.to('#{sid}-focus',{{opacity:1,duration:.3}},4.2);tl.to('#{sid}-focus',{{scale:1.10,duration:.8,repeat:2,yoyo:true,ease:'sine.inOut'}},4.6);window.__timelines['{sid}']=tl;'''
    (ROOT / 'compositions' / (sid+'.html')).write_text(f'<!doctype html><html lang="pt-PT"><body><template><style>#{sid}{{position:absolute;inset:0}}{fontcss}{css}</style><div id="{sid}" data-composition-id="{sid}" data-width="1920" data-height="1080" data-duration="8">{content}</div><script>{motion}</script></template></body></html>')
    (ROOT / 'compositions' / (sid+'.motion.json')).write_text(json.dumps({'duration':8,'assertions':[{'kind':'appearsBy','selector':f'#{sid} h1','bySec':.5}]},indent=2))
    slots.append(f'<div class="clip" id="el-{sid}" data-composition-id="{sid}" data-composition-src="compositions/{sid}.html" data-start="{i*8}" data-duration="8" data-track-index="1" data-width="1920" data-height="1080" style="position:absolute;inset:0"></div>')
    story.append(f'## Frame {i+1}\nstatus: built\nsrc: compositions/{sid}.html\nrules: spring-pop-entrance; cursor-click-ripple (pointer guidance only)\n{title}. 0–1 s: ecrã integral. 1–3.4 s: primeiro destaque. 3.4–7 s: segundo destaque. 7–8 s: manter para leitura.\n')
    script.append(f'## Cena {i+1} — {title} ({presenter})\n\nDuração total: 8 s.\n\n- 0–1 s: ecrã integral e título.\n- 1–3.4 s: ponteiro e primeiro destaque.\n- 3.4–7 s: ponteiro e segundo destaque.\n- 7–8 s: leitura final.\n\nLocução: “{narration}”\n\nFotograma: `{source}`.\n')
    def timestamp(t): return f'00:00:{t:02d}.000'
    vtt.append(f'{i+1}\n{timestamp(i*8)} --> {timestamp((i+1)*8)}\n{narration}\n')
(ROOT / 'index.html').write_text(f'<!doctype html><html lang="pt-PT"><head><meta charset="UTF-8"><script src="assets/gsap.min.js"></script><style>{fontcss}{css}</style></head><body><div id="root" data-composition-id="main" data-width="1920" data-height="1080" data-duration="32">'+''.join(slots)+"</div><script>window.__timelines['main']=gsap.timeline({paused:true});</script></body></html>")
(ROOT / 'STORYBOARD.md').write_text('\n'.join(story))
(ROOT / 'GUIAO.md').write_text('\n'.join(script))
(ROOT / 'amostra-windows-atc.vtt').write_text('\n'.join(vtt))
(ROOT / 'cenas.json').write_text(json.dumps([{'id':s[0],'start':i*8,'duration':8,'frame':s[1],'presenter':s[2],'narration':s[6]} for i,s in enumerate(scenes)],ensure_ascii=False,indent=2)+'\n')
print('Built 4 scenes, 32 seconds total.')
