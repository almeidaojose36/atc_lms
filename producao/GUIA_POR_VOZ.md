# Guia por voz (protótipo: Informática, aula 1.1)

O formando carrega no microfone na página da aula, faz a pergunta em voz alta e o guia que escolheu (Helena ou Miguel) responde por escrito e em voz. Também pode escrever a pergunta.

## Como responde (do mais barato para o mais caro)
1. **Cache** (`voice_answers`): respostas já dadas nesta aula para a mesma pergunta. Custo zero.
2. **Perguntas frequentes** (`cursos/<curso>/voz/<aula>.json`): respostas escritas a partir da aula e do manual. Custo zero.
3. **Modelo local (Ollama)**, se estiver instalado: responde com base na transcrição e no manual; a resposta fica em cache.
4. **"Pergunte ao formador"**: se nada servir, o guia encaminha para a secção Perguntas e dúvidas. Nunca inventa.

## Custos
- **Ouvir a pergunta** (ElevenLabs Scribe): paga-se em cada pergunta falada, alguns segundos de áudio. As perguntas escritas não pagam nada.
- **Falar a resposta**: as respostas frequentes e as frases fixas já vêm gravadas com o curso (`voz/audio/`), nas duas vozes. Só as respostas novas do modelo local geram áudio, uma única vez (`dados/voz/`).
- **Limite**: 40 perguntas por formando e por dia (`ATC_VOZ_LIMITE`).
- O registo `voice_log` guarda cada pergunta, a fonte da resposta e o que foi pago, para acompanhar os custos.

## Instalação
- Definir `ATC_ELEVEN_KEY` com a chave da ElevenLabs no servidor (nunca no código nem no repositório).
- O navegador pede autorização para o microfone. É preciso HTTPS (ou localhost) para o microfone funcionar.

## Acrescentar outra aula
1. Criar `cursos/<curso>/voz/<aula>.json` (ver `aula-1-1.json`: frases fixas e perguntas com vários exemplos).
2. Gerar o áudio: `python3 producao/vozes/gerar_voz_aula.py <curso> <aula>`.
3. O painel aparece sozinho na página dessa aula.
