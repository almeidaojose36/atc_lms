# ATC LMS — handoff

Updated: 10 October 2026.

## Delivered

Six real screenshots of ATC training examples in Word, Excel and PowerPoint for the Web, with Portuguese (Portugal) interfaces. Each course has two instruction cards: a task title, screenshot, three steps and a result to check. Excel and PowerPoint also include these cards in their existing online manuals.

The catalogue exposes **Ver exemplos** while the full courses remain **Em breve**. Viewing the samples does not change enrolment, progress or course completion.

## Files to reproduce the LMS samples

- `atc_lms.py`: catalogue links, sample pages and authenticated sample-image routes.
- `cursos/{word,excel,powerpoint}/manual/exemplos-atc.json`: instruction-card content.
- `cursos/{word,excel,powerpoint}/manual/figures/amostra-*.jpg`: six screenshots.
- `cursos/{word,excel,powerpoint}/manual/exemplos-atc.html`: standalone printable samples. Keep each HTML file beside its `figures/` directory.
- `cursos/excel/manual/modulo-1.json` and `cursos/powerpoint/manual/modulo-1.json`: updated online manuals.
- `producao/imagens-instrucionais-office/manifesto.json`: screenshot inventory and hashes.
- `tests/test_instruction_examples.py`: sample-route authentication, image allowlist and card-rendering checks.

## Run locally

Python 3 is sufficient for the LMS; no extra package installation is required.

```sh
python3 atc_lms.py servir --host 127.0.0.1 --porta 8080
```

Sign in using an existing LMS account, open the catalogue and choose **Ver exemplos**. Direct paths:

- `/cursos/word/exemplos`
- `/cursos/excel/exemplos`
- `/cursos/powerpoint/exemplos`

The sample-image endpoint serves only files declared in the sample JSON and requires a signed-in account. Other course assets retain their existing access controls.

## Updating the samples

Capture a real ATC exercise with a single clear teaching objective. Save the screenshot in that course's `manual/figures/` directory. Update its figure name, caption, steps and result in `exemplos-atc.json`; update the standalone HTML to match. If needed, add the same task to `modulo-1.json`.

Keep interface terms in Portuguese (Portugal), use fictional training data, and identify the application version as **para a Web**. Application commands can differ in installed versions. There are no new video deliverables in this image-sample handoff.

## Verification and repository

```sh
python3 -m unittest discover -s tests -q
git diff --check
```

Twelve tests passed. All three sample pages and the catalogue links were verified in the in-app browser. The repository is `https://github.com/almeidaojose36/atc_lms.git`, branch `main`.

The local `dados/atc.db` contains account and learner state. It is excluded from this update; preserve the existing deployment database.
