# Amostra Windows ATC

1920 × 1080, 32 segundos, quatro cenas de 8 segundos, com legendas visíveis. Desde 14/10/2026 tem locução: Helena nas cenas 1 e 3, Miguel nas 2 e 4 (vozes ElevenLabs do guia por voz, em `voz/`). Para refazer a montagem depois de um novo render silencioso: `bash juntar_voz.sh <render-sem-som.mp4> ../../cursos/informatica/video/amostra-windows-atc.mp4`. Ver `GUIAO.md` e `cenas.json`. Os guiões devem ser cronometrados com as vozes reais antes da montagem final.

O MP4 usado pelo LMS fica em `../../cursos/informatica/video/amostra-windows-atc.mp4`, com poster e VTT. Os clips individuais de 8 segundos estão em `cenas/`.

## Editar ou reconstruir

```sh
npm ci
python3 build.py
npm run check
npx hyperframes preview --background
npx hyperframes render --quality delivery --output ../../cursos/informatica/video/amostra-windows-atc.mp4
```

`build.py` requer Pillow apenas para ler dimensões; não modifica os PNG. As edições raster foram realizadas com imagegen. O projeto inclui imagens, fontes e GSAP locais para renderização sem dependências de rede em tempo de execução. O ponteiro é adaptado do componente de registo `oversized-cursor`; destaca controlos sem inventar o resultado de um clique.

`BRIEF.md`, `design.md` e `STORYBOARD.md` registam as decisões. As imagens são simulações pedagógicas, identificadas no vídeo. Os retratos não são vídeos falantes; a locução personalizada será adicionada posteriormente.
