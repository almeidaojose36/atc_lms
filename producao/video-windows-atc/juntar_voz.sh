#!/usr/bin/env bash
# Junta a locução (Helena nas cenas 1 e 3, Miguel nas 2 e 4) ao vídeo silencioso da amostra.
# As falas foram geradas com o guia por voz do LMS (mesmas vozes ElevenLabs): voz/cena*.mp3.
# Uso: bash juntar_voz.sh <video-sem-som.mp4> <saida.mp4>
set -euo pipefail
cd "$(dirname "$0")"
ENTRADA="$1"; SAIDA="$2"
n() { echo "[$1]loudnorm=I=-16:TP=-1.5:LRA=7:linear=true,aresample=48000,volume=$3,adelay=$2|$2[a$1]"; }
ffmpeg -v error -y -i "$ENTRADA" -i voz/cena1-helena.mp3 -i voz/cena2-miguel.mp3 -i voz/cena3-helena.mp3 -i voz/cena4-miguel.mp3 \
  -filter_complex "$(n 1 400 1.0);$(n 2 8400 1.35);$(n 3 16400 1.0);$(n 4 24400 1.35);[a1][a2][a3][a4]amix=inputs=4:normalize=0,apad,atrim=0:32,aformat=channel_layouts=stereo[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 128k -ar 48000 -movflags +faststart "$SAIDA"
