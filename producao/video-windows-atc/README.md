# Amostra Windows ATC

1920 × 1080, 32 segundos, quatro cenas de 8 segundos. Demonstração silenciosa com legendas visíveis; preparada para receber as vozes de Helena e Miguel com sotaque angolano. Ver `GUIAO.md` e `cenas.json`. Os guiões devem ser cronometrados com as vozes reais antes da montagem final.

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
