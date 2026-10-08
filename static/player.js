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
    function send() {
      if (!v.duration) return;
      lastSent = Date.now();
      var s = '';
      for (var i = 0; i < Math.ceil(v.duration); i++) s += seen[i] === '1' ? '1' : '0';
      post('/api/progresso', { lesson: lesson, media: v.dataset.media || "original", pos: v.currentTime, seen: s, dur: v.duration })
        .then(function (r) {
          if (r.completed && !done) { done = true; status.textContent = '✓ Aula concluída'; status.className = 'okmsg'; }
        }).catch(function () {});
    }
    // Só conta o que foi realmente reproduzido: saltos para a frente não marcam segundos como vistos.
    v.addEventListener('timeupdate', function () {
      var t = v.currentTime, d = t - last;
      if (!v.seeking && d > 0 && d <= 1 + v.playbackRate) {
        for (var i = Math.floor(last); i <= Math.floor(t); i++) seen[i] = '1';
      }
      last = t;
      if (Date.now() - lastSent > 10000) send();
    });
    v.addEventListener('seeking', function () { last = v.currentTime; });
    v.addEventListener('seeked', function () { last = v.currentTime; });
    v.addEventListener('pause', send);
    v.addEventListener('ended', send);
    window.addEventListener('pagehide', send);
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
