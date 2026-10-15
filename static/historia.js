// Página inicial pública. Sequências de fotogramas num canvas presas ao scroll (GSAP ScrollTrigger),
// scroll suave com Lenis e carrossel de cursos com Swiper. Com movimento reduzido mostra um fotograma por secção.
(() => {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const small = window.matchMedia('(max-width: 768px)').matches;
  const motion = !reduce && window.gsap && window.ScrollTrigger;
  const root = document.documentElement;
  root.classList.add(motion ? 'lp-motion' : 'lp-static');

  if (window.Swiper) {
    new Swiper('.lp-swiper', {
      slidesPerView: 1.15, spaceBetween: 14, grabCursor: true, speed: reduce ? 0 : 500,
      pagination: { el: '.lp-swiper .swiper-pagination', clickable: true },
      navigation: { nextEl: '.lp-swiper .swiper-button-next', prevEl: '.lp-swiper .swiper-button-prev' },
      breakpoints: { 640: { slidesPerView: 2.2, spaceBetween: 16 }, 1024: { slidesPerView: 3.2, spaceBetween: 20 } },
      a11y: { prevSlideMessage: 'Curso anterior', nextSlideMessage: 'Curso seguinte', paginationBulletMessage: 'Ir para o curso {{index}}' },
    });
  }

  const pad = (n) => String(n).padStart(4, '0');
  const src = (seq, n) => `${seq.dataset.frames}${small ? 'm/' : ''}${pad(n)}.webp`;

  function canvasFor(seq) {
    const canvas = seq.querySelector('.seq-canvas');
    const ctx = canvas.getContext('2d');
    let last = null;
    const fit = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = canvas.clientWidth * dpr;
      canvas.height = canvas.clientHeight * dpr;
      if (last) draw(last);
    };
    function draw(img) { // paisagem: object-fit cover; retrato: largura total, na parte de cima, com o texto por baixo
      last = img;
      const portrait = canvas.height > canvas.width;
      const s = portrait ? (canvas.width / img.naturalWidth) * 1.12
        : Math.max(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight);
      const w = img.naturalWidth * s, h = img.naturalHeight * s;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, (canvas.width - w) / 2, portrait ? canvas.height * 0.3 - h / 2 : (canvas.height - h) / 2, w, h);
    }
    fit();
    window.addEventListener('resize', fit);
    return draw;
  }

  const seqs = [...document.querySelectorAll('.seq')];

  if (!motion) { // um fotograma estático por secção e todos os passos visíveis
    seqs.forEach((seq) => {
      const draw = canvasFor(seq);
      const img = new Image();
      img.onload = () => draw(img);
      img.src = src(seq, +seq.dataset.count);
    });
    return;
  }

  gsap.registerPlugin(ScrollTrigger);
  if (window.Lenis) {
    const lenis = new Lenis({ lerp: 0.1 });
    lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add((t) => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
    document.querySelectorAll('a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => {
      const target = document.querySelector(a.getAttribute('href'));
      if (target) { e.preventDefault(); lenis.scrollTo(target); }
    }));
  }

  // Título: linhas a subir à entrada. Manifesto: linhas acendem com o scroll.
  gsap.from('.lp-lines > span', { yPercent: 110, opacity: 0, duration: 1, ease: 'power4.out', stagger: 0.12, delay: 0.1 });
  gsap.from('.lp-hero .lp-actions, .lp-hero .eyebrow', { opacity: 0, y: 16, duration: 0.8, delay: 0.5, stagger: 0.1 });
  gsap.to('.lp-reveal > span', {
    opacity: 1, stagger: 0.5, ease: 'none',
    scrollTrigger: { trigger: '.lp-manifesto', start: 'top 75%', end: 'bottom 45%', scrub: true },
  });

  // Sequências: os 20 primeiros fotogramas já, o resto em segundo plano.
  seqs.forEach((seq) => {
    const count = +seq.dataset.count;
    if (!count) return;
    const draw = canvasFor(seq);
    const frames = new Array(count + 1);
    const load = (n) => {
      if (frames[n]) return frames[n];
      const img = new Image();
      img.decoding = 'async';
      img.src = src(seq, n);
      frames[n] = img;
      return img;
    };
    const state = { frame: 1 };
    const render = () => {
      let n = Math.round(state.frame);
      while (n > 1 && !(frames[n] && frames[n].complete && frames[n].naturalWidth)) n--; // o mais próximo já carregado
      const img = frames[n];
      if (img && img.complete && img.naturalWidth) draw(img);
    };
    for (let n = 1; n <= Math.min(20, count); n++) load(n).onload = n === 1 ? render : null;
    const rest = () => { for (let n = 21; n <= count; n++) load(n); };
    ScrollTrigger.create({ trigger: seq, start: 'top 200%', once: true, onEnter: rest });

    const steps = [...seq.querySelectorAll('.seq-step')];
    const final = seq.querySelector('.seq-final');
    const tl = gsap.timeline({
      defaults: { ease: 'none' },
      scrollTrigger: { trigger: seq, start: 'top top', end: () => '+=' + window.innerHeight * 3, pin: true, scrub: 0.5 },
    });
    tl.to(state, { frame: count, duration: 1, onUpdate: render }, 0);
    const slot = 0.8 / steps.length;
    steps.forEach((li, i) => {
      tl.fromTo(li, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: slot * 0.3 }, i * slot)
        .to(li, { opacity: 0.25, y: -6, duration: slot * 0.25 }, i * slot + slot * 0.75);
    });
    tl.fromTo(final, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.12 }, 0.84);
  });
})();
