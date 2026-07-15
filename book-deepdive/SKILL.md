---
name: book-deepdive
description: Turns a whole book (any design/engineering/non-fiction title) into a fact-checked, bilingual (RU/EN), interactive, self-contained HTML deep-dive — runs a multi-agent analysis workflow (structure → per-theme deep analysis → adversarial verification → synthesis), writes per-theme source notes + a single book.json source of truth, translates RU↔EN, generates a few key illustrations, and renders a standalone page with inline-SVG/CSS concept visuals, a searchable glossary and active-recall Q&A. Use when the user wants a book deep-dive, to analyze/break down a whole book, or to package a book into an interactive study page.
argument-hint: "<book title> [author] [year]"
allowed-tools: Read, Write, Edit, Bash(python3 *), Workflow, Agent
---

# book-deepdive

Produce a complete, self-contained book deep-dive under `books/<slug>/` (relative to the user's project root). One skill takes a book from analysis all the way to a standalone bilingual HTML page you open by double-click.

**Requirements:** `.env` with `OPEN_ROUTER_API_KEY` (+ optional `IMG_MODEL`, `IMG_STYLE`) is needed for the illustration step (paid OpenRouter calls); `uv` is needed to run `validate_book.py` (it pulls a Draft-07 dependency via PEP 723 metadata). Everything else is stdlib Python 3.

## Result layout

```
books/<slug>/
  book.json            ← SOURCE OF TRUTH: book meta · parts · sections[].concepts[] · glossary · qa_seeds
  sources/*.md         ← per-theme deep-dive notes (grounding source documents)
  i18n/*.json          ← EN translations (one per section + _global for summary/glossary/qa)
  assets/*.png         ← cover + a few key illustrations (cached; flat editorial vector)
  <slug>.html          ← generated interactive page (open by double-click)
```

`<slug>` = kebab-case of the title (e.g. `the-design-of-design`). The page filename **must** equal `<slug>.html` (the builder relies on it).

## Pipeline (4 stages)

### 1 — Analysis (multi-agent workflow → `book.json` + `sources/`)
Run the bundled workflow with the **Workflow** tool, passing the book identity as `args`:

```
Workflow({ scriptPath: "<this skill>/scripts/analyze_book.workflow.js",
           args: { title: "...", author: "...", year: 2010, slug: "..." } })
```

It does Map (authoritative parts/chapters + 6–9 teachable themes) → Analyze (deep per-theme: concepts, Brooks-style framing, modern AI-engineering bridge, verified quotes, a proposed visual) → **Verify** (skeptical fact-check per theme — attributions and especially verbatim quotes; corrections fold into synthesis) → Synthesize (one ordered RU dataset: `sections[].concepts[]` each with a `visual.component`, plus `glossary` and `qa_seeds`).

From its result (`result.map`, `result.theme_docs`, `result.synth`) **write the files yourself** (the workflow can't touch disk):
- `sources/<theme_id>.md` ← each `theme_docs[].markdown_ru` (prepend an H1 + a one-line source citation).
- `book.json` ← merge `map.book` + `map.parts` + `synth` (`summary_ru`, `sections`, `glossary`, `qa_seeds`). Add `book.cover_alt_ru`, and on each section a `source_docs: ["<theme_id>.md", …]` list. Keep all `id`s slug-style and stable. Validate against the real schema (not just syntax): `uv run ${CLAUDE_SKILL_DIR}/scripts/validate_book.py books/<slug>/book.json` — run it after every edit of `book.json` and before `build_page.py`.

See [reference/book.schema.json](reference/book.schema.json) for the exact shape and [reference/viz-components.md](reference/viz-components.md) for the visual component each concept may use.

### 2 — Translation (RU → EN → `i18n/`)
The page is bilingual (dual-span). Spawn parallel **Agent** subagents (one per section + one global), each `Read`s `book.json` and `Write`s its slice to `i18n/`:
- `i18n/<section_id>.json`: `{section_id, intro_en, concepts:[{id, explanation_en, analogy_en|null, visual_title_en}]}`
- `i18n/_global.json`: `{summary_en, glossary:[{term_en, definition_en}], qa:[{id, question_en, expected_answer_points_en:[…]}]}`

Rule for translators: faithful, complete, natural English; preserve proper nouns and the author's terminology verbatim. (The builder falls back to RU if a translation file is absent, so the page still works without this stage.)

### 3 — Illustrations (a few, paid; the rest are free CSS/SVG)
Ask the user how many images to generate (paid OpenRouter calls). Default: **cover + 3 key metaphors**. For each, set the concept's `visual.type:"image"`, `cache_filename:"assets/<name>.png"`, `image_prompt` (SUBJECT only — shared flat-editorial style is auto-applied), and **also** a `visual.component` fallback. Generate with the shared script:

```
python3 .claude/skills/book-deepdive/scripts/generate_image.py "<subject>" books/<slug>/assets/<name>.png
```

Always also generate `assets/cover.png` (used as the page hero). Every other concept renders a free, crisp inline-SVG/CSS `visual.component`.

### 4 — Build the page
```
python3 .claude/skills/book-deepdive/scripts/build_page.py books/<slug>
```
Renders the standalone `<slug>.html`: a header with the book title + RU/EN toggle, bilingual hero, parts strip, section TOC, concept cards (term · explanation with inline term-highlight · analogy · verified quote · visual), searchable glossary, `<details>` Q&A. No args → rebuilds every `books/*/`. The page is fully self-contained — open it by double-click, no server or hub needed.

## Quality gate (do this before declaring done)
- **Adversarial quote audit.** Quotes are the highest hallucination risk. Spawn skeptical **Agent**s (web-enabled) to classify every `quote_en` as verbatim / chapter-title / faithful-paraphrase / doubtful / fabricated; **null out** doubtful & fabricated quotes in `book.json`, rebuild. (This is how a quote misattributed to a critic rather than the author gets caught.)
- **Integrity check** (script): no broken `src`/`href`, balanced `lang ru`/`lang en` span counts, zero `viz error` comments, all `source_docs` resolve.
- **Visual check**: headless-Chrome screenshots. Page is taller than one screenshot — inject `body{margin-top:-Npx}` into a temp copy to capture lower regions (anchor scroll is ignored by headless screenshots).

## Conventions
- **Bilingual** dual-span (`<span class="lang ru">…</span><span class="lang en">…</span>`); RU default; English terms inline; key terms wrapped in `<span class="t">` (the builder auto-highlights glossary/concept terms).
- **Standalone header**: the page has its own top bar — the book title as the brandmark plus a RU/EN toggle on the right; no links to any other page. The toggle stores the choice in `localStorage` under the key `deepdive-lang`.
- **Visuals hybrid**: diagrammatic ideas → inline SVG/CSS components ([reference/viz-components.md](reference/viz-components.md)); strong metaphors → generated images (subject-only prompt; style centralised in `generate_image.py`). Prefer inline SVG over emoji.
- **Self-contained** HTML (CSS/JS inline, images by relative path); respects `prefers-reduced-motion`; auto dark theme; no provenance footers.
- **Scripts** — stdlib Python 3 only; read keys from `.env` themselves. Exception: `validate_book.py` runs via `uv` (Draft-07 dependency).

## Adding another book
1. Pick a `slug`. 2. Run stage 1 (workflow) → write `book.json` + `sources/`. 3. Stage 2 translation. 4. Stage 3 images. 5. `build_page.py books/<slug>`. Done.
