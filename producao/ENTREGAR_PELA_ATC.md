# O que a ATC precisa de fornecer

Lista exacta do material que não pode ser produzido neste ambiente (sem Windows/Office licenciados e sem acesso à web). Tudo o resto já está feito ou está a cargo do produtor.

Entrega: anexar os ficheiros na conversa ou guardá-los em `producao/entrega/` com **exactamente** os nomes abaixo.

## A. Capturas reais do Windows 11 (prioridade 1)

Substituem as 5 ilustrações do manual do Módulo 1 (as ilustrações dizem "não é uma captura real").

**Regras para todas:** Windows 11 licenciado, idioma **Português (Portugal)**, ecrã 1920 × 1080, escala 100 %, tema claro, fundo de ambiente de trabalho neutro, sem dados pessoais nem notificações. Formato PNG, sem compressão. Tecla `Win + Shift + S` ou Ferramenta de Recortes (ecrã inteiro). Anotar a versão do Windows (Definições › Sistema › Acerca de).

| Ficheiro | Substitui | O que mostrar |
|---|---|---|
| `win11-01-inicio-sessao.png` | `fig_login.jpg` | Ecrã de início de sessão, com o campo da palavra-passe visível |
| `win11-02-ambiente-trabalho.png` | `fig_desktop.jpg` | Ambiente de trabalho limpo, com barra de tarefas, botão Iniciar, ícones e relógio visíveis |
| `win11-03-iniciar-pesquisa-word.png` | `fig_start.jpg` | Menu Iniciar aberto, com «Word» escrito na pesquisa |
| `win11-04-janela-bloco-de-notas.png` | `fig_window.jpg` | Bloco de Notas aberto, com os botões minimizar, maximizar e fechar visíveis |
| `win11-05-encerrar.png` | `fig_shutdown.jpg` | Menu Iniciar › botão Ligar/Desligar aberto, com «Suspender», «Encerrar», «Reiniciar» |

## B. Gravações de ecrã para as aulas (prioridade 2, para substituir os vídeos de demonstração desenhados)

OBS Studio, 1920 × 1080, 30 fps, MP4. Sem áudio (a narração é acrescentada depois). Cursor visível, movimentos lentos. Seguir o guião de cada aula em `cursos/informatica/curso.json`.

| Ficheiro | Conteúdo |
|---|---|
| `aula-1-1-gravacao.mp4` | Ligar o computador, iniciar sessão, ambiente de trabalho, menu Iniciar, abrir o Bloco de Notas, janelas, encerrar |
| `aula-1-2-gravacao.mp4` | Explorador de Ficheiros, criar pasta, copiar, mover e mudar o nome de um ficheiro |

## C. Logótipos oficiais (prioridade 2)

Obter no portal de parceiros (ou no kit de marca oficial), com as regras de utilização. Preferir SVG; caso contrário, PNG com fundo transparente de pelo menos 1000 px de largura.

| Ficheiro | Origem |
|---|---|
| `logo-windows.svg`, `logo-word.svg`, `logo-excel.svg`, `logo-powerpoint.svg`, `logo-outlook.svg` | Microsoft, versão actual (os que estão no repositório são históricos 2019–2025) |
| `logo-comptia-a-plus.svg`, `logo-comptia-network-plus.svg` | CompTIA (kit de Authorized Partner) |
| `logo-atc.svg` | ATC, vectorial (hoje só existe PNG de 600 px) |
| `selo-acreditacao.svg` e o **número/entidade de acreditação** | Entidade que acredita a ATC em Angola; será usado no certificado e no rodapé |

Se a ATC for parceira autorizada Microsoft ou CompTIA, incluir também o selo de parceiro e as regras de utilização (tamanho mínimo, zona livre, texto obrigatório).

## D. Opcional, para o toque premium

- 5 a 10 fotografias reais da ATC (sala de formação, formadores, formandos a trabalhar) com autorização de imagem, 1920 px ou mais de largura. Servem para capas e para a página de entrada.
- Uma conta de formando "limpa" para gravar o LMS (sem progresso nem nome de teste).

## E. Não é preciso agora

Word, Excel, PowerPoint, Outlook e CompTIA ainda não têm módulos nem aulas escritos (cada `curso.json` tem `modules: []`). As capturas desses cursos só se pedem depois de existirem os guiões das aulas.

## Já feito ou a cargo do produtor (nada a fornecer)

Capas e cartões do catálogo com os ícones já no repositório, ajuste das imagens do manual quando as capturas chegarem, regravação dos clips com o LMS actualizado, vozes e sincronização labial.
