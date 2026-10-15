// Página inicial pública: "Do hardware à rede". Duas histórias presas ao scroll (GSAP + ScrollTrigger).
// Sem movimento (prefers-reduced-motion) ou sem GSAP, mostra os diagramas no estado final.
(() => {
  const parts = [...document.querySelectorAll('.pc-part')];
  const partItems = [...document.querySelectorAll('.lp-parts li')];
  const layers = [...document.querySelectorAll('.lp-osi li')];
  const nodes = Object.fromEntries([...document.querySelectorAll('.net-node')].map((n) => [n.id.slice(3), n]));
  const caption = document.querySelector('.net-caption');
  const packet = document.getElementById('net-packet');
  const track = document.getElementById('net-path');
  const intro = caption ? caption.textContent : '';

  const stages = [ // [início, fim, nó, camadas acesas, legenda]  (progresso da viagem 0–1)
    [0, 0.17, 'pc', null, 'No computador, os dados descem as sete camadas e ganham cabeçalhos: porta, endereço IP, endereço MAC.'],
    [0.17, 0.3, 'switch', [1, 2], 'O switch lê o endereço MAC e entrega o pacote dentro da rede local. Camada 2.'],
    [0.3, 0.52, 'router', [1, 2, 3], 'O router lê o endereço IP e escolhe o caminho para fora da rede local. Camada 3.'],
    [0.52, 0.8, 'internet', [1, 2, 3], 'Na Internet, dezenas de routers passam o pacote de rede em rede até ao destino.'],
    [0.8, 1.01, 'servidor', null, 'No servidor, os dados sobem as sete camadas até chegarem à aplicação.'],
  ];

  const lit = (set) => layers.forEach((li) => li.classList.toggle('on', set.includes(+li.dataset.camada)));
  const markParts = (n) => partItems.forEach((li, i) => li.classList.toggle('on', i < n));

  function setNetwork(p) { // p: progresso da secção (0–1)
    const travel = gsap.utils.clamp(0, 1, (p - 0.12) / 0.76);
    const stage = stages.find(([a, b]) => travel >= a && travel < b) || stages[stages.length - 1];
    Object.entries(nodes).forEach(([id, n]) => n.classList.toggle('on', id === stage[2]));
    if (p < 0.12) {           // encapsulamento: 7 → 1
      const k = Math.floor((p / 0.12) * 7);
      lit([7, 6, 5, 4, 3, 2, 1].slice(0, k + 1));
    } else if (p > 0.88) {    // desencapsulamento: 1 → 7
      const k = Math.floor(((p - 0.88) / 0.12) * 7);
      lit([1, 2, 3, 4, 5, 6, 7].slice(0, k + 1));
    } else lit(stage[3] || [1]);
    if (caption) caption.textContent = p <= 0.001 ? intro : stage[4];
  }

  const exploded = () => {
    parts.forEach((g) => g.setAttribute('transform', `translate(${g.dataset.dx} ${g.dataset.dy})`));
    document.documentElement.classList.add('lp-static');
    markParts(parts.length);
  };

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!window.gsap || !window.ScrollTrigger || reduce) {
    exploded();
    layers.forEach((li) => li.classList.add('on'));
    return;
  }
  gsap.registerPlugin(ScrollTrigger, MotionPathPlugin, DrawSVGPlugin);
  document.documentElement.classList.add('lp-motion');

  // Parte 1: a tampa sai e as peças afastam-se uma a uma, com as etiquetas.
  const hw = gsap.timeline({
    defaults: { ease: 'power2.inOut' },
    scrollTrigger: {
      trigger: '#por-dentro', start: 'top top', end: () => '+=' + window.innerHeight * 2.2, pin: true, scrub: 0.8,
      onUpdate: (st) => { const t = st.progress * hw.duration(); markParts(parts.filter((_, i) => t >= 1.4 + i * 0.7).length); },
    },
  });
  hw.to('#pc-tampa', { x: 240, opacity: 0, duration: 1 })
    .to('.pc-case', { opacity: 0.35, duration: 0.6 }, '<0.4');
  parts.forEach((g, i) => {
    hw.to(g, { x: +g.dataset.dx, y: +g.dataset.dy, duration: 1 }, 1 + i * 0.7)
      .to(g.querySelector('.pc-label'), { opacity: 1, duration: 0.4 }, '>-0.3');
  });
  hw.to({}, { duration: 0.6 });

  // Parte 2: o caminho desenha-se e o pacote percorre-o, com as camadas OSI ao lado.
  gsap.set(track, { drawSVG: '0%' });
  gsap.set(packet, { attr: { cx: 0, cy: 0 }, x: 70, y: 250 });
  const net = gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: {
      trigger: '.lp-net', start: 'top top', end: () => '+=' + window.innerHeight * 2.6, pin: true, scrub: 0.6,
      onUpdate: (st) => setNetwork(st.progress),
    },
  });
  net.to({}, { duration: 0.12 })
    .to(track, { drawSVG: '100%', duration: 0.76 }, 0.12)
    .to(packet, { motionPath: { path: track }, duration: 0.76 }, 0.12)
    .to({}, { duration: 0.12 });
  setNetwork(0);
})();
