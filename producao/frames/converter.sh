#!/usr/bin/env bash
# Converte um vídeo nos fotogramas WebP da página inicial (substitui os provisórios).
# Uso (na pasta atc_lms):  bash producao/frames/converter.sh aplus   ~/Downloads/aplus.mp4
#                          bash producao/frames/converter.sh netplus ~/Downloads/netplus.mp4
# Cria static/frames/<nome>/0001.webp … (1280 px) e static/frames/<nome>/m/0001.webp … (720 px, telemóvel).
# A página conta os ficheiros sozinha; basta reiniciar o LMS.
set -euo pipefail
nome="$1"; video="$2"; fps="${FPS:-24}"
dest="static/frames/$nome"
[ -f "$video" ] || { echo "Vídeo não encontrado: $video"; exit 1; }
rm -rf "$dest"; mkdir -p "$dest/m"
ffmpeg -v error -i "$video" -vf "fps=$fps,scale=1280:-2" -c:v libwebp -quality 70 -compression_level 6 "$dest/%04d.webp"
ffmpeg -v error -i "$video" -vf "fps=$fps,scale=720:-2"  -c:v libwebp -quality 65 -compression_level 6 "$dest/m/%04d.webp"
echo "$nome: $(ls "$dest"/*.webp | wc -l | tr -d ' ') fotogramas, $(du -sh "$dest" | cut -f1) no total"
