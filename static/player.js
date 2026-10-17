// Leitor de vídeo: retoma onde parou, regista o progresso e liga o assistente de estudo.
(function () {
  var csrf = document.querySelector('meta[name=csrf]').content;
  function post(url, data) {
    return fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF': csrf },
      body: JSON.stringify(data)
    }).then(function (r) { return r.json(); });
  }

  var v = document.getElementById('v');
  var status = document.getElementById('status');
  if (v) {
    var lesson = v.dataset.lesson;
    var seen = (v.dataset.seen || '').split('');  // um carácter por segundo: '1' = visto
    var last = 0, lastSent = 0, done = /✓/.test(status.textContent);
    v.addEventListener('loadedmetadata', function () {
      var pos = parseFloat(v.dataset.pos) || 0;
      if (pos > 5 && pos < v.duration - 5) v.currentTime = pos;
      last = v.currentTime;
    });
    var cues = [].slice.call(document.querySelectorAll('.transcript .cue'));
    cues.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var st = parseFloat(btn.dataset.start);
        if (!isNaN(st)) {
          v.currentTime = st;
          v.play().catch(function () {});
        }
      });
    });
    function syncCues(t) {
      if (!cues.length) return;
      for (var i = 0; i < cues.length; i++) {
        var s = parseFloat(cues[i].dataset.start), e = parseFloat(cues[i].dataset.end);
        var on = t >= s && t <= e;
        if (on !== cues[i].classList.contains('ativo')) {
          cues[i].classList.toggle('ativo', on);
          if (on && cues[i].closest('details[open]')) {
            cues[i].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          }
        }
      }
    }
    function send() {
      if (!v.duration) return;
      lastSent = Date.now();
      var s = '';
      for (var i = 0; i < Math.ceil(v.duration); i++) s += seen[i] === '1' ? '1' : '0';
      post('/api/progresso', { lesson: lesson, media: v.dataset.media || "original", pos: v.currentTime, seen: s, dur: v.duration })
        .then(function (r) {
          if (r.completed && !done) {
            done = true;
            status.textContent = '✓ Aula concluída — muito bem!';
            status.className = 'okmsg celebrar';
            document.dispatchEvent(new Event('aula-concluida'));
          }
        }).catch(function () {});
    }
    // Só conta o que foi realmente reproduzido: saltos para a frente não marcam segundos como vistos.
    v.addEventListener('timeupdate', function () {
      var t = v.currentTime, d = t - last;
      if (!v.seeking && d > 0 && d <= 1 + v.playbackRate) {
        for (var i = Math.floor(last); i <= Math.floor(t); i++) seen[i] = '1';
      }
      last = t;
      syncCues(t);
      if (Date.now() - lastSent > 10000) send();
    });
    v.addEventListener('seeking', function () { last = v.currentTime; syncCues(v.currentTime); });
    v.addEventListener('seeked', function () { last = v.currentTime; syncCues(v.currentTime); });
    v.addEventListener('pause', send);
    v.addEventListener('ended', send);
    window.addEventListener('pagehide', send);
  }

  var cinemaBtn = document.getElementById('cinema-toggle');
  if (cinemaBtn) {
    cinemaBtn.addEventListener('click', function () {
      var on = document.body.classList.toggle('cinema');
      cinemaBtn.setAttribute('aria-pressed', String(on));
      cinemaBtn.textContent = on ? '⤡ Sair do cinema' : '⤢ Modo cinema';
    });
  }

  var form = document.getElementById('ask');
  if (form) {
    var out = document.getElementById('answer');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = form.querySelector('button');
      btn.disabled = true; out.hidden = false; out.textContent = 'A pensar…';
      post('/api/assistente', { lesson: v.dataset.lesson, q: form.q.value })
        .then(function (r) { out.textContent = r.resposta || r.erro; })
        .catch(function () { out.textContent = 'Não foi possível contactar o assistente.'; })
        .then(function () { btn.disabled = false; });
    });
  }
})();
