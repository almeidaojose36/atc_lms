# Prompts: fotogramas inicial e final para a página inicial

Ordem: 1 → 2 → 3 → 4, depois os dois vídeos. Todas as imagens em 16:9 (1920×1080).
Regra comum: fundo azul-marinho #0B2137, luz de contorno laranja #F08A3E, terço esquerdo escuro e vazio (é onde fica o texto), sem texto nem logótipos.

## A+ (o computador monta-se)

### 1. Imagem final A+ (gerar)
Photorealistic product shot of a modern mid-tower desktop PC, seen at a three-quarter angle from the front-left, with the tempered-glass side panel facing the camera. Inside: motherboard, CPU cooler, two RAM sticks, a graphics card, an M.2 SSD, a power supply at the bottom, tidy cables. Deep navy studio background (#0B2137) with a soft vignette, warm orange rim light (#F08A3E) outlining the case edges, subtle cool fill light. The PC sits in the right two-thirds of the frame; the left third is empty, dark negative space. Shallow depth of field, premium tech advert, 16:9, no text, no logos, no people.

### 2. Imagem inicial A+ (editar a imagem 1)
Edit this image: keep exactly the same camera angle, background, lighting and empty PC case. Remove the glass side panel and take the components out of the case so they float in mid-air around it, evenly spaced and fully visible, not overlapping: motherboard on the left of the case, graphics card above, RAM sticks and CPU in front, SSD and power supply to the right. Each part keeps a soft orange rim light. Keep the left third of the frame dark and empty. No text, no logos.

### Vídeo A+ (imagem 2 → imagem 1)
The floating computer components glide smoothly into the open PC case one at a time and click into place, then the glass side panel slides closed. Fixed camera with a very slow push-in, continuous motion, no cuts, no camera shake, no new objects, photorealistic. 6 seconds.

## Network+ (pacotes pela rede)

### 3. Imagem inicial Network+ (gerar; usar a imagem 1 como referência do PC)
Wide 3D scene on a deep navy background (#0B2137). A small network laid out from centre to right: the same desktop PC as the reference image on the left, a network switch, a router, a stylised glowing wireframe globe for the internet, and a server rack on the right. Thin dark cables connect them in a gentle curve rising from the PC to the globe and dropping to the server. Everything is unlit and calm, with only a faint orange rim light (#F08A3E) on the edges. The left third of the frame is empty, dark negative space. Clean premium tech look, slight depth of field, 16:9, no text, no logos.

### 4. Imagem final Network+ (editar a imagem 3)
Edit this image: keep exactly the same layout, camera and devices. Now the cables glow bright orange (#F08A3E), several small glowing orange light pulses (data packets) are spaced along the cables, the server rack has its status lights on, the router and switch glow softly, and the globe is lit with fine orange lines. Keep the left third of the frame dark and empty. No text, no logos.

### Vídeo Network+ (imagem 3 → imagem 4)
Orange light pulses leave the PC and travel along the cables through the switch and the router, across the globe and into the server; each device lights up as a pulse passes, until the whole network glows. Fixed camera with a very slow lateral drift, continuous motion, no cuts, no camera shake, no new objects. 6 seconds.

## Depois
Na pasta `atc_lms`:

    bash producao/frames/converter.sh aplus   ~/Downloads/aplus.mp4
    bash producao/frames/converter.sh netplus ~/Downloads/netplus.mp4

## Vídeos instalados (16 out. 2026)
Origem: `atc_lms-main/Landing page videos/`.

- **A+** (`Computer components assembling.mp4`, 5,3 s, 60 fps): o vídeo gerado vai do PC montado para as peças soltas, por isso foi invertido.
  Cortaram-se os primeiros 0,6 s (rotação da câmara com imagem esborratada) e aplicou-se uma correção de cor para o fundo cinzento ficar azul-marinho:

      ffmpeg -ss 0.6 -i "Computer components assembling.mp4" -an -vf "reverse,colorbalance=rs=-0.10:gs=-0.03:bs=0.16:rm=-0.04:bm=0.05,eq=saturation=1.05:brightness=-0.03" -c:v libx264 -crf 14 -pix_fmt yuv420p aplus.mp4
      bash producao/frames/converter.sh aplus aplus.mp4

  Limitação conhecida: o fundo tem um padrão de xadrez (a grelha de transparência do editor de imagem ficou na imagem inicial). Para o eliminar, gerar de novo a imagem 2 com fundo liso.
- **Network+** (`Light pulses travel through network.mp4`, 8 s): usado tal como está, a 15 fps para reduzir o peso:

      FPS=15 bash producao/frames/converter.sh netplus "Light pulses travel through network.mp4"

- No ecrã largo, a sequência A+ é deslocada 18 % para a direita para não ficar por baixo do texto (`LANDING_SEQUENCES` em `atc_lms.py`).
