(() => {
  const path = window.location.pathname;
  const active = path.startsWith('/admin') ? '/admin' : path === '/conta' ? '/conta' : window.location.hash === '#catalogo' ? '/#catalogo' : '/';
  function markNavigation(href) {
    document.querySelectorAll('.sidebar nav a').forEach(link => {
      if (link.getAttribute('href') === href) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }
  markNavigation(active);
  window.addEventListener('hashchange', () => markNavigation(window.location.hash === '#catalogo' ? '/#catalogo' : active));
  const search = document.getElementById('course-search');
  if (search) {
    const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    search.addEventListener('input', () => {
      let visible = 0;
      document.querySelectorAll('#catalog-courses .course').forEach(card => {
        card.hidden = !normalize(card.textContent).includes(normalize(search.value.trim()));
        if (!card.hidden) visible++;
      });
      document.getElementById('catalog-empty').hidden = visible > 0;
    });
  }

  // Vídeos do guia por ordem: o seguinte só abre quando o anterior foi visto até ao fim (ou quase).
  const utilizador = document.body.dataset.u || '';
  const chave = video => `atc-clip-visto:${utilizador}:${(video.querySelector('source') || video).getAttribute('src')}`;
  const lembrar = video => { try { localStorage.setItem(chave(video), '1'); } catch (e) { /* sem armazenamento: vale só nesta página */ } };
  const visto = video => { try { return localStorage.getItem(chave(video)) === '1'; } catch (e) { return false; } };
  document.querySelectorAll('.guide-clips[data-ordem]').forEach(grupo => {
    const clips = [...grupo.querySelectorAll('.guide-clip')];
    const seccao = grupo.closest('section');
    const proximo = seccao && seccao.querySelector('[data-proximo], [data-seguinte]');
    const titulo = clip => (clip.querySelector('figcaption b') || {}).textContent || 'o vídeo anterior';
    const vistos = clips.map(clip => visto(clip.querySelector('video')));
    function trancar(clip, i) {
      const video = clip.querySelector('video');
      clip.classList.add('trancado');
      video.controls = false;
      video.setAttribute('tabindex', '-1');
      video.setAttribute('aria-disabled', 'true');
      const aviso = document.createElement('div');
      aviso.className = 'clip-aviso';
      aviso.setAttribute('role', 'note');
      aviso.innerHTML = `<span aria-hidden="true">🔒</span><b>Vídeo ${i + 1}</b><span>Abre quando terminar «${titulo(clips[i - 1])}».</span>`;
      clip.insertBefore(aviso, video.nextSibling);
      video.addEventListener('play', () => { if (clip.classList.contains('trancado')) video.pause(); });
    }
    function abrir(i) {
      const clip = clips[i];
      if (!clip || !clip.classList.contains('trancado')) return;
      const video = clip.querySelector('video');
      clip.classList.remove('trancado');
      clip.classList.add('desbloqueado');
      video.controls = true;
      video.removeAttribute('tabindex');
      video.removeAttribute('aria-disabled');
      const aviso = clip.querySelector('.clip-aviso');
      if (aviso) aviso.remove();
      clip.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    function concluir() {
      if (!proximo) return;
      proximo.classList.add('destaque');
      const dica = seccao.querySelector('.next-hint, .proximo-dica');
      if (dica) dica.textContent = 'Muito bem! Já viu os vídeos. Continue para a aula.';
    }
    clips.forEach((clip, i) => {
      const video = clip.querySelector('video');
      const numero = document.createElement('span');
      numero.className = 'clip-numero';
      numero.textContent = `${i + 1} de ${clips.length}`;
      clip.querySelector('figcaption').prepend(numero);
      if (i > 0 && !vistos.slice(0, i).every(Boolean)) trancar(clip, i);
      let marcado = false;
      const marcar = () => {
        if (marcado) return;
        marcado = true;
        lembrar(video);
        clip.classList.add('visto');
        if (i + 1 < clips.length) abrir(i + 1); else concluir();
      };
      video.addEventListener('ended', marcar);
      video.addEventListener('timeupdate', () => { if (video.duration && video.currentTime / video.duration >= 0.95) marcar(); });
      if (vistos[i]) clip.classList.add('visto');
    });
    if (vistos.every(Boolean)) concluir();
  });

  // Som dos vídeos: «Com som» (narração) ou «Só legendas» (sem som, legendas ligadas). A escolha fica guardada.
  const lerSom = () => { try { return localStorage.getItem('atc-som') || 'on'; } catch (e) { return 'on'; } };
  function aplicarSom(modo) {
    document.querySelectorAll('video.aula-video').forEach(video => {
      video.muted = modo === 'off';
      [...video.textTracks].forEach(t => { if (modo === 'off') t.mode = 'showing'; });
    });
    document.querySelectorAll('.som-escolha button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.som === modo)));
  }
  document.querySelectorAll('.som-escolha button').forEach(b => b.addEventListener('click', () => {
    try { localStorage.setItem('atc-som', b.dataset.som); } catch (e) { /* vale só nesta página */ }
    aplicarSom(b.dataset.som);
  }));
  if (document.querySelector('.som-escolha')) aplicarSom(lerSom());

  // Botão grande de reproduzir sobre os vídeos das aulas: mais fácil de encontrar do que o ícone pequeno.
  document.querySelectorAll('.player video').forEach(video => {
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'play-grande';
    botao.innerHTML = '<span aria-hidden="true">▶</span> Ver o vídeo';
    video.parentElement.appendChild(botao);
    botao.addEventListener('click', () => { video.play().catch(() => {}); });
    video.addEventListener('play', () => { botao.hidden = true; });
  });

  // Quando a aula fica concluída, o próximo passo abre sem recarregar a página.
  document.addEventListener('aula-concluida', () => {
    const cartao = document.querySelector('[data-proximo-passo]');
    if (!cartao) return;
    cartao.classList.add('pronto');
    const dica = cartao.querySelector('.proximo-dica');
    if (dica) dica.textContent = 'Muito bem! Já pode avançar para o passo seguinte.';
    const botao = cartao.querySelector('[data-seguinte]');
    if (botao) { botao.removeAttribute('aria-disabled'); botao.removeAttribute('tabindex'); botao.classList.add('destaque'); }
    cartao.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
  document.querySelectorAll('[data-seguinte][aria-disabled="true"]').forEach(a => a.addEventListener('click', e => {
    e.preventDefault();
    const dica = a.closest('[data-proximo-passo]').querySelector('.proximo-dica');
    if (dica) { dica.classList.remove('abanar'); void dica.offsetWidth; dica.classList.add('abanar'); }
  }));
})();
