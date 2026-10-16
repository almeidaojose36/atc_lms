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
  // Destaque: o PC desmonta-se com o scroll (e volta a montar-se ao subir); os módulos acendem um a um.
  const feat = document.getElementById('feature');
  if (!feat) return;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) { feat.classList.add('no-motion'); feat.style.height = 'auto'; return; }
  const canvas = feat.querySelector('canvas'), ctx = canvas.getContext('2d');
  const n = +feat.dataset.count, small = matchMedia('(max-width: 768px)').matches;
  const url = (k) => `${feat.dataset.frames}${small ? 'm/' : ''}${String(k).padStart(4, '0')}.webp`;
  const frames = [];
  const load = (k) => { if (!frames[k]) { const im = new Image(); im.src = url(k); im.onload = () => draw(); frames[k] = im; } return frames[k]; };
  for (let k = n; k > n - 20; k--) load(k);             // o PC montado (fim da sequência) primeiro
  new IntersectionObserver((es, o) => { if (es[0].isIntersecting) { for (let k = n; k >= 1; k--) load(k); o.disconnect(); } }, { rootMargin: '150% 0px' }).observe(feat);
  const items = [...feat.querySelectorAll('.modules li')], count = document.getElementById('fcount');
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
