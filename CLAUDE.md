# mis-notas-obsidian — esquema de la wiki

Este repositorio es una bóveda de Obsidian que funciona como una **wiki personal
mantenida por un agente LLM** (patrón "LLM Wiki"). En lugar de un RAG que
redescubre todo en cada pregunta, el LLM lee las fuentes una vez y va
compilando/actualizando páginas interconectadas. Tú te encargas de traer
fuentes y hacer preguntas; el LLM se encarga de resumir, cruzar referencias y
mantener todo al día.

## Las tres capas

1. **`Fuentes/`** — documentos originales (artículos, PDFs, transcripciones,
   apuntes, capturas, etc.). **Inmutables**: el LLM las lee pero nunca las
   modifica. Es la fuente de verdad. Organiza libremente por tema o fecha si
   la carpeta empieza a crecer mucho.
2. **`Wiki/`** — todo lo que genera y mantiene el LLM. El usuario la lee; el
   LLM la escribe.
   - `Wiki/index.md` — catálogo de todas las páginas de la wiki.
   - `Wiki/log.md` — registro cronológico de lo que se ha hecho.
   - `Wiki/Entidades/` — páginas de personas, lugares, organizaciones, cosas
     concretas.
   - `Wiki/Conceptos/` — páginas de ideas, temas, teorías.
   - `Wiki/Resumenes/` — un resumen por fuente ingerida.
   - Añade nuevas subcarpetas (p. ej. `Wiki/Comparaciones/`,
     `Wiki/Sintesis/`) cuando el contenido lo pida; documenta aquí cualquier
     categoría nueva que se vuelva recurrente.
3. **Este archivo (`CLAUDE.md`)** — el esquema. Se actualiza junto con el
   usuario a medida que se descubren mejores convenciones para este dominio
   concreto.

## Convenciones

- **Idioma**: español, salvo que una fuente concreta amerite citarse en su
  idioma original (en ese caso, cita literal + traducción/resumen en
  español).
- **Enlaces**: usa wikilinks de Obsidian (`[[Nombre de la página]]`) para
  cualquier mención a una entidad, concepto o resumen que tenga (o debería
  tener) su propia página. Si un concepto se menciona 2+ veces en la wiki y
  no tiene página propia, créala.
- **Encabezado de cada página**: título en `# H1`, seguido de un frontmatter
  YAML mínimo cuando aporte valor (`tags`, `creado`, `actualizado`).
- **Citas a fuentes**: cuando una afirmación viene de una fuente concreta,
  enlázala como `[[Fuentes/nombre-archivo]]` o cita el resumen
  correspondiente en `Wiki/Resumenes/`.
- **Contradicciones**: si una fuente nueva contradice una página existente,
  no borres silenciosamente la afirmación vieja. Dejar una nota tipo
  `> [!warning] Contradice X (ver [[fuente]])` y decide junto con el usuario
  cuál prevalece.

## Formato de `Wiki/index.md`

Catálogo organizado por categoría (Entidades, Conceptos, Resúmenes, ...).
Cada entrada: enlace + una línea de resumen + metadata opcional. Se actualiza
en cada ingesta.

```markdown
## Entidades
- [[Wiki/Entidades/Nombre]] — una línea describiendo qué es y por qué importa.

## Conceptos
- [[Wiki/Conceptos/Nombre]] — una línea de resumen.

## Resúmenes de fuentes
- [[Wiki/Resumenes/Titulo]] — fuente original, fecha de ingesta.
```

## Formato de `Wiki/log.md`

Registro append-only. Cada entrada empieza con un prefijo consistente para
que sea fácil de grepear:

```markdown
## [YYYY-MM-DD] ingesta | Título de la fuente
## [YYYY-MM-DD] consulta | Pregunta resumida
## [YYYY-MM-DD] lint | Qué se revisó
```

`grep "^## \[" Wiki/log.md | tail -5` da las últimas 5 entradas.

## Operaciones

### Ingerir una fuente
1. El usuario coloca el archivo/enlace en `Fuentes/`.
2. Léela por completo (no solo un resumen superficial).
3. Comenta con el usuario los puntos clave antes de escribir nada (salvo que
   pida ingesta en lote sin supervisión).
4. Escribe un resumen en `Wiki/Resumenes/`.
5. Actualiza/crea las páginas de `Wiki/Entidades/` y `Wiki/Conceptos/`
   afectadas, cruzando referencias con wikilinks.
6. Actualiza `Wiki/index.md`.
7. Añade una entrada a `Wiki/log.md`.

### Responder una consulta
1. Lee `Wiki/index.md` primero para localizar páginas relevantes; entra a
   fondo solo en las que hagan falta.
2. Sintetiza la respuesta citando las páginas/fuentes usadas.
3. Si la respuesta es valiosa por sí misma (comparación, análisis, conexión
   nueva), ofrece archivarla como página nueva en `Wiki/` en vez de dejar que
   se pierda en el chat.
4. Añade una entrada a `Wiki/log.md` si se archivó algo.

### Lint / salud de la wiki
Cuando el usuario lo pida ("haz un lint de la wiki"), revisa:
- Contradicciones entre páginas.
- Afirmaciones desactualizadas que fuentes más recientes hayan superado.
- Páginas huérfanas (sin enlaces entrantes).
- Conceptos mencionados varias veces sin página propia.
- Referencias cruzadas que faltan.
- Huecos de información que se podrían llenar con una fuente nueva.

Reporta hallazgos y, si el usuario da luz verde, corrígelos. Añade una
entrada de tipo `lint` al log.

## Lo que el LLM NO debe hacer sin pedir permiso
- Modificar o borrar archivos en `Fuentes/`.
- Borrar contenido existente de la wiki (mover a "obsoleto"/anotar es mejor
  que eliminar, salvo que el usuario lo pida explícitamente).
- Reestructurar carpetas de forma masiva sin avisar primero.
