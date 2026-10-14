// Primeira visita: tocar na Helena ou no Miguel mostra e toca as boas-vindas desse guia no próprio cartão.
(() => {
  const cartoes = [...document.querySelectorAll('.primeira-visita .presenter-option')];
  function mostrar(cartao) {
    cartoes.forEach(outro => {
      const v = outro.querySelector('video');
      if (outro !== cartao && v) { v.pause(); v.hidden = true; outro.querySelector('img').hidden = false; }
    });
    const video = cartao.querySelector('video');
    if (!video) return;
    cartao.querySelector('img').hidden = true;
    video.hidden = false;
    if (video.paused) { video.currentTime = video.ended ? 0 : video.currentTime; video.play().catch(() => {}); }
    else video.pause();
  }
  cartoes.forEach(cartao => {
    cartao.addEventListener('click', e => {
      if (e.target.matches('input')) return;   // o clique no rótulo já chega ao botão de escolha
      mostrar(cartao);
    });
    cartao.querySelector('input').addEventListener('keydown', e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); e.target.checked = true; mostrar(cartao); } });
  });
})();
