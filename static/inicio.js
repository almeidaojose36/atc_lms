// Páginas públicas (início e entrada): cabeçalho, revelação suave, lista de percursos e destaque A+ com o scroll.
(() => {
  const nav = document.getElementById('nav');
  const onScroll = () => nav && nav.classList.toggle('solid', scrollY > innerHeight * 0.6);
  addEventListener('scroll', onScroll, { passive: true }); onScroll();
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: 0.18 });
  document.querySelectorAll('.rv').forEach((el) => io.observe(el));
  const thumb = document.getElementById('thumb'), timg = thumb && thumb.querySelector('img');
  if (thumb) document.querySelectorAll('.path').forEach((p) => {
    p.addEventListener('mouseenter', () => { timg.src = p.dataset.img; thumb.classList.add('on'); });
    p.addEventListener('mouseleave', () => thumb.classList.remove('on'));
    p.addEventListener('mousemove', (e) => { thumb.style.left = e.clientX + 'px'; thumb.style.top = e.clientY + 'px'; });
  });
  // Guias na página inicial: ouvir a apresentação da Helena ou do Miguel em direto no cartão.
  const guideCards = [...document.querySelectorAll('.guide')];
  guideCards.forEach((card) => {
    const btn = card.querySelector('[data-guide-play]'), vid = card.querySelector('.guide-video'), sub = card.querySelector('.guide-sub');
    if (!btn || !vid) return;
    const syncTrack = () => {
      const tr = vid.textTracks && vid.textTracks[0];
      if (!tr) return;
      if (tr.mode !== 'hidden') tr.mode = 'hidden';
      const active = tr.activeCues && tr.activeCues.length ? tr.activeCues[0].text : '';
      if (sub) sub.textContent = active;
    };
    if (vid.textTracks && vid.textTracks[0]) {
      vid.textTracks[0].mode = 'hidden';
      vid.textTracks[0].addEventListener('cuechange', syncTrack);
    }
    vid.addEventListener('loadedmetadata', syncTrack);
    vid.addEventListener('timeupdate', syncTrack);
    const stopCard = (c) => {
      const v = c.querySelector('.guide-video'), b = c.querySelector('[data-guide-play]'), s = c.querySelector('.guide-sub');
      if (v) { v.pause(); v.currentTime = 0; }
      if (s) s.textContent = '';
      c.classList.remove('playing');
      if (b) b.textContent = b.dataset.label || '▶ Ouvir';
    };
    const toggle = () => {
      if (card.classList.contains('playing')) { stopCard(card); return; }
      guideCards.forEach((other) => { if (other !== card) stopCard(other); });
      card.classList.add('playing');
      btn.textContent = '❚❚ Parar';
      vid.muted = false;
      syncTrack();
      vid.play().catch(() => { stopCard(card); });
    };
    btn.addEventListener('click', toggle);
    vid.addEventListener('click', toggle);
    vid.addEventListener('ended', () => stopCard(card));
  });

  // Destaque: o PC desmonta-se com o scroll (ou alterna para CompTIA Network+); clicar num módulo salta para essa etapa.
  const feat = document.getElementById('feature');
  if (!feat) return;
  const TRACKS = {
    aplus: {
      eyebrow: 'Percurso em destaque · Hardware',
      title: 'CompTIA A+',
      desc: 'Monte, configure e repare computadores. Do processador à rede sem fios, aprende o que um técnico faz todos os dias.',
      modules: ['Componentes e montagem', 'Dispositivos móveis', 'Redes e conectividade', 'Segurança e resolução de problemas']
    },
    netplus: {
      eyebrow: 'Percurso em destaque · Redes',
      title: 'CompTIA Network+',
      desc: 'Projete, configure e mantenha redes empresariais. Dos cabos e switches ao encaminhamento IP e segurança de rede.',
      modules: ['Arquitetura e topologias de rede', 'Switching, VLANs e cablagem estruturada', 'Endereçamento IPv4/IPv6 e routing', 'Segurança, monitorização e diagnóstico']
    }
  };
  const tabs = [...feat.querySelectorAll('.feature-tab')];
  let setTrack = null;   // definido mais abaixo quando há animação
  const feyebrow = document.getElementById('feyebrow'), ftitle = document.getElementById('ftitle'), fdesc = document.getElementById('fdesc');
  const still = feat.querySelector('.feature-media img');
  const stillA = still && { src: still.getAttribute('src'), alt: still.alt };
  const items = [...feat.querySelectorAll('.modules li')], count = document.getElementById('fcount');
  tabs.forEach((tab) => tab.addEventListener('click', () => {
    const key = tab.dataset.track, data = TRACKS[key];
    if (!data) return;
    tabs.forEach((t) => { t.classList.toggle('on', t === tab); t.setAttribute('aria-selected', String(t === tab)); });
    if (feyebrow) feyebrow.textContent = data.eyebrow;
    if (ftitle) ftitle.textContent = data.title;
    if (fdesc) fdesc.textContent = data.desc;
    items.forEach((li, i) => { const b = li.querySelector('b'); if (b && data.modules[i]) b.textContent = data.modules[i]; });
    if (still) { const net = key === 'netplus'; still.src = net ? still.dataset.netSrc : stillA.src; still.alt = net ? still.dataset.netAlt : stillA.alt; }
    if (setTrack) setTrack(key);
  }));
  items.forEach((li, idx) => {
    const jump = () => {
      const total = feat.offsetHeight - innerHeight;
      if (total <= 0) return;
      const targetY = window.scrollY + feat.getBoundingClientRect().top + ((idx + 0.15) / items.length) * total;
      window.scrollTo({ top: targetY, behavior: 'smooth' });
    };
    li.addEventListener('click', jump);
    li.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); jump(); } });
  });
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) { feat.classList.add('no-motion'); feat.style.height = 'auto'; return; }
  const canvas = feat.querySelector('canvas'), ctx = canvas.getContext('2d');
  // Cada percurso tem a sua sequência: A+ (o PC desmonta-se) e Network+ (a rede acende-se do PC ao servidor).
  // Em ambas, o fotograma n é o início (scroll no topo) e o 1 é o fim.
  const small = matchMedia('(max-width: 768px)').matches;
  const SEQ = {
    aplus: { dir: feat.dataset.frames, n: +feat.dataset.count, frames: [] },
    netplus: { dir: feat.dataset.framesNet, n: +feat.dataset.countNet, frames: [] }
  };
  let seq = SEQ.aplus, n = seq.n, frames = seq.frames, near = false;
  const url = (k) => `${seq.dir}${small ? 'm/' : ''}${String(k).padStart(4, '0')}.webp`;
  const load = (k) => { if (!frames[k]) { const im = new Image(); im.src = url(k); im.onload = () => draw(); frames[k] = im; } return frames[k]; };
  const loadAll = () => { for (let k = n; k >= 1; k--) load(k); };
  for (let k = n; k > n - 20; k--) load(k);             // o início da sequência primeiro
  new IntersectionObserver((es, o) => { if (es[0].isIntersecting) { near = true; loadAll(); o.disconnect(); } }, { rootMargin: '150% 0px' }).observe(feat);
  setTrack = (key) => {
    const next = SEQ[key];
    if (!next || !next.dir || !next.n || next === seq) return;
    seq = next; n = seq.n; frames = seq.frames;
    const k = Math.round(n - p * (n - 1));              // carrega primeiro os fotogramas à volta da posição atual
    for (let j = 0; j < 12; j++) { load(Math.min(n, k + j)); load(Math.max(1, k - j)); }
    if (near) loadAll();
    draw();
  };
  let p = 0;
  function fit() { const r = canvas.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2); canvas.width = r.width * d; canvas.height = r.height * d; draw(); }
  function draw() {
    let k = Math.round(n - p * (n - 1));                  // p=0: montado (fotograma n); p=1: desmontado (1)
    let im = frames[k];
    for (let j = 1; (!im || !im.complete || !im.naturalWidth) && j < n; j++) im = frames[Math.min(n, k + j)] || frames[Math.max(1, k - j)];
    if (!im || !im.naturalWidth) return;
    const s = Math.max(canvas.width / im.naturalWidth, canvas.height / im.naturalHeight), w = im.naturalWidth * s, h = im.naturalHeight * s;
    ctx.drawImage(im, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
  }
  function update() {
    const r = feat.getBoundingClientRect(), total = feat.offsetHeight - innerHeight;
    p = Math.min(1, Math.max(0, -r.top / total));
    const active = Math.min(items.length - 1, Math.floor(p * items.length));
    items.forEach((li, i) => {
      li.classList.toggle('on', i === active); li.classList.toggle('done', i < active);
      const local = Math.min(1, Math.max(0, p * items.length - i));
      li.querySelector('i').style.height = (i < active ? 1 : i === active ? local : 0) * (li.offsetHeight - 28) + 'px';
    });
    count.textContent = String(active + 1).padStart(2, '0');
    draw();
  }
  let ticking = false;
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; update(); }); } }, { passive: true });
  addEventListener('resize', fit); fit(); update();
})();

// Apresentação: um leitor grande, troca de vídeo pelos cartões e ecrã inteiro (com recurso a uma janela que ocupa o ecrã
// quando o navegador não permite o ecrã inteiro, por exemplo dentro de outra página).
(() => {
  const video = document.getElementById('pv-video');
  if (!video) return;
  const box = document.getElementById('pv-box'), boxVideo = document.getElementById('pv-box-video');
  const cards = [...document.querySelectorAll('.pv-card')];
  cards.forEach((c) => c.addEventListener('click', () => {
    cards.forEach((x) => { x.classList.toggle('on', x === c); x.setAttribute('aria-pressed', String(x === c)); });
    video.poster = c.dataset.poster; video.src = c.dataset.video; video.load();
    video.play().catch(() => {});
    video.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }));
  let antes = null;
  function abrir() {
    antes = document.activeElement;
    const t = video.currentTime, tocava = !video.paused;
    video.pause();
    boxVideo.src = video.currentSrc || video.querySelector('source').src; boxVideo.poster = video.poster;
    box.hidden = false; document.body.style.overflow = 'hidden';
    boxVideo.addEventListener('loadedmetadata', () => { boxVideo.currentTime = t; boxVideo.play().catch(() => {}); }, { once: true });
    if (!tocava && t === 0) boxVideo.play().catch(() => {});
    const pedir = box.requestFullscreen || box.webkitRequestFullscreen;
    if (pedir) { try { const p = pedir.call(box); if (p && p.catch) p.catch(() => {}); } catch (e) { /* fica a janela a ocupar o ecrã */ } }
    document.getElementById('pv-close').focus();
  }
  function fechar() {
    const t = boxVideo.currentTime;
    boxVideo.pause(); box.hidden = true; document.body.style.overflow = '';
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if (t) video.currentTime = t;
    if (antes) antes.focus();
  }
  document.getElementById('pv-full').addEventListener('click', abrir);
  video.addEventListener('click', () => { if (video.paused && video.currentTime < 0.5) abrir(); });   // o primeiro clique abre em grande
  document.getElementById('pv-close').addEventListener('click', fechar);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !box.hidden) fechar(); });
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && !box.hidden) fechar(); });
})();
