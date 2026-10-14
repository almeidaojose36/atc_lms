// Apresentações PowerPoint dos manuais ATC (uma por manual), com os avatares Helena e Miguel.
// Lê cursos/<curso>/manual/modulo-1.json e as imagens preparadas em _build/ (python3 preparar_imagens.py).
// Uso: node gerar_apresentacoes.js [curso ...]   → producao/apresentacoes/<Curso>_Modulo1.pptx
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const AQUI = __dirname;
const RAIZ = path.resolve(AQUI, "../..");
const BUILD = path.join(AQUI, "_build");
const CENAS = JSON.parse(fs.readFileSync(path.join(BUILD, "cenas.json"), "utf8"));
const W = 13.333, H = 7.5;

const CURSOS = {
  informatica: { farda: "camisa", cor: "1E6F8A", abre: "helena", ficheiro: "Informatica_Modulo1" },
  word: { farda: "blazer", cor: "2B579A", abre: "helena", ficheiro: "Word_Modulo1" },
  excel: { farda: "polo", cor: "217346", abre: "miguel", ficheiro: "Excel_Modulo1" },
  powerpoint: { farda: "casaco", cor: "C43E1C", abre: "helena", ficheiro: "PowerPoint_Modulo1" },
  outlook: { farda: "blazer", cor: "0F6CBD", abre: "miguel", ficheiro: "Outlook_Modulo1" },
  "comptia-a-plus": { farda: "polo", cor: "B5272D", abre: "miguel", ficheiro: "CompTIA_A+_Modulo1" },
  "comptia-network-plus": { farda: "casaco", cor: "1F5F99", abre: "helena", ficheiro: "CompTIA_Network+_Modulo1" },
};
const NOMES = { helena: "Helena", miguel: "Miguel" };
const outro = (g) => (g === "helena" ? "miguel" : "helena");

// ---------- texto ----------
const limpo = (s) => String(s).replace(/\*\*/g, "");
function runs(s, base = {}) {   // **negrito** → runs
  return String(s).split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((t) =>
    t.startsWith("**") ? { text: t.slice(2, -2), options: { ...base, bold: true } } : { text: t, options: { ...base } });
}
function linhas(texto, largura, pt) {   // estimativa de linhas (Calibri ~0,5 em por carácter)
  const porLinha = Math.max(8, Math.floor((largura - 0.15) * 72 / (pt * 0.56)));
  return limpo(texto).split("\n").reduce((n, p) => n + Math.max(1, Math.ceil(p.length / porLinha)), 0);
}
const altura = (texto, largura, pt, entre = 1.18) => linhas(texto, largura, pt) * pt * entre / 72 + 0.12;

async function dimensoes(f) { const m = await sharp(f).metadata(); return { w: m.width, h: m.height }; }
function caber(d, bx, by, bw, bh) {
  const r = Math.min(bw / d.w, bh / d.h); const w = d.w * r, h = d.h * r;
  return { x: bx + (bw - w) / 2, y: by + (bh - h) / 2, w, h };
}
const sombra = () => ({ type: "outer", color: "0B2137", opacity: 0.18, blur: 10, offset: 3, angle: 90 });

// ---------- apresentação ----------
async function gerar(slug) {
  const cfg = CURSOS[slug];
  const manual = JSON.parse(fs.readFileSync(path.join(RAIZ, "cursos", slug, "manual", "modulo-1.json"), "utf8"));
  const mod = manual.modules[0];
  const figDir = path.join(RAIZ, "cursos", slug, "manual", "figures");
  const cena = (g, lado, tom) => {
    const nome = `${cfg.farda}-${g}-${lado}-${tom}.jpg`;
    return { path: path.join(BUILD, "cenas", nome), borda: CENAS[nome].borda };
  };
  const avatar = (g) => path.join(BUILD, "avatares", `${cfg.farda}-${g}.png`);
  const LOGO = path.join(RAIZ, "static", "logo-600.png");

  const THEME = {
    name: "ATC Formação", headFontFace: "Cambria", bodyFontFace: "Calibri",
    colors: { dk1: "1D2733", lt1: "FFFFFF", dk2: "0B2137", lt2: "F2F4F7", accent1: "DA6D24", accent2: cfg.cor,
              accent3: "F08A3E", accent4: "5F6B78", accent5: "2E7D4F", accent6: "B3361F", hlink: "DA6D24", folHlink: "8A5A3C" },
  };
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = `${manual.course} · Módulo ${mod.num} · ${mod.title}`;
  pres.author = "ATC – Angbu Training Centre";
  pres.company = "ATC – Angbu Training Centre";
  pres.subject = "Apresentação do manual do formando";
  const C = pres.SchemeColor;
  const rodape = `ATC · Angbu Training Centre   |   ${manual.course} · Módulo ${mod.num}`;

  pres.defineSlideMaster({
    title: "Conteúdo", background: { color: "FFFFFF" },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.4, w: 11.2, h: 0.85, fontFace: "Cambria",
          fontSize: 30, bold: true, color: C.text2, align: "left", valign: "middle", margin: 0 }, text: "Título" } },
      { image: { x: 12.15, y: 0.42, w: 0.62, h: 0.62, path: LOGO } },
      { text: { text: rodape, options: { x: 0.6, y: 7.0, w: 9, h: 0.3, fontSize: 10, color: C.accent4, margin: 0 } } },
    ],
    slideNumber: { x: 12.2, y: 7.0, w: 0.55, h: 0.3, fontSize: 10, color: C.accent4, align: "right" },
  });
  pres.defineSlideMaster({
    title: "Cena", background: { color: "E8EAED" },
    objects: [{ text: { text: rodape, options: { x: 0.6, y: 7.0, w: 9, h: 0.3, fontSize: 10, color: C.accent4, margin: 0 } } }],
    slideNumber: { x: 12.2, y: 7.0, w: 0.55, h: 0.3, fontSize: 10, color: C.accent4, align: "right" },
  });
  pres.defineSlideMaster({ title: "Capa", background: { color: "0B2137" } });

  const seccao = (t) => pres.addSection({ title: t });
  let secAtual = "";
  const novo = (master, sec) => pres.addSlide({ masterName: master, sectionTitle: sec || secAtual });

  // área de texto de uma cena (o lado sem apresentador)
  function zona(c, lado) {
    if (lado === "dir") return { x: 0.6, w: c.borda * W - 1.0 };
    const x = c.borda * W + 0.45; return { x, w: W - 0.6 - x };
  }
  function eyebrow(s, texto, x, y, w, cor) {
    s.addText(texto.toUpperCase(), { x, y, w, h: 0.3, fontSize: 12, bold: true, charSpacing: 3, color: cor || C.accent1, margin: 0, isTextBox: true });
  }
  function dica(s, bloco, guia, x, y, w, h) {   // cartão com o avatar do guia
    const tipo = bloco.tip ? "tip" : bloco.note ? "note" : "warn";
    const rot = { tip: `Dica ${guia === "helena" ? "da" : "do"} ${NOMES[guia]}`, note: "Nota", warn: "Atenção" }[tipo];
    const fundo = tipo === "warn" ? "FBEDE6" : "F2F4F7";
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fundo }, line: { color: fundo }, objectName: "Cartão de dica" });
    const a = Math.min(0.85, h - 0.3);
    s.addImage({ path: avatar(guia), x: x + 0.2, y: y + (h - a) / 2, w: a, h: a, altText: `${NOMES[guia]}, guia virtual ATC` });
    s.addText([{ text: rot, options: { bold: true, color: tipo === "warn" ? C.accent6 : C.accent1, breakLine: true } },
               ...runs(bloco[tipo], { color: C.text1 })],
      { x: x + a + 0.38, y: y + 0.08, w: w - a - 0.55, h: h - 0.16, fontSize: dica.pt || 14, valign: "middle", margin: 0, isTextBox: true, paraSpaceAfter: 2 });
  }
  function passos(s, lista, x, y, w, pt, cor) {   // passos numerados em círculos
    let cy = y;
    lista.forEach((t, i) => {
      const hh = Math.max(0.42, altura(t, w - 0.6, pt) - 0.06);
      s.addShape(pres.shapes.OVAL, { x, y: cy + 0.02, w: 0.38, h: 0.38, fill: { color: cor || C.accent1 }, line: { color: cor || C.accent1 } });
      s.addText(String(i + 1), { x, y: cy + 0.02, w: 0.38, h: 0.38, fontSize: 13, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true });
      s.addText(runs(t, { color: C.text1 }), { x: x + 0.55, y: cy, w: w - 0.55, h: hh, fontSize: pt, valign: "top", margin: 0, isTextBox: true });
      cy += hh + 0.14;
    });
    return cy;
  }
  const alturaPassos = (lista, w, pt) => lista.reduce((n, t) => n + Math.max(0.42, altura(t, w - 0.6, pt) - 0.06) + 0.14, 0);
  function tabela(s, t, x, y, w, pt) {
    const linhasT = t.map((r, i) => r.map((c) => ({
      text: i === 0 ? limpo(c) : runs(c),
      options: i === 0 ? { bold: true, color: "FFFFFF", fill: { color: "0B2137" } } : { color: "1D2733", fill: { color: i % 2 ? "FFFFFF" : "F2F4F7" } },
    })));
    const n = t[0].length;
    const colW = n === 2 ? [w * 0.34, w * 0.66] : n === 3 ? [w * 0.22, w * 0.46, w * 0.32] : Array(n).fill(w / n);
    s.addTable(linhasT, { x, y, w, colW, fontSize: pt, fontFace: "Calibri", border: { type: "solid", pt: 0.75, color: "DCE3E9" }, margin: [5, 8, 5, 8], valign: "middle" });
  }
  const alturaTabela = (t, w, pt) => {
    const n = t[0].length; const colW = n === 2 ? [w * 0.34, w * 0.66] : n === 3 ? [w * 0.22, w * 0.46, w * 0.32] : Array(n).fill(w / n);
    return t.reduce((acc, r) => acc + Math.max(...r.map((c, j) => linhas(c, colW[j] - 0.25, pt))) * pt * 1.2 / 72 + 0.16, 0);
  };
  const notasSeccao = (sec) => sec.blocks.map((b) =>
    b.p ? limpo(b.p) : b.steps ? b.steps.map((t, i) => `${i + 1}. ${limpo(t)}`).join("\n") :
    b.table ? b.table.map((r) => r.map(limpo).join(" | ")).join("\n") :
    b.tip ? "Dica: " + limpo(b.tip) : b.note ? "Nota: " + limpo(b.note) : b.warn ? "Atenção: " + limpo(b.warn) :
    b.figure ? `[Figura] ${limpo(b.caption || "")}` : "").filter(Boolean).join("\n\n");

  function origemFigura(b, guia) {
    let f = (b.variants && b.variants[guia]) || b.figure;
    if (f.endsWith(".svg")) return path.join(BUILD, "svg", slug, path.basename(f, ".svg") + ".png");
    return path.join(figDir, f);
  }
  const comprimidas = {};
  async function comprimir(b, guia) {
    const o = origemFigura(b, guia);
    if (pequena(b.figure)) return o;
    const d = path.join(BUILD, "fig", slug); fs.mkdirSync(d, { recursive: true });
    const destino = path.join(d, o.replace(/[\/]/g, "_").slice(-90).replace(/\.\w+$/, ".jpg"));
    if (!fs.existsSync(destino)) await sharp(o).flatten({ background: "#ffffff" }).resize({ width: 1800, withoutEnlargement: true }).jpeg({ quality: 85 }).toFile(destino);
    comprimidas[o] = destino; return destino;
  }
  const ficheiroFigura = (b, guia) => comprimidas[origemFigura(b, guia)] || origemFigura(b, guia);
  const pequena = (f) => /office-replica|windows-replica|icone-/.test(f);

  // ===== 1. Capa =====
  secAtual = "Abertura"; seccao(secAtual);
  {
    const g = cfg.abre, c = cena(g, "dir", "escuro"), z = zona(c, "dir");
    const s = novo("Capa"); s.background = { path: c.path };
    s.addImage({ path: LOGO, x: z.x, y: 0.55, w: 1.05, h: 1.05, altText: "Logótipo ATC – Angbu Training Centre" });
    eyebrow(s, `Manual do formando · Módulo ${mod.num}`, z.x, 2.15, z.w);
    s.addText(manual.course, { x: z.x, y: 2.5, w: z.w, h: 1.5, fontFace: "Cambria", fontSize: 44, bold: true, color: C.background1, valign: "top", margin: 0, fit: "shrink", isTextBox: true });
    s.addText(mod.title, { x: z.x, y: 4.0, w: z.w, h: 0.6, fontSize: 24, color: C.accent3, margin: 0, isTextBox: true });
    s.addText(manual.subtitle || "", { x: z.x, y: 4.6, w: z.w, h: 0.8, fontSize: 16, color: "D5DEE6", margin: 0, valign: "top", isTextBox: true });
    s.addText([{ text: "ATC – Angbu Training Centre · Luanda", options: { bold: true, breakLine: true } },
               { text: `Versão ${manual.version || "1.0"} · ${manual.date || ""}` }],
      { x: z.x, y: 6.25, w: z.w, h: 0.7, fontSize: 12, color: "D5DEE6", margin: 0, isTextBox: true });
    s.addNotes(`Apresentação do módulo ${mod.num} do curso ${manual.course}. ${NOMES[g]} é o guia virtual que acompanha os formandos na plataforma ATC.`);
  }
  // ===== 2. Boas-vindas =====
  {
    const g = outro(cfg.abre), c = cena(g, "esq", "claro"), z = zona(c, "esq");
    const s = novo("Cena"); s.background = { path: c.path };
    eyebrow(s, `Olá, sou ${g === "helena" ? "a" : "o"} ${NOMES[g]}`, z.x, 0.9, z.w);
    s.addText(`Bem-vindo ao módulo ${mod.num}`, { x: z.x, y: 1.25, w: z.w, h: 0.9, fontFace: "Cambria", fontSize: 34, bold: true, color: C.text2, margin: 0, isTextBox: true });
    const pt = altura(mod.intro, z.w, 18) > 2.6 ? 16 : 18;
    s.addText(runs(mod.intro, { color: C.text1 }), { x: z.x, y: 2.3, w: z.w, h: 2.6, fontSize: pt, valign: "top", margin: 0, isTextBox: true });
    const stats = [];
    if (manual.hours_class) stats.push([`${manual.hours_class} h`, "de sessão presencial"]);
    if (manual.hours_video) stats.push([`${Math.round(manual.hours_video * 60)} min`, "de vídeo-aulas"]);
    stats.push([String(mod.sections.length), "temas neste módulo"]);
    const sw = (z.w - 0.3 * (stats.length - 1)) / stats.length;
    stats.forEach(([n, l], i) => {
      const x = z.x + i * (sw + 0.3);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.15, w: sw, h: 1.45, rectRadius: 0.1, fill: { color: "FFFFFF", transparency: 10 }, line: { color: "FFFFFF" }, shadow: sombra() });
      s.addText(n, { x, y: 5.25, w: sw, h: 0.75, fontFace: "Cambria", fontSize: 32, bold: true, color: C.accent1, align: "center", margin: 0, isTextBox: true });
      s.addText(l, { x: x + 0.1, y: 5.98, w: sw - 0.2, h: 0.5, fontSize: 13, color: C.text1, align: "center", margin: 0, isTextBox: true });
    });
    s.addNotes(limpo(mod.intro));
  }
  // ===== 3. Objetivos =====
  {
    const s = novo("Conteúdo"); s.addText("Objetivos do módulo", { placeholder: "title" });
    const g = cfg.abre;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.5, w: 3.6, h: 5.15, rectRadius: 0.15, fill: { color: C.text2 }, line: { color: "0B2137" } });
    s.addImage({ path: avatar(g), x: 1.35, y: 1.9, w: 2.1, h: 2.1, altText: `${NOMES[g]}, guia virtual ATC` });
    s.addText([{ text: "No final deste módulo,", options: { breakLine: true } }, { text: "vai ser capaz de:" }],
      { x: 0.85, y: 4.3, w: 3.1, h: 1.0, fontFace: "Cambria", fontSize: 20, bold: true, color: C.background1, align: "center", margin: 0, isTextBox: true });
    s.addText(`${NOMES[g]} · guia virtual ATC`, { x: 0.85, y: 5.6, w: 3.1, h: 0.4, fontSize: 12, color: C.accent3, align: "center", margin: 0, isTextBox: true });
    const lista = mod.objectives, rowH = Math.min(1.0, 5.15 / lista.length);
    lista.forEach((t, i) => {
      const y = 1.5 + i * rowH;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.6, y: y + 0.06, w: 8.1, h: rowH - 0.14, rectRadius: 0.08, fill: { color: "F2F4F7" }, line: { color: "F2F4F7" } });
      s.addShape(pres.shapes.OVAL, { x: 4.82, y: y + rowH / 2 - 0.25, w: 0.5, h: 0.5, fill: { color: C.accent1 }, line: { color: "DA6D24" } });
      s.addText(String(i + 1), { x: 4.82, y: y + rowH / 2 - 0.25, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true });
      s.addText(runs(t, { color: C.text1 }), { x: 5.55, y: y + 0.06, w: 6.95, h: rowH - 0.14, fontSize: 16, valign: "middle", margin: 0, isTextBox: true });
    });
    s.addNotes("Objetivos:\n" + lista.map((t, i) => `${i + 1}. ${limpo(t)}`).join("\n"));
  }
  // ===== 4. Agenda =====
  {
    const g = cfg.abre, c = cena(g, "dir", "claro"), z = zona(c, "dir");
    const s = novo("Cena"); s.background = { path: c.path };
    eyebrow(s, `Módulo ${mod.num} · ${mod.title}`, z.x, 0.9, z.w, C.accent2);
    s.addText("O que vamos aprender", { x: z.x, y: 1.25, w: z.w, h: 0.9, fontFace: "Cambria", fontSize: 34, bold: true, color: C.text2, margin: 0, isTextBox: true });
    const lista = mod.sections.map((x) => x.title.replace(/^\d+\.\d+\s*/, ""));
    const rowH = Math.min(0.62, 4.5 / lista.length);
    lista.forEach((t, i) => {
      const y = 2.35 + i * rowH;
      s.addText(String(i + 1).padStart(2, "0"), { x: z.x, y, w: 0.6, h: rowH, fontFace: "Cambria", fontSize: 18, bold: true, color: C.accent1, valign: "middle", margin: 0, isTextBox: true });
      s.addText(t, { x: z.x + 0.7, y, w: z.w - 0.7, h: rowH, fontSize: rowH < 0.6 ? 16 : 18, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
    });
    s.addNotes("Temas do módulo:\n" + mod.sections.map((x) => x.title).join("\n"));
  }

  // ===== Secções =====
  secAtual = "Conteúdos"; seccao(secAtual);
  for (const [i, sec] of mod.sections.entries()) {
    const guia = i % 2 === 0 ? outro(cfg.abre) : cfg.abre;
    const ps = sec.blocks.filter((b) => b.p).map((b) => b.p);
    const steps = (sec.blocks.find((b) => b.steps) || {}).steps;
    const tab = (sec.blocks.find((b) => b.table) || {}).table;
    const call = sec.blocks.find((b) => b.tip || b.note || b.warn);
    const figs = sec.blocks.filter((b) => b.figure);
    const grandes = figs.filter((b) => !pequena(b.figure));
    const icones = figs.filter((b) => pequena(b.figure));
    const titulo = sec.title.replace(/^Exemplo ATC · /, "Exemplo ATC: ");
    let s;
    for (const b of figs) await comprimir(b, guia);
    const d0 = grandes.length === 1 ? await dimensoes(ficheiroFigura(grandes[0], guia)) : null;

    if (d0 && d0.w / d0.h > 2.2) {
      // --- figura larga em cima, texto em baixo ---
      s = novo("Conteúdo"); s.addText(titulo, { placeholder: "title" });
      const r = caber(d0, 0.6, 1.45, 12.1, 2.3);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: r.x - 0.07, y: r.y - 0.07, w: r.w + 0.14, h: r.h + 0.14, rectRadius: 0.06, fill: { color: "FFFFFF" }, line: { color: "DCE3E9", width: 0.75 }, shadow: sombra() });
      s.addImage({ path: ficheiroFigura(grandes[0], guia), ...r, altText: limpo(grandes[0].caption || titulo) });
      let y = r.y + r.h + 0.3;
      const lw = call ? 7.4 : 12.1;
      if (ps[0]) { const hh = altura(ps[0], lw, 15); s.addText(runs(ps[0], { color: C.text1 }), { x: 0.6, y, w: lw, h: hh, fontSize: 15, valign: "top", margin: 0, isTextBox: true }); y += hh + 0.15; }
      if (tab) tabela(s, tab, 0.6, y, lw, alturaTabela(tab, lw, 14) + y <= 6.8 ? 14 : 12);
      else if (steps) passos(s, steps, 0.6, y, lw, 14);
      if (call) { dica.pt = 14; dica(s, call, guia, 8.35, r.y + r.h + 0.3, 4.4, Math.min(2.4, Math.max(1.3, altura(call.tip || call.note || call.warn, 3.0, 14) + 0.4))); }
    } else if (grandes.length) {
      // --- figura à esquerda, texto à direita ---
      s = novo("Conteúdo"); s.addText(titulo, { placeholder: "title" });
      const fx = 0.6, fy = 1.45, fw = 7.3, fh = 5.25;
      const usar = grandes.slice(0, 2);
      const dims = await Promise.all(usar.map((b) => dimensoes(ficheiroFigura(b, guia))));
      let caixas;
      if (usar.length === 1) caixas = [[fx, fy, fw, fh - 0.45]];
      else {   // duas figuras: lado a lado ou empilhadas, o que der figuras maiores
        const lado = Math.min(...dims.map((d) => caber(d, 0, 0, (fw - 0.25) / 2, fh - 0.45).w * caber(d, 0, 0, (fw - 0.25) / 2, fh - 0.45).h));
        const pilha = Math.min(...dims.map((d) => caber(d, 0, 0, fw, (fh - 0.6) / 2).w * caber(d, 0, 0, fw, (fh - 0.6) / 2).h));
        caixas = lado >= pilha ? [[fx, fy, (fw - 0.25) / 2, fh - 0.45], [fx + (fw + 0.25) / 2, fy, (fw - 0.25) / 2, fh - 0.45]]
                               : [[fx, fy, fw, (fh - 0.6) / 2], [fx, fy + (fh - 0.6) / 2 + 0.15, fw, (fh - 0.6) / 2]];
      }
      usar.forEach((b, k) => {
        const r = caber(dims[k], ...caixas[k]);
        s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: r.x - 0.07, y: r.y - 0.07, w: r.w + 0.14, h: r.h + 0.14, rectRadius: 0.06, fill: { color: "FFFFFF" }, line: { color: "DCE3E9", width: 0.75 }, shadow: sombra() });
        s.addImage({ path: ficheiroFigura(b, guia), ...r, altText: limpo(b.caption || titulo) });
      });
      const cap = limpo(usar[0].caption || "");
      if (cap) s.addText(cap.length > 150 ? cap.slice(0, 147).replace(/\s\S*$/, "") + "…" : cap,
        { x: fx, y: fy + fh - 0.35, w: fw, h: 0.42, fontSize: 10, italic: true, color: C.accent4, margin: 0, valign: "top", isTextBox: true });
      // coluna da direita, com o que couber (o resto vai para as notas)
      const cx = 8.3, cw = 4.45; let y = 1.45; const fim = 6.75;
      const hCall = call ? Math.max(1.15, altura(call.tip || call.note || call.warn, cw - 1.4, 13) + 0.35) : 0;
      const limite = fim - (call ? hCall + 0.2 : 0);
      const lead = ps[0];
      if (lead) {
        const pt = altura(lead, cw, 16) < 1.9 ? 16 : 14;
        const hh = Math.min(altura(lead, cw, pt), limite - y);
        s.addText(runs(lead, { color: C.text1 }), { x: cx, y, w: cw, h: hh, fontSize: pt, valign: "top", margin: 0, isTextBox: true });
        y += hh + 0.2;
      }
      if (steps && y + alturaPassos(steps, cw, 14) <= limite) y = passos(s, steps, cx, y, cw, 14) + 0.05;
      else if (tab && tab[0].length === 2 && y + alturaTabela(tab, cw, 12) <= limite) { tabela(s, tab, cx, y, cw, 12); y += alturaTabela(tab, cw, 12) + 0.2; }
      else if (tab && y + 1.2 <= limite) {   // tabela larga: lista compacta "termo — significado"
        const itens = tab.slice(1).map((r) => (r.length > 2 && limpo(r[0]).length <= 2) ? `**${limpo(r[1])}**: ${limpo(r[2])}` : `**${limpo(r[0])}**: ${limpo(r[1])}`);
        if (y + alturaPassos(itens, cw, 13) <= limite) {
          s.addText(itens.flatMap((t, k) => { const r = runs(t, { color: C.text1 }); r[0].options.bullet = true; if (k < itens.length - 1) r[r.length - 1].options.breakLine = true; return r; }),
            { x: cx, y, w: cw, h: limite - y, fontSize: 13, valign: "top", margin: 0, paraSpaceAfter: 6, isTextBox: true });
        }
      }
      if (call) { dica.pt = 13; dica(s, call, guia, cx, fim - hCall, cw, hCall); dica.pt = 14; }
      icones.slice(0, 3).forEach((b, k) => {
        s.addImage({ path: ficheiroFigura(b, guia), x: 10.9 - k * 0.7, y: 0.5, w: 0.55, h: 0.55, altText: limpo(b.caption || "") });
      });
    } else if (icones.length >= 3) {
      // --- grelha de ícones (reconhecer os programas) ---
      s = novo("Conteúdo"); s.addText(titulo, { placeholder: "title" });
      if (ps[0]) s.addText(runs(ps[0], { color: C.text1 }), { x: 0.6, y: 1.45, w: 12.1, h: 1.1, fontSize: 16, valign: "top", margin: 0, isTextBox: true });
      const n = icones.length, cw = 2.6, gap = (12.1 - n * cw) / (n - 1);
      icones.forEach((b, k) => {
        const x = 0.6 + k * (cw + gap);
        s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.9, w: cw, h: 3.2, rectRadius: 0.12, fill: { color: "F2F4F7" }, line: { color: "F2F4F7" } });
        s.addImage({ path: ficheiroFigura(b, guia), x: x + (cw - 1.5) / 2, y: 3.25, w: 1.5, h: 1.5, altText: limpo(b.caption || "") });
        const nome = (b.figure.match(/replica-(\w+)/) || [, ""])[1];
        s.addText({ word: "Word", excel: "Excel", powerpoint: "PowerPoint", outlook: "Outlook" }[nome] || nome, { x, y: 5.0, w: cw, h: 0.5, fontSize: 20, bold: true, color: C.text2, align: "center", margin: 0, isTextBox: true });
      });
      s.addText("Ícones de identificação: réplicas visuais fornecidas para este curso.", { x: 0.6, y: 6.35, w: 12.1, h: 0.35, fontSize: 10, italic: true, color: C.accent4, margin: 0, isTextBox: true });
    } else if (tab) {
      // --- tabela em largura total ---
      s = novo("Conteúdo"); s.addText(titulo, { placeholder: "title" });
      let y = 1.45;
      icones.slice(0, 1).forEach((b) => s.addImage({ path: ficheiroFigura(b, guia), x: 11.35, y: 0.47, w: 0.62, h: 0.62, altText: limpo(b.caption || "") }));
      for (const p of ps.slice(0, 2)) {
        const hh = altura(p, 12.1, 16);
        if (y + hh > 3.6) break;
        s.addText(runs(p, { color: C.text1 }), { x: 0.6, y, w: 12.1, h: hh, fontSize: 16, valign: "top", margin: 0, isTextBox: true }); y += hh + 0.12;
      }
      y += 0.1;
      const pt = alturaTabela(tab, 12.1, 14) + y < (call ? 5.4 : 6.6) ? 14 : 12;
      tabela(s, tab, 0.6, y, 12.1, pt); y += alturaTabela(tab, 12.1, pt) + 0.25;
      if (call) { const hc = Math.max(1.05, altura(call.tip || call.note || call.warn, 10.6, 14) + 0.3); dica(s, call, guia, 0.6, Math.max(y, 6.75 - hc), 12.1, hc); }
    } else {
      // --- cena com o guia a apontar para os passos ---
      const lado = i % 4 < 2 ? "dir" : "esq";
      const c = cena(guia, lado, "claro"), z = zona(c, lado);
      s = novo("Cena"); s.background = { path: c.path };
      eyebrow(s, `Tema ${i + 1}`, z.x, 0.9, z.w, C.accent2);
      const tt = titulo.replace(/^\d+\.\d+\s*/, "");
      const tpt = linhas(tt, z.w, 30) > 1 ? 26 : 30;
      s.addText(tt, { x: z.x, y: 1.25, w: z.w, h: 0.9, fontFace: "Cambria", fontSize: tpt, bold: true, color: C.text2, margin: 0, valign: "top", isTextBox: true });
      const topo = 2.3, fim = 6.75;
      const callTxt = call ? (call.tip || call.note || call.warn) : "";
      const hCall = call ? Math.max(1.05, altura(callTxt, z.w - 1.4, 14) + 0.3) : 0;
      // escolher o que cabe: passos primeiro, depois a dica, depois o parágrafo (o resto fica nas notas)
      let pt = 15, usarLead = !!ps[0], usarCall = !!call;
      const preciso = () => (usarLead ? altura(ps[0], z.w, pt) + 0.2 : 0) + (steps ? alturaPassos(steps, z.w, pt) : 0) + (usarCall ? hCall + 0.2 : 0);
      if (preciso() > fim - topo) pt = 14;
      if (preciso() > fim - topo) usarLead = false;
      if (preciso() > fim - topo) { usarLead = !!ps[0]; usarCall = false; }
      if (preciso() > fim - topo) usarLead = false;
      let y = topo;
      if (usarLead) {
        const hh = altura(ps[0], z.w, pt);
        s.addText(runs(ps[0], { color: C.text1 }), { x: z.x, y, w: z.w, h: hh, fontSize: pt, valign: "top", margin: 0, isTextBox: true }); y += hh + 0.2;
      }
      if (steps) y = passos(s, steps, z.x, y, z.w, pt);
      if (usarCall) dica(s, call, guia, z.x, Math.max(y + 0.1, fim - hCall), z.w, hCall);
    }
    s.addNotes(`${sec.title}\n\n${notasSeccao(sec)}`);
    // Secção com imagem e tabela larga: a tabela segue num diapositivo próprio, para não ficar só nas notas.
    if (grandes.length && tab && tab[0].length > 2) {
      const t = novo("Conteúdo"); t.addText(`${titulo} (continuação)`, { placeholder: "title" });
      const pt = alturaTabela(tab, 12.1, 14) + 1.45 <= 6.7 ? 14 : 12;
      tabela(t, tab, 0.6, 1.45, 12.1, pt);
      t.addNotes(`${sec.title} (tabela)`);
    }
  }

  // ===== Resumo, exercício, questionário, glossário =====
  secAtual = "Consolidação"; seccao(secAtual);
  {
    const g = outro(cfg.abre), c = cena(g, "dir", "claro"), z = zona(c, "dir");
    const s = novo("Cena"); s.background = { path: c.path };
    eyebrow(s, "Para recordar", z.x, 0.9, z.w);
    s.addText("Resumo do módulo", { x: z.x, y: 1.25, w: z.w, h: 0.9, fontFace: "Cambria", fontSize: 34, bold: true, color: C.text2, margin: 0, isTextBox: true });
    let y = 2.35;
    mod.summary.forEach((t) => {
      const hh = Math.max(0.5, altura(t, z.w - 0.6, 16));
      s.addShape(pres.shapes.OVAL, { x: z.x, y: y + 0.05, w: 0.36, h: 0.36, fill: { color: C.accent5 }, line: { color: "2E7D4F" } });
      s.addText("✓", { x: z.x, y: y + 0.05, w: 0.36, h: 0.36, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true });
      s.addText(runs(t, { color: C.text1 }), { x: z.x + 0.55, y, w: z.w - 0.55, h: hh, fontSize: 16, valign: "top", margin: 0, isTextBox: true });
      y += hh + 0.18;
    });
    s.addNotes("Resumo:\n" + mod.summary.map(limpo).join("\n"));
  }
  {
    const ex = mod.exercise, s = novo("Conteúdo"); s.addText(ex.title.replace(/^Exercício prático · /, "Exercício prático: "), { placeholder: "title" });
    const g = cfg.abre;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.5, w: 3.4, h: 5.2, rectRadius: 0.15, fill: { color: "F2F4F7" }, line: { color: "F2F4F7" } });
    s.addText(String(ex.minutes || ""), { x: 0.6, y: 1.75, w: 3.4, h: 1.1, fontFace: "Cambria", fontSize: 60, bold: true, color: C.accent1, align: "center", margin: 0, isTextBox: true });
    s.addText("minutos", { x: 0.6, y: 2.85, w: 3.4, h: 0.4, fontSize: 16, color: C.text1, align: "center", margin: 0, isTextBox: true });
    if (ex.file) s.addText(runs(ex.file, { color: C.text1 }), { x: 0.85, y: 3.45, w: 2.9, h: 1.0, fontSize: 14, align: "center", valign: "top", margin: 0, isTextBox: true });
    s.addImage({ path: avatar(g), x: 1.55, y: 4.65, w: 1.5, h: 1.5, altText: `${NOMES[g]}, guia virtual ATC` });
    s.addText(`Prática com ${g === "helena" ? "a" : "o"} ${NOMES[g]}`, { x: 0.6, y: 6.2, w: 3.4, h: 0.35, fontSize: 12, color: C.accent4, align: "center", margin: 0, isTextBox: true });
    const pt = alturaPassos(ex.tasks, 8.3, 16) <= 5.2 ? 16 : 14;
    passos(s, ex.tasks, 4.45, 1.55, 8.3, pt, C.accent2);
    s.addNotes(`${ex.title} (${ex.minutes} min)\n${limpo(ex.file || "")}\n` + ex.tasks.map((t, i) => `${i + 1}. ${limpo(t)}`).join("\n"));
  }
  if (mod.quiz && mod.quiz.length) {
    const s = novo("Conteúdo"); s.addText("Teste os seus conhecimentos", { placeholder: "title" });
    const qs = mod.quiz.slice(0, 4), cw = 5.9, ch = 2.5;
    qs.forEach((q, k) => {
      const x = 0.6 + (k % 2) * (cw + 0.3), y = 1.5 + Math.floor(k / 2) * (ch + 0.25);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: ch, rectRadius: 0.1, fill: { color: "F2F4F7" }, line: { color: "F2F4F7" } });
      s.addText(q.q, { x: x + 0.25, y: y + 0.15, w: cw - 0.5, h: 0.7, fontSize: 15, bold: true, color: C.text2, valign: "top", margin: 0, isTextBox: true });
      s.addText(q.options.map((o, j) => ({ text: `${"ABCD"[j]}) ${o}`, options: { breakLine: j < q.options.length - 1 } })),
        { x: x + 0.25, y: y + 0.88, w: cw - 0.5, h: ch - 1.0, fontSize: 14, color: C.text1, valign: "top", margin: 0, paraSpaceAfter: 2, isTextBox: true });
    });
    s.addNotes("Respostas certas:\n" + qs.map((q, k) => `${k + 1}. ${q.q} → ${"ABCD"[q.answer]}) ${q.options[q.answer]}`).join("\n"));
  }
  if (manual.glossary && manual.glossary.length) {
    const s = novo("Conteúdo"); s.addText("Glossário", { placeholder: "title" });
    const gl = manual.glossary.slice(0, 6), cols = 3, cw = (12.1 - 0.3 * (cols - 1)) / cols, rowsN = Math.ceil(gl.length / cols);
    const ch = (5.2 - 0.3 * (rowsN - 1)) / rowsN;
    gl.forEach(([t, d], k) => {
      const x = 0.6 + (k % cols) * (cw + 0.3), y = 1.5 + Math.floor(k / cols) * (ch + 0.3);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: ch, rectRadius: 0.1, fill: { color: "F2F4F7" }, line: { color: "F2F4F7" } });
      s.addText(t, { x: x + 0.3, y: y + 0.25, w: cw - 0.6, h: 0.5, fontFace: "Cambria", fontSize: 20, bold: true, color: C.accent2, margin: 0, isTextBox: true });
      s.addText(runs(d, { color: C.text1 }), { x: x + 0.3, y: y + 0.85, w: cw - 0.6, h: ch - 1.05, fontSize: 15, valign: "top", margin: 0, isTextBox: true });
    });
    s.addNotes(manual.glossary.map(([t, d]) => `${t}: ${limpo(d)}`).join("\n"));
  }
  // ===== Encerramento =====
  secAtual = "Encerramento"; seccao(secAtual);
  {
    const g = outro(cfg.abre), c = cena(g, "esq", "escuro"), z = zona(c, "esq");
    const s = novo("Capa"); s.background = { path: c.path };
    s.addImage({ path: LOGO, x: z.x, y: 0.7, w: 1.05, h: 1.05, altText: "Logótipo ATC – Angbu Training Centre" });
    s.addText([{ text: "Aprender hoje.", options: { breakLine: true } }, { text: "Ir mais longe amanhã.", options: { color: C.accent3 } }],
      { x: z.x, y: 2.2, w: z.w, h: 1.8, fontFace: "Cambria", fontSize: 38, bold: true, color: C.background1, margin: 0, valign: "top", fit: "shrink", isTextBox: true });
    s.addText(`Continue o módulo ${mod.num} na plataforma ATC: vídeo-aulas, manual completo e o seu guia virtual.`,
      { x: z.x, y: 4.2, w: z.w, h: 1.2, fontSize: 18, color: "D5DEE6", margin: 0, valign: "top", isTextBox: true });
    s.addText("ATC – Angbu Training Centre · Luanda, Angola", { x: z.x, y: 6.3, w: z.w, h: 0.4, fontSize: 12, bold: true, color: "D5DEE6", margin: 0, isTextBox: true });
    s.addNotes("Encerramento. Lembre os formandos de que o manual, os vídeos e o guia por voz estão disponíveis na plataforma ATC.");
  }

  const destino = path.join(AQUI, `${cfg.ficheiro}.pptx`);
  await pres.writeFile({ fileName: destino });
  await applyTheme(destino, THEME);
  console.log("ok", destino);
}

(async () => {
  const alvos = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(CURSOS);
  for (const c of alvos) await gerar(c);
})().catch((e) => { console.error(e); process.exit(1); });
