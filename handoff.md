# ATC LMS — Full Session Handoff (`HANDOFF.md`)

**Updated:** 17 October 2026  
**Project:** ATC E-Learning Platform & 7-Course Production Pack  
**Client:** ATC – Angbu Training Centre · Grupo Angbu · Cabinda, Angola  
**Author / Producer:** Almeida José  
**Repository:** `almeidaojose36/atc_lms` · **Branch:** `claude/modest-franklin-264d3y`  
**Workspace Root:** `/Users/almeidajose/Documents/A/App/ATC 2/atc_lms`

---

## 1. Executive Summary of What Was Done in This Chat

### A. Platform UI, Workstation Login Illusion & Video Player Fixes
- **Workstation / OS Login Illusion (`/apresentacao` & Onboarding):**
  - Redesigned the interactive client trial section in `atc_lms.py` and `static/atc.css` (`static/inicio.css`, `static/inicio.js`) to mimic logging into a physical desktop computer (**ATC Workstation OS**), complete with monitor bezel, status bar, user profile tiles (Formando, Formador, Administração), and one-click credential copy/launch.
- **Video Player Text & Info Visibility Fix:**
  - Fixed the issue where text overlays and metadata obscured video content during playback (`atc_lms.py`, `static/player.js`, `static/atc.css`). Overlays now auto-hide smoothly when playback begins and dock cleanly outside the active video area.
- **Test Suite:**
  - All **47 unit tests** (`python3 -m unittest discover tests`) pass without regressions.

### B. Commercial Proposal & Financial Rebalancing (Option B)
- **Course Price Redistribution (Option B):**
  - Shifted weight away from Phase 2 so individual courses feel balanced and Phase 1 provides stronger initial cash flow:
    - **Phase 1 (Informática & Office — 5 courses):** **550 000,00 Kz** (was 430 000 Kz)
    - **Phase 2 (CompTIA A+ & Network+ — 2 courses):** **450 000,00 Kz** (was 570 000 Kz)
    - **Grand Total:** **1 000 000,00 Kz**
    - **Immediate 1st Payment (50% of Phase 1):** **275 000,00 Kz** (was 215 000 Kz)
- **Page & Image Volume Estimates Added:**
  - Embedded estimated manual pages (**~500 pages** total) and instructional images/diagrams (**~340 images** total) alongside video hours (**23,5 h** total) in both the WhatsApp slides and the Proforma Invoice.

### C. Proforma Invoice (`Fatura-Proforma-PF-2026-001.pdf`)
- **Strictly 2 A4 Pages:** Verified via PyMuPDF (`fitz`).
- **Banking Details Removed:** Removed the Bank/IBAN block completely from Page 2 as requested.
- **Work Hours & Production Schedule Added:** Added the **«Regime e carga horária»** section on Page 2 stating:
  - **Daily dedication:** Average of **not less than 8 hours/day** (8+ hours/day of specialized technical and pedagogical production).
  - **Shifts:** Production carried out across **mornings, afternoons, and late nights** as agreed to meet milestones.
  - **Total estimated effort:** **~360 to 400+ hours** over the ~2-month project schedule.
  - **Continuous alignment:** Regular progress check-ins and early deliverable reviews with ATC.

### D. Pedagogical & European Portuguese (PT-PT) Overhaul of All 7 Sample Courses
- **Manuals (`cursos/*/manual/modulo-1.json`):**
  - Reviewed and upgraded all 7 courses (`informatica`, `word`, `excel`, `powerpoint`, `outlook`, `comptia-a-plus`, `comptia-network-plus`) for strict **European Portuguese (PT-PT)** terminology (*ecrã, rato, ficheiro, pasta, separador, friso, guardar, transferir, folha de cálculo, diapositivo, endereço IP, encaminhador, comutador*) and **Cabinda, Angola** workplace scenarios.
  - Expanded every course's formative quiz to **6 questions** and glossary to **6–8 essential terms**.
- **PowerPoint Presentations (`producao/apresentacoes/*.pptx`):**
  - Upgraded `gerar_apresentacoes.js` with course-colored top brand stripes, pedagogical breadcrumbs (`MÓDULO 1 · TEMA X DE Y`), green **«Critério de sucesso»** banners on lab slides, 2×2 formative quiz grids (4 questions per deck), 3×2 glossary grids, and 100% trainer speaker notes (`[Guia do Formador ATC]`).
- **Lightweight PDF Presentations for WhatsApp (`producao/apresentacoes/*.pdf`):**
  - Created `gerar_apresentacoes_pdf.js` (Playwright + Chrome headless) to export crisp 16:9 vector PDFs (3.1 MB to 7.1 MB) alongside the heavier `.pptx` files so they can be sent effortlessly via WhatsApp.

---

## 2. Pricing & Deliverables Table (Option B)

| Course | Video | Est. Manual | Est. Images | Option B Price |
| :--- | :---: | :---: | :---: | :---: |
| **Fase 1 · Informática e Office** | | | | |
| Informática na Ótica do Utilizador | 2,0 h | ~45 págs. | ~30 | 110 000,00 Kz |
| Microsoft Word | 2,0 h | ~45 págs. | ~30 | 110 000,00 Kz |
| Microsoft Excel | 3,0 h | ~65 págs. | ~45 | 140 000,00 Kz |
| Microsoft PowerPoint | 1,5 h | ~35 págs. | ~25 | 100 000,00 Kz |
| Microsoft Outlook | 1,0 h | ~25 págs. | ~15 | 90 000,00 Kz |
| **Subtotal Fase 1** | **9,5 h** | **~215 págs.** | **~145** | **550 000,00 Kz** |
| **Fase 2 · CompTIA (com laboratórios)** | | | | |
| CompTIA A+ (220-1201/1202) | 8,0 h | ~160 págs. | ~110 | 240 000,00 Kz |
| CompTIA Network+ (N10-009) | 6,0 h | ~125 págs. | ~85 | 210 000,00 Kz |
| **Subtotal Fase 2** | **14,0 h** | **~285 págs.** | **~195** | **450 000,00 Kz** |
| **Incluído sem custo** | | | | |
| Plataforma LMS online + Sessão formadores | — | — | — | **Oferta** |
| **TOTAL DO PROJETO** | **23,5 h** | **~500 págs.** | **~340** | **1 000 000,00 Kz** |

### Payment Milestones (50% on phase approval / 50% on phase delivery)
1. **Aprovação da Fase 1 (agora):** `275 000,00 Kz`
2. **Entrega da Fase 1 (~4 semanas):** `275 000,00 Kz`
3. **Aprovação da Fase 2:** `225 000,00 Kz`
4. **Entrega da Fase 2 (~8 semanas globais):** `225 000,00 Kz`

---

## 3. Key Files & Locations

### Client Commercial Pack
- **Proforma Invoice HTML:** `atc_lms/producao/cliente/proforma/proforma.html`
- **Proforma Invoice PDF (2 pages A4):** `atc_lms/producao/cliente/proforma/Fatura-Proforma-PF-2026-001.pdf`
- **WhatsApp Slides HTML:** `atc_lms/producao/cliente/whatsapp/slides.html`
- **WhatsApp Slides PNGs (1200×1500):**
  - `atc_lms/producao/cliente/whatsapp/ATC-Formacao-1.png`
  - `atc_lms/producao/cliente/whatsapp/ATC-Formacao-2.png`
  - `atc_lms/producao/cliente/whatsapp/ATC-Formacao-3.png`

### Course Presentations (PDF & PPTX)
Located in `atc_lms/producao/apresentacoes/`:
- `Informatica_Modulo1.pdf` (7,15 MB, 19 slides) & `Informatica_Modulo1.pptx` (9,6 MB)
- `Word_Modulo1.pdf` (3,21 MB, 15 slides) & `Word_Modulo1.pptx` (5,5 MB)
- `Excel_Modulo1.pdf` (4,69 MB, 18 slides) & `Excel_Modulo1.pptx` (6,6 MB)
- `PowerPoint_Modulo1.pdf` (3,48 MB, 16 slides) & `PowerPoint_Modulo1.pptx` (5,7 MB)
- `Outlook_Modulo1.pdf` (3,10 MB, 15 slides) & `Outlook_Modulo1.pptx` (5,4 MB)
- `CompTIA_A+_Modulo1.pdf` (5,05 MB, 18 slides) & `CompTIA_A+_Modulo1.pptx` (7,4 MB)
- `CompTIA_Network+_Modulo1.pdf` (4,65 MB, 21 slides) & `CompTIA_Network+_Modulo1.pptx` (7,1 MB)
- **Generators:** `gerar_apresentacoes.js` (PPTX) and `gerar_apresentacoes_pdf.js` (PDF)

### Course Manuals (JSON)
- `atc_lms/cursos/{informatica,word,excel,powerpoint,outlook,comptia-a-plus,comptia-network-plus}/manual/modulo-1.json`

### LMS Application & Static Assets
- `atc_lms/atc_lms.py` — Main server & routes (including `/apresentacao`)
- `atc_lms/static/atc.css`, `inicio.css`, `inicio.js`, `player.js`, `voz.js`

---

## 4. Commands to Run & Regenerate Everything

### Start the LMS Server
```sh
cd "/Users/almeidajose/Documents/A/App/ATC 2/atc_lms"
python3 atc_lms.py
# Default: http://127.0.0.1:8000 (or pass: servir --host 0.0.0.0 --porta 8080)
```

### Run the Test Suite
```sh
cd "/Users/almeidajose/Documents/A/App/ATC 2/atc_lms"
python3 -m unittest discover tests
```

### Regenerate PowerPoint (`.pptx`) Decks
```sh
cd "/Users/almeidajose/Documents/A/App/ATC 2/atc_lms"
PPTX_SKILL="/Users/almeidajose/Documents/K/KiddieCanvas/tmp/pptx/editable-book" \
NODE_PATH="/Users/almeidajose/Documents/K/KiddieCanvas/tmp/pptx/editable-book/node_modules" \
node producao/apresentacoes/gerar_apresentacoes.js
```

### Regenerate WhatsApp-Ready PDF (`.pdf`) Decks
```sh
cd "/Users/almeidajose/Documents/A/App/ATC 2/atc_lms"
node producao/apresentacoes/gerar_apresentacoes_pdf.js
```

### Regenerate Proforma PDF & WhatsApp PNG Slides
```sh
cd "/Users/almeidajose/Documents/A/App/ATC 2/atc_lms"
node -e '
const path = require("path");
const pw = require("/Users/almeidajose/Documents/K/KiddieCanvas/tmp/pptx/editable-book/node_modules/playwright");
(async () => {
  const browser = await pw.chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" });
  const page = await browser.newPage();
  await page.goto("file://" + path.resolve("producao/cliente/proforma/proforma.html"), { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({ path: "producao/cliente/proforma/Fatura-Proforma-PF-2026-001.pdf", format: "A4", printBackground: true, preferCSSPageSize: true });

  const sPage = await browser.newPage({ viewport: { width: 1200, height: 1500 } });
  await sPage.goto("file://" + path.resolve("producao/cliente/whatsapp/slides.html"), { waitUntil: "networkidle" });
  await sPage.evaluate(() => document.fonts.ready);
  for (let i = 1; i <= 3; i++) {
    await sPage.locator("#s" + i).screenshot({ path: `producao/cliente/whatsapp/ATC-Formacao-${i}.png` });
  }
  await browser.close();
})();
'
```

---

## 5. Pending Items Before Sending to Client

1. **Fill Yellow Fields in `proforma.html` (if desired before sending):**
   - Emitter NIF and phone/email (`[preencher]`, `[telefone / email]`).
   - Client NIF and contact person name (`[preencher]`, `[nome do responsável]`).
   - IVA line (`[regime a confirmar]`).
2. **Deploy Latest `atc_lms.py` & `static/` to `lms.grupoangbu.com`:**
   - Ensure the remote server has the updated `/apresentacao` workstation UI and video player fixes before sharing the link.
3. **Send via WhatsApp in Order:**
   - Album of 3 PNG slides (`ATC-Formacao-1.png` to `3.png`) with HD enabled.
   - Accompanying WhatsApp message.
   - `Fatura-Proforma-PF-2026-001.pdf` + the 7 `*_Modulo1.pdf` presentation decks.
   - Demo login credentials in a separate message (`formando@atc.ao` / `formando123`, `formador@atc.ao` / `formador123`, `admin@atc.ao` / `admin123`).
