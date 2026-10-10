# ATC — avatares, guiões e imagens reais

## Entregas

- `../static/presenters/helena.png`: retrato original da Helena, personagem africana fictícia, 1024 × 1536.
- `../static/presenters/miguel.png`: retrato original do Miguel, personagem africana fictícia, 1024 × 1536.
- `apresentadores/PROMPTS.json`: prompts completos, gerados com a ferramenta de imagem integrada.
- `guiões/GUIOES_ATC_PT-PT.md`: texto completo e direção de voz.
- `guiões/GUIOES_ATC_GEMINI_OMNI_FLASH.md`: versão de produção dividida em cenas de 7–9 segundos, nunca acima de 10 segundos; cada cena inclui a locução exacta e todos os planos que cabem nesse clipe.
- `guiões/GUIOES_ATC_GEMINI_OMNI_FLASH.json`: manifesto técnico para a produção.
- `vozes/PROMPTS_VOZES_ANGOLA_PT-PT.md`: prompts para criar as vozes femininas e masculinas de Helena e Miguel, incluindo texto de teste e critérios de aprovação.
- `vozes/GOOGLE_FLOW_MIGUEL_HELENA.md`: texto pronto para os campos **Character info** e **Customise performance** do Google Flow, para ambas as personagens.
- `guiões/*.txt`: 16 textos prontos para copiar — boas-vindas ao LMS e introduções dos sete cursos, em versão Helena e Miguel.
- `visuais/`: fotografia real, duas capturas oficiais do Explorador do Windows 11, dois ícones funcionais e quatro ícones originais históricos do Microsoft Office.
- `visuais/manual-avatares/`: 69 imagens de referência dos apresentadores para composição dos manuais, preservadas por sessão de exportação.
- `cursos/informatica/manual/figures/fig-1-2-sign-in-options-atc.png` e `fig-1-4-start-menu-atc.png`: variantes localizadas para o exemplo do formando, com Helena Manuel e ficheiros de treino ATC.
- `cursos/excel/manual/`: módulo online «Primeiros passos no Excel», questionário e quatro esquemas animados ATC. Duas capturas completas da página oficial de suporte da Microsoft ilustram introdução de dados e preenchimento automático; origem, data e orientação de reutilização estão registadas em `cursos/excel/manual/figures/fontes.json`. O ecrã de abertura não foi incluído. O curso mantém o estado «Em breve» até as vídeo-aulas estarem prontas.
- `cursos/powerpoint/`: amostra de curso com o módulo online «Primeiros passos no PowerPoint», questionário e dois esquemas animados ATC. O curso mantém o estado «Em breve» até as vídeo-aulas estarem prontas.
- Capas SVG originais para Word, Excel, PowerPoint, Outlook, CompTIA A+ e CompTIA Network+; a capa de Informática mantém a imagem atual. As capas ilustram temas de aprendizagem e não reutilizam logótipos Microsoft ou CompTIA.
- `visuais/fontes.json`: origem, autor, termos e limites de uso de cada imagem.

Os retratos são ficheiros de imagem, não vídeos. Os textos foram preparados para narração, mas ainda não foram sintetizados nem cronometrados com uma voz final.

## Gemini Omni Flash: regra de geração

Use `GUIOES_ATC_GEMINI_OMNI_FLASH.md` para gerar os clips. Cada cabeçalho é uma chamada separada. Copie a locução desse cabeçalho para o campo de fala, copie os planos para a direcção visual e use apenas o retrato do apresentador escolhido como referência. O alvo é 7–9 segundos; nunca ultrapassar 10 segundos. Não peça ao modelo para gerar uma sequência de vários cabeçalhos numa só chamada.

Depois de gerar, descarregue cada clip com um nome estável, reveja a duração real e monte os clips pela ordem dos códigos: `LMS-01`, `LMS-02`, `LMS-03`, `LMS-04`; ou `INF-01` a `INF-05`, conforme o curso. Gere as legendas fora do vídeo a partir da locução final. Se o Gemini alterar uma palavra, corrija a legenda e regenere o clip para manter a correspondência áudio-texto.

## Usar os vídeos depois de os produzir

Os exports recebidos do Google Flow estão preservados em `producao/videos/avatar-video/Helena/` e `producao/videos/avatar-video/Miguel/`. Os dois clips de boas-vindas escolhidos para a integração imediata são também copiados para:

```
cursos/informatica/apresentadores/helena-introducao.mp4
cursos/informatica/apresentadores/miguel-introducao.mp4
```

Os restantes exports permanecem no arquivo de produção até serem associados a uma aula específica e revistos com a locução final.

Criar os ficheiros seguintes para Informática (não é necessário reimportar o curso):

```
cursos/informatica/apresentadores/
  helena-introducao.mp4
  helena-introducao.vtt       # legendas opcionais
  miguel-introducao.mp4
  miguel-introducao.vtt
  helena/
    aula-1-1.mp4
    aula-1-1.vtt
    aula-1-2.mp4
    aula-1-2.vtt
  miguel/
    aula-1-1.mp4
    aula-1-1.vtt
    aula-1-2.mp4
    aula-1-2.vtt
```

Substituir `informatica` e o identificador da aula para outros cursos. O MP4 deve ser válido (H.264/AAC recomendado). O LMS lê a duração do ficheiro e seleciona a versão do apresentador escolhido. Use VTT com tempos correspondentes ao vídeo; uma versão sem VTT não usa as legendas antigas. O texto e as demonstrações devem cobrir os mesmos objetivos do curso, porque o questionário e o assistente de estudo são comuns às duas versões.

Sem o novo MP4, a aula apresenta explicitamente o vídeo original de demonstração. A introdução mostra o retrato e o guião. A escolha do avatar não altera por si só a voz de um vídeo já existente.

O ponto de reprodução e os segundos vistos são guardados separadamente por apresentador. A conclusão da aula é partilhada: mudar de apresentador não apaga uma aula concluída nem junta metade do vídeo da Helena com metade do vídeo do Miguel para dar aprovação. Os vídeos de boas-vindas ao LMS são entregáveis para produção; esta versão integra automaticamente apenas as introduções por curso e as aulas nas localizações acima.

## Imagens reais e limites de fidelidade

O manual online tem uma fotografia real de equipamento e novas secções que explicam capturas oficiais do Windows e ícones originais. As ilustrações anteriores que ainda existem estão identificadas como ilustrações. As capturas da Microsoft estão em inglês e têm resolução limitada; são referências autênticas, não gravações PT-PT da máquina do formando.

Para substituir as restantes demonstrações com qualidade de produção, capturar num Windows 11 licenciado, em PT-PT e a 1920 × 1080: ambiente de trabalho, pesquisa no Iniciar, Bloco de Notas, Explorador e encerramento. Usar ficheiros de exemplo e uma conta de formação. Documentar a versão do Windows. Não apresentar imagens geradas por IA como capturas reais.

Os MP4 de demonstração e o manual Word original não foram reconstruídos. O Word continua a ser a versão demo; o manual online contém os novos exemplos. `manual-original-demo.json` preserva a versão anterior do conteúdo JSON. Os ícones Office incluídos correspondem à família histórica 2018–2025; não são apresentados como os ícones mais recentes. Nenhum logótipo foi regenerado por IA. Os cartões do catálogo continuam com a identidade gráfica ATC; os ícones originais aparecem na explicação pedagógica do manual, não como decoração promocional.

## Termos das imagens

- Foto: Matheus Bertelli / Pexels, sob a [licença Pexels](https://www.pexels.com/license/). Não implica patrocínio dos produtos fotografados.
- Capturas e ícones do Windows: [documentação oficial do Explorador](https://support.microsoft.com/en-us/windows/experience/fileexplorer/file-explorer-in-windows), com [regras de conteúdo da Microsoft](https://www.microsoft.com/en-us/legal/intellectualproperty/copyright/permissions). Não são imagens de domínio público. Preservar o original, incluir a atribuição e usar como documentação do produto. Não recortar, redesenhar ou usar como interface do LMS.
- Word, Excel, PowerPoint e Outlook: originais históricos atribuídos à Microsoft, obtidos nas páginas Wikimedia indicadas em `fontes.json`. Essas páginas classificam os desenhos como PD-textlogo, com restrições de marca. A identificação de domínio público no Commons não é uma licença de marca ou uma aprovação da ATC pela Microsoft. Usar no contexto instrucional descrito.
- Não foram incluídos selos de certificação CompTIA: não representam uma certificação da ATC nem do formando.

## LMS e verificação

O perfil permite alterar nome de apresentação, profissão/interesse, objetivo e cor. O nome legal usado no certificado permanece inalterado. A preferência de apresentador é individual e específica de cada curso. A base de dados é atualizada automaticamente com tabelas adicionais, sem apagar utilizadores, matrículas ou resultados.

Testes automatizados: `python3 -m unittest discover -s tests -v`. Cobrem persistência, isolamento entre utilizadores, validação, acesso ao curso, escolha do avatar, fallback e progresso separado por vídeo. A reprodução e sincronização dos novos vídeos terão de ser verificadas quando os ficheiros finais existirem.
