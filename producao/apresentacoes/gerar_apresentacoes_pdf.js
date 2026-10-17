// Gerador de apresentações PDF em formato 16:9 (1920x1080) para WhatsApp.
// Lê cursos/<curso>/manual/modulo-1.json e os recursos em _build/.
// Uso: node gerar_apresentacoes_pdf.js [curso ...]   → producao/apresentacoes/<Curso>_Modulo1.pdf

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const pw = require("/Users/almeidajose/Documents/K/KiddieCanvas/tmp/pptx/editable-book/node_modules/playwright");

const AQUI = __dirname;
const RAIZ = path.resolve(AQUI, "../..");
const BUILD = path.join(AQUI, "_build");
const CENAS = JSON.parse(fs.readFileSync(path.join(BUILD, "cenas.json"), "utf8"));
const LOGO = path.join(RAIZ, "static", "logo-600.png");

const CURSOS = {
  informatica: { farda: "camisa", cor: "#1E6F8A", abre: "helena", ficheiro: "Informatica_Modulo1" },
  word: { farda: "blazer", cor: "#2B579A", abre: "helena", ficheiro: "Word_Modulo1" },
  excel: { farda: "polo", cor: "#217346", abre: "miguel", ficheiro: "Excel_Modulo1" },
  powerpoint: { farda: "casaco", cor: "#C43E1C", abre: "helena", ficheiro: "PowerPoint_Modulo1" },
  outlook: { farda: "blazer", cor: "#0F6CBD", abre: "miguel", ficheiro: "Outlook_Modulo1" },
  "comptia-a-plus": { farda: "polo", cor: "#B5272D", abre: "miguel", ficheiro: "CompTIA_A+_Modulo1" },
  "comptia-network-plus": { farda: "casaco", cor: "#1F5F99", abre: "helena", ficheiro: "CompTIA_Network+_Modulo1" },
};

const NOMES = { helena: "Helena", miguel: "Miguel" };
const outro = (g) => (g === "helena" ? "miguel" : "helena");

const limpo = (s) => String(s || "").replace(/\*\*/g, "");
const mdHtml = (s) => String(s || "")
  .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
  .replace(/\n/g, "<br>");

const dimCache = {};
function getDimensions(filePath) {
  if (dimCache[filePath]) return dimCache[filePath];
  try {
    const out = execFileSync("sips", ["-g", "pixelWidth", "-g", "pixelHeight", filePath], { encoding: "utf8" });
    const w = parseInt((out.match(/pixelWidth:\s*(\d+)/) || [])[1], 10);
    const h = parseInt((out.match(/pixelHeight:\s*(\d+)/) || [])[1], 10);
    if (w && h) {
      dimCache[filePath] = { w, h, ratio: w / h };
      return dimCache[filePath];
    }
  } catch (_) {}
  dimCache[filePath] = { w: 1600, h: 900, ratio: 1.77 };
  return dimCache[filePath];
}

function resolverFigura(b, slug, guia) {
  let f = (b.variants && b.variants[guia]) || b.figure;
  if (!f) return null;
  if (f.endsWith(".svg")) {
    const p = path.join(BUILD, "svg", slug, path.basename(f, ".svg") + ".png");
    if (fs.existsSync(p)) return p;
  }
  const compDir = path.join(BUILD, "fig", slug);
  if (fs.existsSync(compDir)) {
    const base = path.basename(f).replace(/\.\w+$/, "");
    const files = fs.readdirSync(compDir);
    const m = files.find((x) => x.includes(base));
    if (m) return path.join(compDir, m);
  }
  const figPath = path.resolve(RAIZ, "cursos", slug, "manual", "figures", f);
  if (fs.existsSync(figPath)) return figPath;
  return null;
}

const pequena = (f) => /office-replica|windows-replica|icone-/.test(f || "");

function gerarHtml(slug) {
  const cfg = CURSOS[slug];
  const manual = JSON.parse(fs.readFileSync(path.join(RAIZ, "cursos", slug, "manual", "modulo-1.json"), "utf8"));
  const mod = manual.modules[0];

  const cenaPath = (g, lado, tom) => path.join(BUILD, "cenas", `${cfg.farda}-${g}-${lado}-${tom}.jpg`);
  const cenaBorda = (g, lado, tom) => CENAS[`${cfg.farda}-${g}-${lado}-${tom}.jpg`].borda;
  const avatarPath = (g) => path.join(BUILD, "avatares", `${cfg.farda}-${g}.png`);

  let slidesHtml = [];
  let slideNum = 0;

  const rodape = (n) => `
    <div class="footer">
      <div>ATC · Angbu Training Centre &nbsp;|&nbsp; ${manual.course} · Módulo ${mod.num}</div>
      <div>${n}</div>
    </div>
  `;

  const rodapeCena = (n, zLeft, zWidth) => `
    <div class="footer-cena" style="left:${zLeft}px; width:${zWidth}px;">
      <div>ATC · Angbu Training Centre &nbsp;|&nbsp; ${manual.course} · Módulo ${mod.num}</div>
      <div>${n}</div>
    </div>
  `;

  function renderDica(c, g) {
    if (!c) return "";
    const tipo = c.tip ? "tip" : c.note ? "note" : "warn";
    const rot = { tip: `Dica ${g === "helena" ? "da" : "do"} ${NOMES[g]}`, note: "Nota pedagógica", warn: "Atenção" }[tipo];
    const txt = c.tip || c.note || c.warn;
    return `
      <div class="tip-card ${tipo === "warn" ? "warn" : ""}">
        <img class="tip-avatar" src="file://${avatarPath(g)}" alt="${NOMES[g]}">
        <div class="tip-content">
          <div class="tip-title">${rot}</div>
          <div class="tip-text">${mdHtml(txt)}</div>
        </div>
      </div>
    `;
  }

  function renderPassos(lista, cor) {
    if (!lista || !lista.length) return "";
    return `
      <div class="steps-list">
        ${lista.map((t, idx) => `
          <div class="step-item">
            <div class="step-num" style="background:${cor || "#DA6D24"};">${idx + 1}</div>
            <div class="step-text">${mdHtml(t)}</div>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderTabela(t) {
    if (!t || !t.length) return "";
    const [hRow, ...rows] = t;
    return `
      <table class="atc-table">
        <thead>
          <tr>${hRow.map((c) => `<th>${limpo(c)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${rows.map((r) => `
            <tr>${r.map((c) => `<td>${mdHtml(c)}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  // 1. Capa
  {
    slideNum++;
    const g = cfg.abre;
    const cPath = cenaPath(g, "dir", "escuro");
    const borda = cenaBorda(g, "dir", "escuro");
    const zWidth = Math.round(borda * 1920 - 150);
    slidesHtml.push(`
      <section class="slide capa" style="background-image:url('file://${cPath}');">
        <div class="zona" style="left:86px; width:${zWidth}px;">
          <img class="logo" src="file://${LOGO}" alt="Logo ATC">
          <div class="eyebrow">Manual do formando · Módulo ${mod.num}</div>
          <h1>${manual.course}</h1>
          <h2>${mod.title}</h2>
          ${manual.subtitle ? `<div class="sub">${manual.subtitle}</div>` : ""}
          <div class="footer-meta">
            <div><b>ATC – Angbu Training Centre</b> · Cabinda, Angola</div>
            <div>Versão ${manual.version || "1.0"} · ${manual.date || "Outubro 2026"}</div>
          </div>
        </div>
      </section>
    `);
  }

  // 2. Boas-vindas
  {
    slideNum++;
    const g = outro(cfg.abre);
    const cPath = cenaPath(g, "esq", "claro");
    const borda = cenaBorda(g, "esq", "claro");
    const zLeft = Math.round(borda * 1920 + 70);
    const zWidth = 1920 - 86 - zLeft;

    const hSala = manual.hours_class && manual.hours_class <= 4 ? `${manual.hours_class} h` : "2 h";
    const mVideo = manual.hours_video && manual.hours_video <= 1 ? `${Math.round(manual.hours_video * 60)} min` : "40 min";
    const stats = [
      [hSala, "em sala e laboratório"],
      [mVideo, "de vídeo-aulas"],
      [String(mod.sections.length), "temas estruturados"],
    ];

    slidesHtml.push(`
      <section class="slide cena" style="background-image:url('file://${cPath}');">
        <div class="zona" style="left:${zLeft}px; width:${zWidth}px;">
          <div class="eyebrow">Olá, sou ${g === "helena" ? "a" : "o"} ${NOMES[g]}</div>
          <h1>Bem-vindo ao módulo ${mod.num}</h1>
          <div style="font-size:24px; line-height:1.5; color:#1D2733; margin-bottom:36px;">
            ${mdHtml(mod.intro)}
          </div>
          <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:20px;">
            ${stats.map(([val, label]) => `
              <div class="card-white" style="text-align:center; padding:24px 16px;">
                <div style="font-family:'Cambria',Georgia,serif; font-size:46px; font-weight:700; color:#DA6D24; line-height:1; margin-bottom:8px;">${val}</div>
                <div style="font-size:18px; color:#1D2733; font-weight:500;">${label}</div>
              </div>
            `).join("")}
          </div>
        </div>
        ${rodapeCena(slideNum, zLeft, zWidth)}
      </section>
    `);
  }

  // 3. Objetivos
  {
    slideNum++;
    const g = cfg.abre;
    slidesHtml.push(`
      <section class="slide conteudo">
        <div class="top-stripe" style="background:${cfg.cor};"></div>
        <div class="header">
          <div class="title-area">
            <div class="breadcrumb" style="color:${cfg.cor};">MÓDULO ${mod.num} · COMPETÊNCIAS E RESULTADOS DE APRENDIZAGEM</div>
            <h1>Objetivos de aprendizagem</h1>
          </div>
          <img class="logo" src="file://${LOGO}" alt="Logo ATC">
        </div>
        <div class="content-body" style="display:grid; grid-template-columns:420px 1fr; gap:36px; align-items:stretch;">
          <div style="background:#0B2137; border-radius:20px; padding:36px 28px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;">
            <img src="file://${avatarPath(g)}" style="width:200px; height:200px; object-fit:contain; margin-bottom:24px;" alt="${NOMES[g]}">
            <div style="font-family:'Cambria',Georgia,serif; font-size:26px; font-weight:700; color:#FFFFFF; line-height:1.25; margin-bottom:12px;">
              No final deste módulo,<br>será capaz de:
            </div>
            <div style="font-size:17px; color:#F08A3E; font-weight:600;">
              ${NOMES[g]} · guia virtual ATC
            </div>
          </div>
          <div style="display:flex; flex-direction:column; justify-content:space-around; gap:14px;">
            ${mod.objectives.map((t, i) => `
              <div class="card" style="display:flex; align-items:center; gap:20px; padding:20px 24px;">
                <div style="width:48px; height:48px; border-radius:50%; background:#DA6D24; color:#FFFFFF; font-size:22px; font-weight:700; display:flex; align-items:center; justify-content:center; flex-shrink:0;">
                  ${i + 1}
                </div>
                <div style="font-size:22px; color:#1D2733; line-height:1.35; font-weight:500;">
                  ${mdHtml(t)}
                </div>
              </div>
            `).join("")}
          </div>
        </div>
        ${rodape(slideNum)}
      </section>
    `);
  }

  // 4. Agenda
  {
    slideNum++;
    const g = cfg.abre;
    const cPath = cenaPath(g, "dir", "claro");
    const borda = cenaBorda(g, "dir", "claro");
    const zWidth = Math.round(borda * 1920 - 150);
    const seccoes = mod.sections.map((x) => x.title.replace(/^\d+\.\d+\s*/, ""));

    slidesHtml.push(`
      <section class="slide cena" style="background-image:url('file://${cPath}');">
        <div class="zona" style="left:86px; width:${zWidth}px;">
          <div class="eyebrow" style="color:${cfg.cor};">Módulo ${mod.num} · ${mod.title}</div>
          <h1>Percurso do módulo</h1>
          <div style="display:flex; flex-direction:column; gap:16px;">
            ${seccoes.map((t, i) => `
              <div style="display:flex; align-items:center; gap:18px;">
                <div style="background:${cfg.cor}; color:#FFFFFF; font-family:'Cambria',Georgia,serif; font-size:20px; font-weight:700; border-radius:8px; padding:8px 16px; min-width:54px; text-align:center;">
                  ${String(i + 1).padStart(2, "0")}
                </div>
                <div style="font-size:24px; font-weight:700; color:#1D2733;">
                  ${t}
                </div>
              </div>
            `).join("")}
          </div>
        </div>
        ${rodapeCena(slideNum, 86, zWidth)}
      </section>
    `);
  }

  // Secções de conteúdo
  const totalSec = mod.sections.length;
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
    const migalha = `MÓDULO ${mod.num} · TEMA ${i + 1} DE ${totalSec}`;

    if (grandes.length) {
      const figPath1 = resolverFigura(grandes[0], slug, guia);
      const cap = limpo(grandes[0].caption || "");
      const dims1 = figPath1 ? getDimensions(figPath1) : { ratio: 1.77 };

      if (grandes.length === 1 && dims1.ratio > 2.2) {
        // --- Figura panorâmica / larga em cima, texto em baixo ---
        slideNum++;
        slidesHtml.push(`
          <section class="slide conteudo">
            <div class="top-stripe" style="background:${cfg.cor};"></div>
            <div class="header">
              <div class="title-area">
                <div class="breadcrumb" style="color:${cfg.cor};">${migalha}</div>
                <h1>${titulo}</h1>
              </div>
              <img class="logo" src="file://${LOGO}" alt="Logo ATC">
            </div>
            <div class="content-body" style="display:flex; flex-direction:column; justify-content:space-between; gap:24px;">
              <div class="image-frame" style="height:380px; width:100%;">
                <img src="file://${figPath1}" alt="${cap || titulo}" style="height:100%; width:100%; object-fit:contain;">
              </div>
              <div style="display:grid; grid-template-columns:${call ? "1.2fr 0.8fr" : "1fr"}; gap:28px; align-items:center;">
                <div style="display:flex; flex-direction:column; gap:16px;">
                  ${ps[0] ? `<div style="font-size:22px; line-height:1.45; color:#1D2733;">${mdHtml(ps[0])}</div>` : ""}
                  ${steps ? renderPassos(steps, cfg.cor) : ""}
                  ${tab ? renderTabela(tab) : ""}
                </div>
                ${call ? renderDica(call, guia) : ""}
              </div>
            </div>
            ${rodape(slideNum)}
          </section>
        `);
      } else {
        // --- Figura à esquerda, texto/passos/dica à direita ---
        slideNum++;
        const figPath2 = grandes.length > 1 ? resolverFigura(grandes[1], slug, guia) : null;

        slidesHtml.push(`
          <section class="slide conteudo">
            <div class="top-stripe" style="background:${cfg.cor};"></div>
            <div class="header">
              <div class="title-area">
                <div class="breadcrumb" style="color:${cfg.cor};">${migalha}</div>
                <h1>${titulo}</h1>
              </div>
              <img class="logo" src="file://${LOGO}" alt="Logo ATC">
            </div>
            <div class="content-body" style="display:grid; grid-template-columns:1.15fr 0.85fr; gap:36px; align-items:stretch;">
              <div style="display:flex; flex-direction:column; gap:12px;">
                ${figPath2 ? `
                  <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; flex:1;">
                    <div class="image-frame"><img src="file://${figPath1}" alt="${cap || titulo}"></div>
                    <div class="image-frame"><img src="file://${figPath2}" alt="${cap || titulo}"></div>
                  </div>
                ` : `
                  <div class="image-frame" style="flex:1;">
                    <img src="file://${figPath1}" alt="${cap || titulo}">
                  </div>
                `}
                ${cap ? `<div style="font-size:16px; font-style:italic; color:#5F6B78; line-height:1.35;">${cap}</div>` : ""}
              </div>
              <div style="display:flex; flex-direction:column; justify-content:space-between; gap:20px;">
                <div style="display:flex; flex-direction:column; gap:20px;">
                  ${ps[0] ? `<div style="font-size:22px; line-height:1.45; color:#1D2733;">${mdHtml(ps[0])}</div>` : ""}
                  ${steps ? renderPassos(steps, cfg.cor) : ""}
                  ${(!steps && tab && tab[0].length === 2) ? renderTabela(tab) : ""}
                </div>
                ${call ? renderDica(call, guia) : ""}
              </div>
            </div>
            ${rodape(slideNum)}
          </section>
        `);
      }

      if (tab && tab[0].length > 2) {
        slideNum++;
        slidesHtml.push(`
          <section class="slide conteudo">
            <div class="top-stripe" style="background:${cfg.cor};"></div>
            <div class="header">
              <div class="title-area">
                <div class="breadcrumb" style="color:${cfg.cor};">${migalha} · QUADRO-RESUMO</div>
                <h1>${titulo} — Quadro de referência</h1>
              </div>
              <img class="logo" src="file://${LOGO}" alt="Logo ATC">
            </div>
            <div class="content-body" style="display:flex; flex-direction:column; justify-content:center;">
              ${renderTabela(tab)}
            </div>
            ${rodape(slideNum)}
          </section>
        `);
      }
    } else if (icones.length >= 3) {
      slideNum++;
      slidesHtml.push(`
        <section class="slide conteudo">
          <div class="top-stripe" style="background:${cfg.cor};"></div>
          <div class="header">
            <div class="title-area">
              <div class="breadcrumb" style="color:${cfg.cor};">${migalha}</div>
              <h1>${titulo}</h1>
            </div>
            <img class="logo" src="file://${LOGO}" alt="Logo ATC">
          </div>
          <div class="content-body" style="display:flex; flex-direction:column; justify-content:space-between;">
            ${ps[0] ? `<div style="font-size:24px; line-height:1.45; color:#1D2733; margin-bottom:24px;">${mdHtml(ps[0])}</div>` : ""}
            <div style="display:grid; grid-template-columns:repeat(${icones.length}, 1fr); gap:28px; margin-bottom:24px;">
              ${icones.map((b) => {
                const icPath = resolverFigura(b, slug, guia);
                const nome = (b.figure.match(/replica-(\w+)/) || [, ""])[1];
                const rotulo = { word: "Word", excel: "Excel", powerpoint: "PowerPoint", outlook: "Outlook" }[nome] || nome;
                return `
                  <div class="card" style="display:flex; flex-direction:column; align-items:center; justify-content:center; padding:36px 20px; text-align:center;">
                    <img src="file://${icPath}" style="width:160px; height:160px; object-fit:contain; margin-bottom:20px;" alt="${rotulo}">
                    <div style="font-size:26px; font-weight:700; color:#0B2137;">${rotulo}</div>
                  </div>
                `;
              }).join("")}
            </div>
            <div style="font-size:16px; font-style:italic; color:#5F6B78;">
              Ícones de identificação: réplicas visuais preparadas para o manual ATC.
            </div>
          </div>
          ${rodape(slideNum)}
        </section>
      `);
    } else if (tab) {
      slideNum++;
      slidesHtml.push(`
        <section class="slide conteudo">
          <div class="top-stripe" style="background:${cfg.cor};"></div>
          <div class="header">
            <div class="title-area">
              <div class="breadcrumb" style="color:${cfg.cor};">${migalha}</div>
              <h1>${titulo}</h1>
            </div>
            <img class="logo" src="file://${LOGO}" alt="Logo ATC">
          </div>
          <div class="content-body" style="display:flex; flex-direction:column; justify-content:space-between; gap:24px;">
            ${ps[0] ? `<div style="font-size:22px; line-height:1.45; color:#1D2733;">${mdHtml(ps[0])}</div>` : ""}
            ${renderTabela(tab)}
            ${call ? renderDica(call, guia) : ""}
          </div>
          ${rodape(slideNum)}
        </section>
      `);
    } else {
      slideNum++;
      const lado = i % 4 < 2 ? "dir" : "esq";
      const cPath = cenaPath(guia, lado, "claro");
      const borda = cenaBorda(guia, lado, "claro");
      const zLeft = lado === "dir" ? 86 : Math.round(borda * 1920 + 70);
      const zWidth = lado === "dir" ? Math.round(borda * 1920 - 150) : (1920 - 86 - zLeft);

      slidesHtml.push(`
        <section class="slide cena" style="background-image:url('file://${cPath}');">
          <div class="zona" style="left:${zLeft}px; width:${zWidth}px;">
            <div class="eyebrow" style="color:${cfg.cor};">${migalha}</div>
            <h1>${titulo.replace(/^\d+\.\d+\s*/, "")}</h1>
            ${ps[0] ? `<div style="font-size:22px; line-height:1.45; color:#1D2733; margin-bottom:24px;">${mdHtml(ps[0])}</div>` : ""}
            ${steps ? `<div style="margin-bottom:24px;">${renderPassos(steps, cfg.cor)}</div>` : ""}
            ${call ? renderDica(call, guia) : ""}
          </div>
          ${rodapeCena(slideNum, zLeft, zWidth)}
        </section>
      `);
    }
  }

  // 6. Síntese pedagógica
  {
    slideNum++;
    const g = outro(cfg.abre);
    const cPath = cenaPath(g, "dir", "claro");
    const borda = cenaBorda(g, "dir", "claro");
    const zWidth = Math.round(borda * 1920 - 150);

    slidesHtml.push(`
      <section class="slide cena" style="background-image:url('file://${cPath}');">
        <div class="zona" style="left:86px; width:${zWidth}px;">
          <div class="eyebrow">Módulo ${mod.num} · Síntese pedagógica</div>
          <h1>Ideias-chave a reter</h1>
          <div style="display:flex; flex-direction:column; gap:18px;">
            ${mod.summary.map((t) => `
              <div style="display:flex; align-items:flex-start; gap:18px;">
                <div style="width:38px; height:38px; border-radius:50%; background:#2E7D4F; color:#FFFFFF; font-size:20px; font-weight:700; display:flex; align-items:center; justify-content:center; flex-shrink:0; margin-top:2px;">
                  ✓
                </div>
                <div style="font-size:22px; line-height:1.45; color:#1D2733; font-weight:500;">
                  ${mdHtml(t)}
                </div>
              </div>
            `).join("")}
          </div>
        </div>
        ${rodapeCena(slideNum, 86, zWidth)}
      </section>
    `);
  }

  // 7. Exercício prático
  {
    slideNum++;
    const ex = mod.exercise;
    const g = cfg.abre;

    slidesHtml.push(`
      <section class="slide conteudo">
        <div class="top-stripe" style="background:${cfg.cor};"></div>
        <div class="header">
          <div class="title-area">
            <div class="breadcrumb" style="color:${cfg.cor};">MÓDULO ${mod.num} · PRÁTICA GUIADA EM LABORATÓRIO</div>
            <h1>${ex.title.replace(/^Exercício prático · /, "Exercício prático: ")}</h1>
          </div>
          <img class="logo" src="file://${LOGO}" alt="Logo ATC">
        </div>
        <div class="content-body" style="display:grid; grid-template-columns:400px 1fr; gap:36px; align-items:stretch;">
          <div class="card" style="display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:32px 24px;">
            <div style="font-family:'Cambria',Georgia,serif; font-size:72px; font-weight:700; color:#DA6D24; line-height:1; margin-bottom:8px;">
              ${ex.minutes || 30}
            </div>
            <div style="font-size:22px; font-weight:700; color:#0B2137; margin-bottom:16px;">
              minutos de prática
            </div>
            ${ex.file ? `
              <div style="background:#FFFFFF; border:1px solid #DCE3E9; border-radius:10px; padding:10px 16px; font-size:16px; color:#1D2733; margin-bottom:20px; font-weight:500;">
                ${mdHtml(ex.file)}
              </div>
            ` : ""}
            <img src="file://${avatarPath(g)}" style="width:160px; height:160px; object-fit:contain; margin-bottom:12px;" alt="${NOMES[g]}">
            <div style="font-size:17px; font-weight:700; color:${cfg.cor};">
              Apoio ${g === "helena" ? "da" : "do"} ${NOMES[g]}
            </div>
          </div>
          <div style="display:flex; flex-direction:column; justify-content:space-between; gap:20px;">
            <div class="steps-list" style="gap:16px;">
              ${ex.tasks.map((t, idx) => `
                <div class="step-item">
                  <div class="step-num" style="background:${cfg.cor};">${idx + 1}</div>
                  <div class="step-text" style="font-size:21px;">${mdHtml(t)}</div>
                </div>
              `).join("")}
            </div>
            <div style="background:#EDF7F1; border:1.5px solid #B8DEC6; border-radius:12px; padding:18px 24px; display:flex; align-items:center; gap:16px;">
              <div style="font-size:24px; color:#2E7D4F;">✓</div>
              <div style="font-size:18px; color:#1D2733; line-height:1.4;">
                <strong style="color:#2E7D4F;">Critério de sucesso:</strong> concluir todos os passos com autonomia e validar o resultado com o formador.
              </div>
            </div>
          </div>
        </div>
        ${rodape(slideNum)}
      </section>
    `);
  }

  // 8. Quiz
  if (mod.quiz && mod.quiz.length) {
    slideNum++;
    const qs = mod.quiz.slice(0, 4);

    slidesHtml.push(`
      <section class="slide conteudo">
        <div class="top-stripe" style="background:${cfg.cor};"></div>
        <div class="header">
          <div class="title-area">
            <div class="breadcrumb" style="color:${cfg.cor};">MÓDULO ${mod.num} · AVALIAÇÃO FORMATIVA EM SALA</div>
            <h1>Teste os seus conhecimentos</h1>
          </div>
          <img class="logo" src="file://${LOGO}" alt="Logo ATC">
        </div>
        <div class="content-body" style="display:flex; flex-direction:column; justify-content:space-between; gap:20px;">
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; flex:1;">
            ${qs.map((q, k) => `
              <div class="card" style="padding:18px 22px; display:flex; flex-direction:column; justify-content:space-between;">
                <div>
                  <div style="display:inline-block; background:${cfg.cor}; color:#FFFFFF; font-size:13px; font-weight:700; border-radius:6px; padding:4px 12px; margin-bottom:8px;">
                    QUESTÃO ${k + 1}
                  </div>
                  <div style="font-size:19px; font-weight:700; color:#0B2137; line-height:1.3; margin-bottom:10px;">
                    ${q.q}
                  </div>
                </div>
                <div style="display:flex; flex-direction:column; gap:4px;">
                  ${q.options.map((opt, j) => `
                    <div style="font-size:17px; color:#1D2733; line-height:1.35;">
                      <strong>${"ABCD"[j]})</strong> ${opt}
                    </div>
                  `).join("")}
                </div>
              </div>
            `).join("")}
          </div>
          <div style="background:#FFF7F0; border:1.5px solid #F2B483; border-radius:12px; padding:14px 20px; display:flex; align-items:center; gap:16px;">
            <div style="font-size:22px; color:#DA6D24;">💡</div>
            <div style="font-size:17px; color:#1D2733;">
              <strong style="color:#DA6D24;">Dinâmica pedagógica:</strong> discuta cada questão em turma antes de confirmar a resposta certa (chave disponível nas notas do formador).
            </div>
          </div>
        </div>
        ${rodape(slideNum)}
      </section>
    `);
  }

  // 9. Glossário
  if (manual.glossary && manual.glossary.length) {
    slideNum++;
    const gl = manual.glossary.slice(0, 6);

    slidesHtml.push(`
      <section class="slide conteudo">
        <div class="top-stripe" style="background:${cfg.cor};"></div>
        <div class="header">
          <div class="title-area">
            <div class="breadcrumb" style="color:${cfg.cor};">MÓDULO ${mod.num} · TERMINOLOGIA TÉCNICA EM PORTUGUÊS EUROPEU</div>
            <h1>Glossário essencial</h1>
          </div>
          <img class="logo" src="file://${LOGO}" alt="Logo ATC">
        </div>
        <div class="content-body" style="display:grid; grid-template-columns:repeat(3, 1fr); grid-template-rows:repeat(2, 1fr); gap:24px;">
          ${gl.map(([termo, def]) => `
            <div class="card" style="padding:24px; display:flex; flex-direction:column; justify-content:flex-start;">
              <div style="width:40px; height:4px; background:#DA6D24; border-radius:2px; margin-bottom:12px;"></div>
              <div style="font-family:'Cambria',Georgia,serif; font-size:26px; font-weight:700; color:${cfg.cor}; margin-bottom:8px; line-height:1.2;">
                ${termo}
              </div>
              <div style="font-size:18px; line-height:1.45; color:#1D2733;">
                ${mdHtml(def)}
              </div>
            </div>
          `).join("")}
        </div>
        ${rodape(slideNum)}
      </section>
    `);
  }

  // 10. Encerramento
  {
    slideNum++;
    const g = outro(cfg.abre);
    const cPath = cenaPath(g, "esq", "escuro");
    const borda = cenaBorda(g, "esq", "escuro");
    const zLeft = Math.round(borda * 1920 + 70);
    const zWidth = 1920 - 86 - zLeft;

    slidesHtml.push(`
      <section class="slide encerramento" style="background-image:url('file://${cPath}');">
        <div class="zona" style="left:${zLeft}px; width:${zWidth}px;">
          <img class="logo" src="file://${LOGO}" alt="Logo ATC">
          <h1 style="font-size:52px; line-height:1.15; margin-bottom:24px;">
            Aprender hoje.<br><span style="color:#F08A3E;">Ir mais longe amanhã.</span>
          </h1>
          <div style="font-size:24px; line-height:1.5; color:#D5DEE6; margin-bottom:44px; max-width:850px;">
            Continue o módulo ${mod.num} na plataforma ATC: vídeo-aulas, manual completo, exercícios e o seu guia virtual por voz.
          </div>
          <div style="font-size:17px; font-weight:700; color:#FFFFFF;">
            ATC – Angbu Training Centre · Cabinda, Angola
          </div>
        </div>
      </section>
    `);
  }

  return `
<!doctype html>
<html lang="pt-PT">
<head>
  <meta charset="utf-8">
  <title>${manual.course} · Módulo ${mod.num}</title>
  <style>
    @font-face {
      font-family: 'InstrumentSerif';
      src: url('file://${path.resolve(RAIZ, "static/fonts/InstrumentSerif.woff2")}');
    }
    @font-face {
      font-family: 'Geist';
      src: url('file://${path.resolve(RAIZ, "static/fonts/Geist.woff2")}');
      font-weight: 100 900;
    }

    @page {
      size: 1920px 1080px;
      margin: 0;
    }

    *, *::before, *::after {
      box-sizing: border-box;
    }

    html, body {
      margin: 0;
      padding: 0;
      width: 1920px;
      background: #0B2137;
      font-family: 'Geist', 'Calibri', 'Segoe UI', system-ui, sans-serif;
      color: #1D2733;
      -webkit-font-smoothing: antialiased;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }

    .slide {
      width: 1920px;
      height: 1080px;
      max-width: 1920px;
      max-height: 1080px;
      page-break-after: always;
      break-after: page;
      position: relative;
      overflow: hidden;
      background: #FFFFFF;
    }

    .slide.conteudo {
      background: #FFFFFF;
    }
    .slide.conteudo .top-stripe {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 8px;
    }
    .slide.conteudo .header {
      position: absolute;
      top: 32px;
      left: 86px;
      right: 86px;
      height: 110px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }
    .slide.conteudo .header .title-area {
      max-width: 1600px;
    }
    .slide.conteudo .header .breadcrumb {
      font-size: 14px;
      font-weight: 800;
      letter-spacing: 2.5px;
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .slide.conteudo .header h1 {
      margin: 0;
      font-family: 'Cambria', 'InstrumentSerif', Georgia, serif;
      font-size: 40px;
      font-weight: 700;
      color: #0B2137;
      line-height: 1.15;
    }
    .slide.conteudo .header .logo {
      width: 72px;
      height: 72px;
      object-fit: contain;
    }
    .slide.conteudo .content-body {
      position: absolute;
      top: 165px;
      left: 86px;
      right: 86px;
      bottom: 80px;
    }
    .slide.conteudo .footer {
      position: absolute;
      bottom: 0;
      left: 86px;
      right: 86px;
      height: 65px;
      border-top: 1.5px solid #E3E8EE;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 15px;
      color: #5F6B78;
    }

    .slide.capa, .slide.encerramento {
      background-size: cover;
      background-position: center;
    }
    .slide.capa .zona, .slide.encerramento .zona {
      position: absolute;
      top: 0;
      bottom: 0;
      display: flex;
      flex-direction: column;
      justify-content: center;
      padding: 0 40px;
    }
    .slide.capa .logo, .slide.encerramento .logo {
      width: 90px;
      height: 90px;
      object-fit: contain;
      margin-bottom: 30px;
    }
    .slide.capa .eyebrow {
      font-size: 16px;
      font-weight: 800;
      letter-spacing: 3.5px;
      text-transform: uppercase;
      color: #DA6D24;
      margin-bottom: 16px;
    }
    .slide.capa h1 {
      margin: 0 0 16px;
      font-family: 'Cambria', 'InstrumentSerif', Georgia, serif;
      font-size: 56px;
      font-weight: 700;
      color: #FFFFFF;
      line-height: 1.12;
    }
    .slide.capa h2 {
      margin: 0 0 20px;
      font-size: 32px;
      font-weight: 600;
      color: #F08A3E;
      line-height: 1.25;
    }
    .slide.capa .sub {
      font-size: 22px;
      color: #D5DEE6;
      line-height: 1.45;
      margin-bottom: 40px;
      max-width: 900px;
    }
    .slide.capa .footer-meta {
      font-size: 16px;
      color: #D5DEE6;
      line-height: 1.5;
    }
    .slide.capa .footer-meta b {
      color: #FFFFFF;
    }

    .slide.cena {
      background-size: cover;
      background-position: center;
    }
    .slide.cena .zona {
      position: absolute;
      top: 0;
      bottom: 0;
      display: flex;
      flex-direction: column;
      justify-content: center;
      padding: 0 40px;
    }
    .slide.cena .eyebrow {
      font-size: 15px;
      font-weight: 800;
      letter-spacing: 3px;
      text-transform: uppercase;
      color: #DA6D24;
      margin-bottom: 12px;
    }
    .slide.cena h1 {
      margin: 0 0 20px;
      font-family: 'Cambria', 'InstrumentSerif', Georgia, serif;
      font-size: 46px;
      font-weight: 700;
      color: #0B2137;
      line-height: 1.15;
    }
    .slide.cena .footer-cena {
      position: absolute;
      bottom: 0;
      height: 65px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 15px;
      color: #5F6B78;
    }

    .card {
      background: #F2F4F7;
      border: 1px solid #DCE3E9;
      border-radius: 14px;
      padding: 20px;
    }
    .card-white {
      background: #FFFFFF;
      border: 1px solid #DCE3E9;
      border-radius: 14px;
      box-shadow: 0 10px 25px rgba(11, 33, 55, 0.08);
    }
    .tip-card {
      background: #F2F4F7;
      border: 1px solid #DCE3E9;
      border-radius: 14px;
      padding: 16px 20px;
      display: flex;
      align-items: center;
      gap: 18px;
    }
    .tip-card.warn {
      background: #FBEDE6;
      border-color: #F0C7B4;
    }
    .tip-card .tip-avatar {
      width: 64px;
      height: 64px;
      border-radius: 50%;
      object-fit: cover;
      flex-shrink: 0;
    }
    .tip-card .tip-content {
      flex: 1;
    }
    .tip-card .tip-title {
      font-weight: 700;
      font-size: 16px;
      margin-bottom: 4px;
      color: #DA6D24;
    }
    .tip-card.warn .tip-title {
      color: #B3361F;
    }
    .tip-card .tip-text {
      font-size: 17px;
      line-height: 1.4;
      color: #1D2733;
    }

    .steps-list {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .step-item {
      display: flex;
      align-items: flex-start;
      gap: 16px;
    }
    .step-num {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: #DA6D24;
      color: #FFFFFF;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 18px;
      flex-shrink: 0;
      margin-top: 2px;
    }
    .step-text {
      font-size: 20px;
      line-height: 1.42;
      color: #1D2733;
      flex: 1;
    }

    table.atc-table {
      width: 100%;
      border-collapse: collapse;
      border: 1px solid #DCE3E9;
      border-radius: 12px;
      overflow: hidden;
      font-size: 18px;
    }
    table.atc-table th {
      background: #0B2137;
      color: #FFFFFF;
      font-weight: 700;
      text-align: left;
      padding: 14px 18px;
    }
    table.atc-table td {
      padding: 12px 18px;
      border-top: 1px solid #DCE3E9;
      color: #1D2733;
    }
    table.atc-table tr:nth-child(even) td {
      background: #F8FAFC;
    }
    table.atc-table tr:nth-child(odd) td {
      background: #FFFFFF;
    }

    .image-frame {
      background: #FFFFFF;
      border: 1px solid #DCE3E9;
      border-radius: 14px;
      padding: 10px;
      box-shadow: 0 10px 25px rgba(11, 33, 55, 0.08);
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }
    .image-frame img {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      border-radius: 6px;
    }
  </style>
</head>
<body>
  ${slidesHtml.join("\n")}
</body>
</html>
  `;
}

async function renderPdf(slug, browser) {
  const cfg = CURSOS[slug];
  const htmlContent = gerarHtml(slug);
  const tempHtmlPath = path.join(AQUI, `_deck_${slug}.html`);
  fs.writeFileSync(tempHtmlPath, htmlContent, "utf8");

  const page = await browser.newPage({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });

  const url = "file://" + tempHtmlPath;
  await page.goto(url, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);

  const destinoPdf = path.join(AQUI, `${cfg.ficheiro}.pdf`);
  const pdfBuf = await page.pdf({
    path: destinoPdf,
    width: "1920px",
    height: "1080px",
    printBackground: true,
    preferCSSPageSize: true,
    margin: { top: 0, right: 0, bottom: 0, left: 0 },
  });

  await page.close();
  try { fs.unlinkSync(tempHtmlPath); } catch (_) {}

  const stats = fs.statSync(destinoPdf);
  console.log(`[OK] ${cfg.ficheiro}.pdf (${(stats.size / 1024 / 1024).toFixed(2)} MB)`);
  return { file: `${cfg.ficheiro}.pdf`, size: stats.size };
}

(async () => {
  const alvos = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(CURSOS);
  const browser = await pw.chromium.launch({
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  });

  for (const c of alvos) {
    await renderPdf(c, browser);
  }

  await browser.close();
  console.log("Todas as apresentações PDF geradas com sucesso!");
})().catch((err) => {
  console.error("Erro na geração:", err);
  process.exit(1);
});
