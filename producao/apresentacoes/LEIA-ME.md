# Apresentações dos manuais (PowerPoint)

Uma apresentação por manual do formando, feita a partir de `cursos/<curso>/manual/modulo-1.json`, com os avatares Helena e Miguel (`producao/visuais/manual-avatares/`).

| Ficheiro | Curso | Farda dos guias |
|---|---|---|
| `Informatica_Modulo1.pptx` | Informática na Ótica do Utilizador | camisa branca com emblema (igual aos vídeos) |
| `Word_Modulo1.pptx` | Microsoft Word | blazer |
| `Excel_Modulo1.pptx` | Microsoft Excel | polo |
| `PowerPoint_Modulo1.pptx` | Microsoft PowerPoint | casaco |
| `Outlook_Modulo1.pptx` | Microsoft Outlook | blazer |
| `CompTIA_A+_Modulo1.pptx` | CompTIA A+ · Dispositivos móveis | polo |
| `CompTIA_Network+_Modulo1.pptx` | CompTIA Network+ · Conceitos de redes | casaco |

Estrutura: capa, boas-vindas, objetivos de aprendizagem, percurso do módulo, um diapositivo por tema do manual (com quadros de referência adicionais nas tabelas largas), ideias-chave a reter, exercício prático em laboratório (com critério de sucesso), avaliação formativa («Teste os seus conhecimentos» com 4 questões em sala), glossário essencial (6 termos) e encerramento. O guia do formador e a chave de respostas completa estão nas **notas do orador** de cada diapositivo.

## Voltar a gerar (depois de alterar um manual)
```
python3 preparar_imagens.py                 # cenas dos avatares, retratos redondos e figuras SVG → _build/
node gerar_apresentacoes.js [curso ...]     # requer pptxgenjs e sharp (ou image-size + sips no macOS)
```
