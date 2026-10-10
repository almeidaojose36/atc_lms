# Percurso do formando e o guia escolhido

O formando escolhe **uma vez** a Helena ou o Miguel. A escolha vale para toda a plataforma: o guia aparece no cabeçalho de todos os ecrãs, nos vídeos de cada passo e nas imagens do manual. Pode mudar a qualquer momento em «Mudar de guia» (`/apresentador`); tudo muda de uma vez.

## Sequência de entrada (`/comecar`)

| Passo | Ecrã | Clip (Helena / Miguel) |
|---|---|---|
| 1 | Escolher o guia (`/comecar/guia`) | retratos |
| 2 | Boas-vindas (`/comecar/boas-vindas`) | H4 / M5 |
| 3 | O seu perfil (`/comecar/perfil`, com o formulário) | H5 / M7 |
| 4 | A plataforma (`/comecar/passeio`) | H6 / M1 |
| 5 | O primeiro curso (`/comecar/curso`) | H1 / M2 |

Um formando sem guia é levado para este percurso ao abrir a plataforma. Cada passo pode ser saltado. Quem já tinha escolhido um apresentador por curso passa a ter essa escolha em toda a plataforma.

## Dentro do curso Informática

| Ecrã | Clip (Helena / Miguel) |
|---|---|
| Introdução do curso | H7 / M6 (boas-vindas ao curso) e H2 / M4 (o que vai aprender) |
| Aula 1.1, «Antes de começar» | H3 / M3 (abertura da aula) e H9 / M8 (como ver a demonstração) |
| Aula 1.2, «Antes de começar» | H9 / M8 |
| Manual online | H8 / M9 |
| Manual, figuras 1.2, 1.4 e 1.6 | ecrãs Windows personalizados do guia (`manual/figures/windows-atc/{helena,miguel}`) |

Os ecrãs Windows são simulações pedagógicas editadas por IA e dizem-no na legenda.

## Ficheiros

- Clips da plataforma: `plataforma/apresentadores/{helena,miguel}/*.mp4` + `.vtt`, `plataforma/clips.json`.
- Clips do curso: `cursos/informatica/apresentadores/{helena,miguel}/*.mp4` + `.vtt`, `clips.json` (títulos e textos) e `fluxo.json` (que clip aparece onde).
- Gerados por `producao/videos/preparar_clips_lms.py` a partir de `producao/videos/avatar-video-final/`.
- Os vídeos **não têm legendas gravadas**: as legendas vêm da faixa `.vtt`, mostrada pelo leitor, e há um botão «Ler o texto» com a transcrição.
- Novo curso: acrescentar `apresentadores/<guia>/*.mp4`, `clips.json` e `fluxo.json` à pasta do curso.
