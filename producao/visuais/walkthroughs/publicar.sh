#!/usr/bin/env bash
# Copia os walkthroughs para a página /apresentacao: versão web (H.264, faststart) e imagem de capa.
# Uso (na pasta atc_lms): bash producao/visuais/walkthroughs/publicar.sh
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
DEST="static/apresentacao"
mkdir -p "$DEST"
for v in formando formador admin; do
  src="$AQUI/saida/walkthrough-$v.mp4"
  [ -f "$src" ] || { echo "Falta $src"; exit 1; }
  ffmpeg -v error -y -i "$src" -c:v libx264 -preset slow -crf 24 -profile:v high -pix_fmt yuv420p \
         -c:a aac -b:a 128k -movflags +faststart "$DEST/walkthrough-$v.mp4"
  # capa: um momento representativo de cada vídeo (depois do cartão de abertura)
  case $v in formando) t=5 ;; formador) t=26 ;; admin) t=31 ;; esac
  ffmpeg -v error -y -ss "$t" -i "$src" -frames:v 1 -vf "scale=1280:-2" -q:v 3 "$DEST/$v.jpg"
  echo "$v: $(du -h "$DEST/walkthrough-$v.mp4" | cut -f1)"
done
