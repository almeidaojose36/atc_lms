# Apresentações dos manuais (PowerPoint)

Uma apresentação por manual do formando, feita a partir de `cursos/<curso>/manual/modulo-1.json`, com os avatares Helena e Miguel (`producao/visuais/manual-avatares/`).

| Ficheiro | Curso | Farda dos guias |
|---|---|---|
| `Informatica_Modulo1.pptx` | Informática na Ótica do Utilizador | camisa branca com emblema (igual aos vídeos) |
| `Word_Modulo1.pptx` | Microsoft Word | blazer |
| `Excel_Modulo1.pptx` | Microsoft Excel | polo |
| `PowerPoint_Modulo1.pptx` | Microsoft PowerPoint | casaco |
| `Outlook_Modulo1.pptx` | Microsoft Outlook | blazer |

Estrutura: capa, boas-vindas, objetivos, o que vamos aprender, um diapositivo por tema do manual, resumo, exercício prático, questionário (quando o manual o tem), glossário e encerramento. O texto completo de cada tema está nas **notas do orador**, para o formador. As imagens do manual que mudam com o guia aparecem com o guia desse diapositivo.

## Voltar a gerar (depois de alterar um manual)
```
python3 preparar_imagens.py                 # cenas dos avatares, retratos redondos e figuras SVG → _build/
node gerar_apresentacoes.js [curso ...]     # requer pptxgenjs e sharp
```
