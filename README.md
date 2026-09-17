# mis-notas-obsidian

Bóveda de Obsidian que implementa el patrón **LLM Wiki**: una base de
conocimiento personal que un agente LLM (Claude Code) mantiene de forma
incremental, en vez de re-derivar todo en cada pregunta como haría un RAG
clásico.

## Cómo está organizado

- **`Fuentes/`** — documentos originales sin tocar (artículos, PDFs,
  transcripciones, apuntes...). Es la fuente de verdad.
- **`Wiki/`** — páginas generadas y mantenidas por el LLM: resúmenes,
  páginas de entidades y conceptos, un índice (`Wiki/index.md`) y un log
  cronológico (`Wiki/log.md`).
- **`CLAUDE.md`** — el esquema: le dice al agente cómo está estructurada la
  wiki, qué convenciones seguir y cómo ejecutar las operaciones de ingesta,
  consulta y mantenimiento (lint).

## Flujo de trabajo

1. **Ingerir**: coloca una fuente nueva en `Fuentes/` y pide al agente que la
   procese. Va a leerla, resumirla en `Wiki/Resumenes/`, actualizar las
   páginas de `Wiki/Entidades/` y `Wiki/Conceptos/` afectadas, y dejar
   constancia en `Wiki/index.md` y `Wiki/log.md`.
2. **Consultar**: hazle preguntas al agente sobre lo que ya está en la wiki.
   Las respuestas que valga la pena conservar se pueden archivar como
   páginas nuevas en vez de perderse en el historial del chat.
3. **Lint**: de vez en cuando, pide un chequeo de salud de la wiki
   (contradicciones, páginas huérfanas, referencias que faltan, conceptos
   sin página propia).

Ábrela en Obsidian mientras trabajas con el agente en la terminal — así ves
en tiempo real los enlaces, el grafo y las páginas actualizarse.

Los detalles de convenciones y el "cómo" exacto de cada operación viven en
[`CLAUDE.md`](./CLAUDE.md) y evolucionan junto con el uso.
