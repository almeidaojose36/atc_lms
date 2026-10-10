# Conversão manual de voz no ElevenLabs (H1, H6, M2)

Objectivo: comparar o resultado da interface do ElevenLabs com o da API, para saber se o problema é a API ou a própria funcionalidade.

Ficheiros: `H1-audio-original.wav`, `H6-audio-original.wav` (Helena) e `M2-audio-original.wav` (Miguel). São o áudio dos clips do Flow, sem alterações.

## Passos (Voice Changer)
1. ElevenLabs › **Voice Changer** (Speech to Speech).
2. Voz: Helena = **ATC Helena** (Claudia); Miguel = **ATC Miguel (Marcos)**.
3. Modelo: **Eleven Multilingual v2 (Speech to Speech)**.
4. Definições usadas na API: Stability **0,60**, Similarity **0,85**, **Remove background noise** ligado.
5. Carregar o ficheiro, gerar e descarregar em MP3. Nomes: `H1-ui.mp3`, `H6-ui.mp3`, `M2-ui.mp3`.
6. Só para Helena: passar o resultado pelo **Voice Isolator** (retira o eco) e descarregar de novo.

Se o sotaque ficar errado, repetir 2 ou 3 vezes com Stability diferente (0,35 e 0,85) e guardar cada tentativa com um sufixo (`-a`, `-b`, `-c`).

## O que acontece depois
O áudio é colocado por baixo do vídeo original (a duração coincide), com o volume normalizado, e os ecrãs reais do LMS são aplicados como nos outros clips.
