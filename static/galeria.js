// Galeria 3D: mostra uma peça de cada vez, com pontos numerados que abrem uma explicação.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

const PECAS = JSON.parse(document.getElementById("galeria-dados").textContent);
const $ = (id) => document.getElementById(id);
const canvas = $("g-canvas"), palco = canvas.parentElement, marcasEl = $("g-marcas");
const reduzir = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Renderizador e cena
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.8;
const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 200);
const key = new THREE.DirectionalLight(0xfff4e8, 2.0);
key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0003; key.shadow.normalBias = 0.02;
scene.add(key, key.target, new THREE.HemisphereLight(0xbfd4ff, 0x2a2622, 0.55));
const rim = new THREE.DirectionalLight(0x8fd8ff, 0.9); scene.add(rim);
const chao = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.ShadowMaterial({ opacity: 0.35 }));
chao.rotation.x = -Math.PI / 2; chao.receiveShadow = true; scene.add(chao);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.dampingFactor = 0.08;
controls.autoRotate = !reduzir; controls.autoRotateSpeed = 0.8;
controls.enablePan = false;

const loader = new GLTFLoader();
loader.setMeshoptDecoder(MeshoptDecoder);
const cache = new Map();
let atual = null, modelo = null, mixer = null, pontos = [], sel = -1, voo = null;
const relogio = new THREE.Clock();

function tamanho() {
  const w = palco.clientWidth, h = palco.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
}
new ResizeObserver(tamanho).observe(palco);

// Põe o modelo à escala, centrado e assente no chão
function encaixar(obj, p) {
  const inner = new THREE.Group(); inner.add(obj);
  const pivot = new THREE.Group(); pivot.add(inner); pivot.updateMatrixWorld(true);
  inner.rotation.set(...(p.rot || [0, 0, 0]));
  let b = new THREE.Box3().setFromObject(inner);
  inner.scale.setScalar(p.escala || p.medida / b.getSize(new THREE.Vector3())[p.eixo]);
  pivot.updateMatrixWorld(true);
  b = new THREE.Box3().setFromObject(inner);
  const c = b.getCenter(new THREE.Vector3());
  inner.position.set(-c.x, -b.min.y, -c.z);
  pivot.updateMatrixWorld(true);
  return pivot;
}

function preparar(root, p) {
  const alu = new THREE.MeshStandardMaterial({ color: 0xa9aeb4, metalness: 1, roughness: 0.36 });
  const cobre = new THREE.MeshStandardMaterial({ color: 0xc27a45, metalness: 1, roughness: 0.3 });
  root.traverse((o) => {
    if (!o.isMesh) return;
    o.castShadow = o.receiveShadow = true;
    // a gravação do processador vem espelhada no modelo
    if (/^Laser.etched/.test(o.name) && o.material.map) { o.material = o.material.clone(); const m = o.material.map.clone(); m.wrapT = THREE.RepeatWrapping; m.repeat.y = -1; m.offset.y = 1; m.needsUpdate = true; o.material.map = m; }
    if (p.materiais === "cooler") o.material = o.name === "Object_3" ? cobre : alu;
  });
}

async function obter(p, aoProgresso) {
  if (cache.has(p.slug)) return cache.get(p.slug);
  const gltf = await loader.loadAsync(`/galeria/modelos/${p.ficheiro}?v=6`, (e) => e.total && aoProgresso(e.loaded / e.total));
  let raiz = gltf.scene;
  if (p.no) { const n = raiz.getObjectByName(p.no); if (n) { raiz = n.clone(true); raiz.position.set(0, 0, 0); } }
  preparar(raiz, p);
  const pivot = encaixar(raiz, p);
  const item = { pivot, anim: p.animar ? gltf.animations : [], raiz: gltf.scene };
  cache.set(p.slug, item);
  return item;
}

// Pontos: procura a superfície do modelo a partir de fora, na direção indicada
const ray = new THREE.Raycaster();
function calcularPontos(p, pivot) {
  const b = new THREE.Box3().setFromObject(pivot), size = b.getSize(new THREE.Vector3()), diag = size.length();
  const centro = b.getCenter(new THREE.Vector3());
  return p.pontos.map((pt) => {
    if (pt.parte) {   // o ponto fica no centro das malhas cujo nome começa por "parte"
      const chave = pt.parte.replace(/\s+/g, "_"), caixa = new THREE.Box3();
      pivot.traverse((o) => { if (o.isMesh && o.name.replace(/\s+/g, "_").startsWith(chave)) caixa.expandByObject(o); });
      if (!caixa.isEmpty()) {
        let pos;
        if (pt.em) {   // posição dentro da parte (0–1 em cada eixo), para afastar pontos vizinhos
          const tam = caixa.getSize(new THREE.Vector3());
          pos = new THREE.Vector3(caixa.min.x + pt.em[0] * tam.x, caixa.min.y + pt.em[1] * tam.y, caixa.min.z + pt.em[2] * tam.z);
        } else {
          pos = caixa.getCenter(new THREE.Vector3());
          pos.y = Math.max(pos.y, caixa.max.y - 0.002);
        }
        const normal = pos.clone().sub(centro); normal.y += size.y * 0.15;
        return { ...pt, pos, normal: normal.normalize() };
      }
    }
    const alvo = new THREE.Vector3(b.min.x + pt.p[0] * size.x, b.min.y + pt.p[1] * size.y, b.min.z + pt.p[2] * size.z);
    let pos = alvo.clone(), normal = null;
    if (pt.dir) {
      const d = new THREE.Vector3(...pt.dir).normalize();
      ray.set(alvo.clone().addScaledVector(d, diag), d.clone().negate());
      const hit = ray.intersectObject(pivot, true)[0];
      if (hit) pos = hit.point;
      normal = d;
    }
    return { ...pt, pos, normal };
  });
}

function criarMarcas() {
  marcasEl.innerHTML = "";
  const lista = $("g-lista"); lista.innerHTML = "";
  pontos.forEach((pt, i) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "g-marca"; b.textContent = i + 1; b.setAttribute("aria-label", `${i + 1}. ${pt.titulo}`);
    b.addEventListener("click", () => escolher(i));
    marcasEl.appendChild(b); pt.el = b;
    const li = document.createElement("li");
    li.innerHTML = `<button type="button"><span>${i + 1}</span>${pt.titulo}</button>`;
    li.firstChild.addEventListener("click", () => escolher(i));
    lista.appendChild(li); pt.item = li.firstChild;
  });
}

function vistaInicial(p, pivot) {
  const b = new THREE.Box3().setFromObject(pivot), centro = b.getCenter(new THREE.Vector3()), raio = b.getSize(new THREE.Vector3()).length() / 2;
  const dir = new THREE.Vector3(...(p.vista || [1, 0.6, 1])).normalize();
  const dist = raio / Math.sin((camera.fov * Math.PI) / 360) * 1.05;
  return { pos: centro.clone().addScaledVector(dir, dist), alvo: centro, raio };
}

function voar(pos, alvo, dur = 0.9) {
  voo = { de: camera.position.clone(), deAlvo: controls.target.clone(), pos, alvo, t0: performance.now(), dur: reduzir ? 0.01 : dur };
}

function escolher(i) {
  sel = i;
  const pt = pontos[i];
  pontos.forEach((q, j) => { q.el.classList.toggle("on", j === i); q.item.setAttribute("aria-current", String(j === i)); });
  $("g-ponto").hidden = false;
  $("g-ponto-num").textContent = i + 1;
  $("g-ponto-titulo").textContent = pt.titulo;
  $("g-ponto-texto").textContent = pt.texto;
  $("g-fs-titulo").textContent = `${i + 1}. ${pt.titulo}`; $("g-fs-texto").textContent = pt.texto; $("g-fs-info").hidden = false;
  setRodar(false);
  const v = atual.vista;
  const dir = pt.normal ? pt.normal.clone().add(new THREE.Vector3(0, 0.35, 0)).normalize() : camera.position.clone().sub(controls.target).normalize();
  voar(pt.pos.clone().addScaledVector(dir, v.raio * 1.25), pt.pos.clone());
}

function setRodar(on) {
  controls.autoRotate = on && !reduzir;
  $("g-rodar").setAttribute("aria-pressed", String(controls.autoRotate));
}

async function mostrar(slug) {
  const p = PECAS.find((x) => x.slug === slug) || PECAS[0];
  document.querySelectorAll(".g-aba").forEach((a) => a.setAttribute("aria-pressed", String(a.dataset.slug === p.slug)));
  $("g-nome").textContent = p.nome; $("g-resumo").textContent = p.resumo;
  $("g-ponto").hidden = true; $("g-fs-info").hidden = true; sel = -1;
  $("g-credito").innerHTML = p.credito ? `Modelo 3D: <a href="${p.credito.url}" target="_blank" rel="noopener">${p.credito.titulo}</a>, de ${p.credito.autor} (CC BY 4.0, Sketchfab).` : "Modelos 3D: ATC Formação.";
  if (history.replaceState) history.replaceState(null, "", `#${p.slug}`);
  $("g-carregar").hidden = false; $("g-progresso").style.width = "0%";
  if (modelo) scene.remove(modelo);
  marcasEl.innerHTML = ""; $("g-lista").innerHTML = "";
  let item;
  try {
    item = await obter(p, (f) => ($("g-progresso").style.width = `${Math.round(f * 100)}%`));
  } catch (e) {
    $("g-carregar").querySelector("span").textContent = "Não foi possível carregar o modelo. Verifique a ligação e tente outra vez.";
    return;
  }
  if (location.hash.slice(1) !== p.slug) return;   // entretanto escolheu outra peça
  modelo = item.pivot; scene.add(modelo);
  mixer = null;
  if (item.anim.length) {
    mixer = new THREE.AnimationMixer(item.raiz);
    const clip = item.anim.find((a) => /600/.test(a.name)) || item.anim[0];
    mixer.clipAction(clip).play();
  }
  atual = { p, vista: vistaInicial(p, modelo) };
  const r = atual.vista.raio;
  key.position.copy(atual.vista.alvo).add(new THREE.Vector3(-r * 2, r * 4, r * 3)); key.target.position.copy(atual.vista.alvo);
  Object.assign(key.shadow.camera, { left: -r * 2, right: r * 2, top: r * 2, bottom: -r * 2, near: 0.1, far: r * 12 }); key.shadow.camera.updateProjectionMatrix();
  rim.position.copy(atual.vista.alvo).add(new THREE.Vector3(r * 3, r * 2, -r * 3));
  controls.minDistance = r * 0.35; controls.maxDistance = r * 6;
  camera.near = r / 200; camera.far = r * 40; camera.updateProjectionMatrix();
  camera.position.copy(atual.vista.pos); controls.target.copy(atual.vista.alvo); controls.update();
  pontos = calcularPontos(p, modelo);
  criarMarcas();
  setRodar(true);
  $("g-carregar").hidden = true;
}

document.querySelectorAll(".g-aba").forEach((a) => a.addEventListener("click", () => { location.hash = a.dataset.slug; }));
addEventListener("hashchange", () => mostrar(location.hash.slice(1)));
$("g-repor").addEventListener("click", () => { if (!atual) return; voar(atual.vista.pos.clone(), atual.vista.alvo.clone()); pontos.forEach((q) => { q.el.classList.remove("on"); q.item.setAttribute("aria-current", "false"); }); $("g-ponto").hidden = true; $("g-fs-info").hidden = true; sel = -1; setRodar(true); });
$("g-rodar").addEventListener("click", () => setRodar(!controls.autoRotate));
// Ecrã inteiro (com recurso a uma janela que ocupa o ecrã quando o navegador não o permite)
$("g-ecra").addEventListener("click", () => {
  const dentro = document.fullscreenElement || palco.classList.contains("g-cheio");
  if (dentro) { if (document.fullscreenElement) document.exitFullscreen(); palco.classList.remove("g-cheio"); $("g-ecra").textContent = "⛶ Ecrã inteiro"; return; }
  $("g-ecra").textContent = "✕ Sair";
  const pedir = palco.requestFullscreen || palco.webkitRequestFullscreen;
  if (pedir) Promise.resolve(pedir.call(palco)).catch(() => palco.classList.add("g-cheio")); else palco.classList.add("g-cheio");
});
document.addEventListener("fullscreenchange", () => { $("g-ecra").textContent = document.fullscreenElement ? "✕ Sair" : "⛶ Ecrã inteiro"; });
addEventListener("keydown", (e) => { if (e.key === "Escape") { palco.classList.remove("g-cheio"); $("g-ecra").textContent = "⛶ Ecrã inteiro"; } });
$("g-ant").addEventListener("click", () => pontos.length && escolher((sel - 1 + pontos.length) % pontos.length));
$("g-seg").addEventListener("click", () => pontos.length && escolher((sel + 1) % pontos.length));
controls.addEventListener("start", () => { voo = null; setRodar(false); });

// Ciclo de desenho (pára quando o separador está escondido)
const v = new THREE.Vector3(), paraCam = new THREE.Vector3();
function ciclo() {
  requestAnimationFrame(ciclo);
  if (document.hidden) return;
  const dt = Math.min(relogio.getDelta(), 0.05);
  if (voo) {
    const k = Math.min(1, (performance.now() - voo.t0) / (voo.dur * 1000)), e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
    camera.position.lerpVectors(voo.de, voo.pos, e); controls.target.lerpVectors(voo.deAlvo, voo.alvo, e);
    if (k >= 1) voo = null;
  }
  controls.update();
  if (mixer) mixer.update(dt);
  renderer.render(scene, camera);
  const w = canvas.clientWidth, h = canvas.clientHeight;
  for (const pt of pontos) {
    v.copy(pt.pos).project(camera);
    const fora = v.z > 1 || Math.abs(v.x) > 1.05 || Math.abs(v.y) > 1.05;
    pt.el.style.display = fora ? "none" : "";
    pt.el.style.transform = `translate(${(v.x * 0.5 + 0.5) * w}px, ${(-v.y * 0.5 + 0.5) * h}px)`;
    const atras = pt.normal && paraCam.copy(camera.position).sub(pt.pos).dot(pt.normal) < 0;
    pt.el.classList.toggle("atras", !!atras);
  }
}
tamanho();
ciclo();
mostrar(location.hash.slice(1) || PECAS[0].slug);
