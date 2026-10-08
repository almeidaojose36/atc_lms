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
})();
