# ATC LMS: handoff for the local (Claude Desktop) session

Updated: 12 October 2026. Read this first, then `README.md`. The older `handoff.md` covers the Office sample screenshots done earlier by another assistant.

## Goal

Build working **samples** of the courses and the LMS for ATC (Angbu Training Centre, Luanda, Angola). The owner sends them to the client with a quotation. Full development starts once the client agrees the time frame and the invoice.

## Where everything is

- **Repository:** `almeidaojose36/atc_lms`.
- **Branch:** `claude/modest-franklin-264d3y`. All work is here and it is **not merged into `main`**. Pull this branch before starting.
- **Language:** the user writes in English. Learner-facing content is **European Portuguese (PT-PT)** with an Angolan audience in mind.

## What is done

### LMS (`atc_lms.py`, single-file Python server with SQLite; no packages needed)
- **Guide choice:** the learner picks a virtual guide, Helena or Miguel, once. That choice drives every later screen: header chip, videos and manual images. "Mudar de guia" switches everything and returns to the same page.
- **First visit:** a five-step start at `/comecar` (guide, welcome, profile, tour, first course).
- **Informática course:** intro clips, lesson 1.1 and 1.2 clips, and a manual whose Windows images follow the guide. These images are AI-edited simulations and are labelled as such.
- **Sample courses:** Word, Excel, PowerPoint and Outlook are published with status `amostra`. They have module 1 manuals and "Ver exemplos" pages, and they never issue certificates.
- **No burned-in captions:** clips carry no captions in the picture; the player shows `.vtt` subtitles, and "Ler o texto" gives the transcript.
- **Guide portraits:** `static/presenters/{helena,miguel}.png` are the blazer portraits the user supplied.
- **Voice guide:** on lessons 1.1 and 1.2. See `producao/GUIA_POR_VOZ.md` and the section below.
- **Tests:** `python -m unittest discover -s tests`, 30 tests, all passing.

### Media and documents
- **Avatar clips:** 18 approved clips (H1–H9, M1–M9) in `producao/videos/avatar-video-final/`. They are placed in the LMS through `plataforma/apresentadores/` and `cursos/informatica/apresentadores/`.
- **Voices (ElevenLabs):**
  - Helena = Claudia `JGnWZj684pcXmK2SxYIv`. Her voice has an echo, so it goes through `/v1/audio-isolation`, which needs clips of 4.6 s or more.
  - Miguel = Marcos `FbFkkfp4Iv6U5Q1WC4C2`.
- **Walkthrough video (1:43):** `producao/visuais/walkthrough/walkthrough-atc.mp4`, approved by the user. The production script is in the same folder.
- **PowerPoint decks:** five, one per manual, in `producao/apresentacoes/`. They are generated from the manual JSON and the avatar photos (`producao/visuais/manual-avatares/`); see that folder's `LEIA-ME.md`.

## Voice guide (option 2: own pipeline with cache, chosen by the user)

- **Flow:** the learner speaks, ElevenLabs Scribe turns it into text, then the answer comes from (in order):
  1. the answer cache (`voice_answers` table);
  2. the curated questions in `cursos/<curso>/voz/<aula>.json`;
  3. a local Ollama model, if one is installed;
  4. otherwise "ask the trainer".
- **Audio:** answers are spoken in the chosen guide's voice. Audio for the curated answers is pre-recorded and committed in `cursos/informatica/voz/audio/`, so it costs nothing at run time.
- **Matcher rule:** most of the question's words must be covered, so off-topic questions ("copiar ficheiro") go to the trainer instead of getting a wrong answer.
- **Limits and logging:** 40 questions per learner per day (`ATC_VOZ_LIMITE`). The `voice_log` table records the answer source and what was paid.
- **Adding a lesson:** write the JSON, then run `python3 producao/vozes/gerar_voz_aula.py <curso> <aula>`.
- **Key:** read from the environment variable **`ATC_ELEVEN_KEY`**. Never put it in code or the repo, and never ask the user to paste it into chat; the user types it into their environment or hosting panel. The account is on the **Creator** (paid) plan, so commercial use is covered. A free-account key also works for demos, with low quotas.

## Run locally (Windows)

1. Install Python 3 and tick "Add to PATH".
2. Open a Command Prompt in the repo folder.
3. To use the voice guide, type `set ATC_ELEVEN_KEY=<key>`. The user does this step themselves.
4. Run `iniciar.bat`, or `py atc_lms.py`, then open http://localhost:8080. The microphone works on localhost without HTTPS.
5. Demo accounts:
   - `formando@atc.ao` / `formando123`
   - `formador@atc.ao` / `formador123`
   - `admin@atc.ao` / `admin123`

The tracked database `dados/atc.db` is the deployment seed. **Do not commit changes to it.** For testing, point the app at a copy with `ATC_DADOS=<folder>`.

## Next task: host the LMS on a client subdomain

The user wants a subdomain on the client's domain so the client can try the LMS. The client's domain DNS is on one platform, and the client also has a shared hosting plan with many website slots. Their wording was unclear; it sounded like "fifty websites".

1. **Find out** the hosting company and plan, and where the domain's DNS is managed. Use the built-in browser; **the user signs in themselves**.
2. **Check the hosting panel for "Setup Python App"**, as offered by cPanel/CloudLinux. The LMS is a long-running Python HTTP server (`BaseHTTPRequestHandler`), not WSGI.
   - If the panel has it, write a small WSGI adapter, or run it under Passenger.
   - If it is PHP-only, which is common on shared plans, recommend a small Linux VPS at about $5–6 a month. The setup with Caddy for automatic HTTPS and systemd is in `README.md` under deployment.
3. **HTTPS is required**, because the voice guide needs the microphone.
4. **Create the subdomain** (for example `lms.<clientdomain>`) with a DNS A record, or a CNAME, pointing to the server. This is done wherever the DNS is managed.
5. **Set the key:** the user types `ATC_ELEVEN_KEY` into the server or panel environment variables. Also set `ATC_DADOS` to a writable folder.
6. **Before sharing:** change the demo passwords and turn off the demo notice in Gestão.

## Open points to mention to the client

- **Windows images:** the Windows images in the manuals and decks are **AI-edited simulations**. Real Windows 11 PT-PT captures are listed in `producao/ENTREGAR_PELA_ATC.md`.
- **Office icons:** the icons are look-alike replicas, not the official logos. Official logos need the Microsoft and CompTIA partner kits.
- **Missing exercise 1.2:** the lesson 1.2 video tells learners to do "exercício 1.2 do manual", but the module 1 manual only has exercise 1.1. Either add the exercise or fix the video.
- **Old demo videos:** `aula-1-1.mp4`, `aula-1-2.mp4` and `amostra-windows-atc.mp4` have burned-in text, so they show double captions with the player's subtitles. They can be re-exported only if the source files are provided.
- **Voice guide testing:** it was tested with generated voices only. It should be tested with a few real learners for Angolan accents.
- **Course content:** Word, Excel, PowerPoint, Outlook and CompTIA have only sample module 1 content. The full courses are part of the paid phase.

## Working conventions

- Commit with clear messages and push to `claude/modest-franklin-264d3y`. Don't open a pull request unless the user asks.
- Keep learner text in PT-PT. Don't invent course content: the voice guide and the decks only use what is in the lessons and manuals.
- Build tools used in the cloud session (not needed to run the LMS): ffmpeg, Playwright with Chromium, OpenCV, and Node with `pptxgenjs` and `sharp` for the decks.
