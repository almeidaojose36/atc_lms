// Guia por voz: grava a pergunta, envia-a ao LMS e toca a resposta na voz do guia escolhido.
(function () {
  var painel = document.getElementById('voz');
  if (!painel) return;
  var csrf = document.querySelector('meta[name=csrf]').content;
  var url = '/api/voz/' + painel.dataset.lesson;
  var mic = painel.querySelector('.voz-mic'), rotulo = painel.querySelector('.voz-rotulo');
  var estado = painel.querySelector('.voz-estado'), conversa = painel.querySelector('.voz-conversa');
  var escrever = painel.querySelector('.voz-escrever');
  var gravador = null, pedacos = [], limite = null, ocupado = false, tocando = null;
  var MAX_MS = 20000;

  var onda = painel.querySelector('.voz-onda');
  var ondaCtx = onda ? onda.getContext('2d') : null;
  var audioCtx = null, rafId = 0;

  function desenharOnda(analyser, cor) {
    if (!ondaCtx || !onda) return;
    cancelAnimationFrame(rafId);
    var dados = analyser ? new Uint8Array(analyser.frequencyBinCount) : null;
    var t0 = performance.now();
    function ciclo(t) {
      var w = onda.width, h = onda.height, cx = w / 2, cy = h / 2;
      ondaCtx.clearRect(0, 0, w, h);
      if (dados) analyser.getByteFrequencyData(dados);
      var barras = 36, rBase = 72;
      for (var i = 0; i < barras; i++) {
        var val = dados ? dados[i % dados.length] / 255 : (0.25 + 0.2 * Math.sin((t - t0) / 160 + i * 0.5));
        var comp = 6 + val * 28;
        var ang = (i / barras) * Math.PI * 2 - Math.PI / 2;
        var x1 = cx + Math.cos(ang) * rBase, y1 = cy + Math.sin(ang) * rBase;
        var x2 = cx + Math.cos(ang) * (rBase + comp), y2 = cy + Math.sin(ang) * (rBase + comp);
        ondaCtx.beginPath();
        ondaCtx.moveTo(x1, y1);
        ondaCtx.lineTo(x2, y2);
        ondaCtx.strokeStyle = cor;
        ondaCtx.lineWidth = 3.2;
        ondaCtx.lineCap = 'round';
        ondaCtx.globalAlpha = 0.35 + val * 0.65;
        ondaCtx.stroke();
      }
      ondaCtx.globalAlpha = 1;
      rafId = requestAnimationFrame(ciclo);
    }
    rafId = requestAnimationFrame(ciclo);
  }
  function limparOnda() {
    cancelAnimationFrame(rafId);
    if (ondaCtx && onda) ondaCtx.clearRect(0, 0, onda.width, onda.height);
    painel.classList.remove('a-falar');
  }
  function ligarAnalisadorStream(stream, cor) {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) { desenharOnda(null, cor); return; }
      if (!audioCtx) audioCtx = new AC();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      var src = audioCtx.createMediaStreamSource(stream);
      var an = audioCtx.createAnalyser();
      an.fftSize = 128;
      src.connect(an);
      desenharOnda(an, cor);
    } catch (e) { desenharOnda(null, cor); }
  }
  function ligarAnalisadorAudio(el, cor) {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) { desenharOnda(null, cor); return; }
      if (!audioCtx) audioCtx = new AC();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      var src = audioCtx.createMediaElementSource(el);
      var an = audioCtx.createAnalyser();
      an.fftSize = 128;
      src.connect(an);
      an.connect(audioCtx.destination);
      desenharOnda(an, cor);
    } catch (e) { desenharOnda(null, cor); }
  }

  function mostrar(msg) { estado.textContent = msg || ''; }
  function balao(classe, texto) {
    var li = document.createElement('li'); li.className = classe; li.textContent = texto;
    conversa.appendChild(li); li.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); return li;
  }
  function tocar(src) {
    if (!src) return;
    var aula = document.getElementById('v'); if (aula && !aula.paused) aula.pause();
    if (tocando) { tocando.pause(); limparOnda(); }
    tocando = new Audio(src);
    tocando.addEventListener('play', function () {
      painel.classList.add('a-falar');
      ligarAnalisadorAudio(tocando, '#da6d24');
    });
    tocando.addEventListener('ended', limparOnda);
    tocando.addEventListener('pause', limparOnda);
    tocando.play().catch(function () { limparOnda(); });
  }
  function enviar(corpo, tipo) {
    ocupado = true; mic.disabled = true; mostrar('A pensar…');
    var headers = { 'X-CSRF': csrf, 'Content-Type': tipo };
    return fetch(url, { method: 'POST', credentials: 'same-origin', headers: headers, body: corpo })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.erro || 'Erro'); return j; }); })
      .then(function (j) {
        if (j.pergunta) balao('voz-pergunta', j.pergunta);
        var b = balao('voz-resposta', j.resposta);
        if (j.audio) {
          var ouvir = document.createElement('button'); ouvir.type = 'button'; ouvir.className = 'linkbtn';
          ouvir.textContent = '▶ Ouvir outra vez'; ouvir.onclick = function () { tocar(j.audio); };
          b.appendChild(ouvir); tocar(j.audio);
        }
        mostrar('');
      })
      .catch(function (e) { mostrar(e.message || 'Não foi possível contactar o guia.'); })
      .then(function () { ocupado = false; mic.disabled = false; });
  }
  function tipoGravacao() {
    var tipos = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    for (var i = 0; i < tipos.length; i++) if (window.MediaRecorder && MediaRecorder.isTypeSupported(tipos[i])) return tipos[i];
    return '';
  }
  function parar() {
    clearTimeout(limite);
    if (gravador && gravador.state === 'recording') gravador.stop();
  }
  function comecar() {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      mostrar('Este navegador não permite gravar. Escreva a pergunta abaixo.'); return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      var tipo = tipoGravacao();
      gravador = tipo ? new MediaRecorder(stream, { mimeType: tipo }) : new MediaRecorder(stream);
      pedacos = [];
      gravador.ondataavailable = function (e) { if (e.data.size) pedacos.push(e.data); };
      gravador.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        limparOnda();
        painel.classList.remove('a-gravar'); mic.setAttribute('aria-pressed', 'false'); rotulo.textContent = 'Falar';
        var blob = new Blob(pedacos, { type: (gravador.mimeType || 'audio/webm') });
        if (blob.size < 2000) { mostrar('Não ouvi nada. Carregue no microfone e fale um pouco mais alto.'); return; }
        enviar(blob, blob.type.split(';')[0] || 'audio/webm');
      };
      gravador.start();
      painel.classList.add('a-gravar'); mic.setAttribute('aria-pressed', 'true'); rotulo.textContent = 'Enviar';
      ligarAnalisadorStream(stream, '#c0392b');
      mostrar('A ouvir… carregue outra vez quando terminar.');
      limite = setTimeout(parar, MAX_MS);
    }).catch(function () { mostrar('Sem acesso ao microfone. Autorize o microfone no navegador ou escreva a pergunta.'); });
  }

  mic.addEventListener('click', function () {
    if (ocupado) return;
    if (gravador && gravador.state === 'recording') { parar(); return; }
    if (tocando) { tocando.pause(); limparOnda(); }
    comecar();
  });
  escrever.addEventListener('submit', function (e) {
    e.preventDefault();
    var q = escrever.q.value.trim(); if (!q || ocupado) return;
    escrever.q.value = '';
    enviar(JSON.stringify({ q: q }), 'application/json');
  });
  // Saudação: aparece escrita; o áudio é pedido só se o formando carregar em «Ouvir».
  var ouvirSaudacao = painel.querySelector('.voz-saudacao button');
  if (ouvirSaudacao) ouvirSaudacao.addEventListener('click', function () {
    if (ocupado) return;
    fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF': csrf, 'Content-Type': 'application/json' },
                 body: JSON.stringify({ linha: 'saudacao' }) })
      .then(function (r) { return r.json(); }).then(function (j) { tocar(j.audio); }).catch(function () {});
  });
})();
