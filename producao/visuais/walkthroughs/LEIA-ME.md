# Walkthroughs da ATC Formação

Três vídeos com a locução da Helena, gravados na plataforma real:

| Vídeo | Duração | Conteúdo |
| --- | --- | --- |
| `walkthrough-formando.mp4` | ~2 min | Página inicial, registo, plano e Multicaixa Express, escolha do guia, aula, dúvidas, manual, questionário e certificado |
| `walkthrough-formador.mp4` | ~1 min | Resumo, perguntas dos formandos e resposta na aula, relatório da turma, inscrição em lote, pagamento na loja |
| `walkthrough-admin.mp4` | ~1 min | Resumo, contas e perfis, pagamentos com comprovativo, códigos de acesso, cursos e verificação de certificados |

Os vídeos finais ficam em `saida/` (não versionados) e a versão web em `static/apresentacao/`, usada pela página `/apresentacao`.

## Como refazer

Requer o Google Chrome instalado, o ffmpeg e um ambiente Python com `playwright opencv-python-headless numpy requests pillow`.

```sh
python3 gerar_locucao.py                 # locução (só gera o que falta em locucao/<video>/)
python3 produzir.py formando saida/walkthrough-formando.mp4
python3 produzir.py formador saida/walkthrough-formador.mp4
python3 produzir.py admin    saida/walkthrough-admin.mp4
bash publicar.sh                         # na pasta atc_lms: versão web e capas para /apresentacao
```

- `roteiros.json`: textos da locução e títulos de capítulo. Ao mudar um texto, apague o mp3 correspondente e volte a correr `gerar_locucao.py`.
- `preparar_dados.py`: cada execução de `produzir.py` cria uma base de demonstração nova (formandos fictícios de várias províncias, progresso, perguntas, pagamentos, códigos) e arranca o LMS na porta 8095. A base real (`dados/atc.db`) nunca é tocada.
- `produzir.py`: uma função por secção (por exemplo `f3` para os planos). Os zooms seguem os cliques; a gravação nunca é abrandada e cobre sempre a locução.
- A chave da ElevenLabs vem de `ATC_ELEVEN_KEY` ou de `~/.config/atc-lms/elevenlabs.env`; nunca é guardada no projeto.
- Todos os dados que aparecem nos vídeos são fictícios, incluindo o comprovativo bancário (`comprovativo-exemplo.png`).
