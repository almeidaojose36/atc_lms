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
    const proximo = seccao && seccao.querySelector('[data-proximo]');
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
      const dica = seccao.querySelector('.next-hint');
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
})();
