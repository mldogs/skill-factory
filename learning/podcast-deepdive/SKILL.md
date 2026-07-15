---
name: podcast-deepdive
description: Turns one YouTube podcast episode into a fact-checked, bilingual (RU/EN), interactive self-contained HTML deep-dive — fetches the transcript via yt-dlp, runs a multi-agent analysis (map → per-section analyze → adversarial verify → synthesize) into a single podcast.json source of truth with speakers, topic sections, concepts, attributed speaker quotes, sparse debate cards and deep-link timestamps, grounds every quote against the transcript, translates RU↔EN, and renders a page with inline-SVG/CSS visuals, a chapter timeline, a searchable glossary and active-recall Q&A. Use when the user wants a podcast deep-dive, to analyze/break down a YouTube episode, or to package an episode into an interactive lesson page.
---

# podcast-deepdive

Turns **one YouTube podcast episode** into a bilingual (RU/EN) interactive deep-dive at `podcasts/<slug>/<slug>.html` — a self-contained HTML page (inline CSS/JS, relative-path images) that opens with a double-click.

The core of the format is a **conversation between voices**: claims are attributed to speakers, (rare) genuine disagreements become debate cards, and sections/chapters carry **deep links** into YouTube at the right moment.

## Prerequisites

- **`yt-dlp`** — external CLI, the pipeline's only third-party dependency; needed only by the Fetch step (`fetch_transcript.py` shells out to it). All Python scripts import stdlib only.
- **`.env`** at the project root with `OPEN_ROUTER_API_KEY` (+ optional `IMG_MODEL`, `IMG_STYLE`) — needed only for image generation (`generate_image.py` reads `.env` itself; it is never sourced into the shell). Without the key, everything builds except illustration images.
- **`uv`** — to run `validate_podcast.py` (its Draft-07 `jsonschema` dependency is declared via PEP 723 metadata).

Output always goes to `podcasts/<slug>/` relative to the user's project root.

## Single source of truth

```
podcasts/<show>-<topic>/
  <slug>.txt                 input: transcript "MM:SS [>>] text" (yt-dlp; >> = speaker change)
  episode_seed.json          episode metadata (title, show, chapters, speakers, captions_kind)
        │  analyze_podcast.workflow.js → assemble_podcast.py → podcast.json.draft
        │  → validate_podcast.py publish (Draft-07 + atomic replace)
        ▼
  podcast.json               ← SOURCE OF TRUTH (schema: reference/podcast.schema.json)
        │            episode • speakers • chapters • sections[].concepts[] • debates[] • glossary • qa_seeds
        ├─ i18n/_global.json + i18n/<section>.json   (EN translations of RU fields)
        ├─ assets/*.png                              (cover/metaphors, cached; optional)
        └─ build_page.py ─▶ <slug>.html
```

## Pipeline (5 steps)

**1. Fetch** — `scripts/fetch_transcript.py <youtube-url> podcasts/<slug>/`
Shells out to `yt-dlp` (prerequisite). Prefers MANUAL captions; falls back to auto (`en-orig`). Parses VTT into a clean `MM:SS` transcript (strips the rolling-window and word-timing tags, keeps `>>`). Writes `<slug>.txt` + `episode_seed.json` (title, show, duration, up to 10 YouTube chapters, `captions_kind`, speaker hints from the description). If no captions exist it fails softly — drop in `<slug>.txt` by hand.

**2. Analyze** — workflow `scripts/analyze_podcast.workflow.js` (Workflow tool, `args:{dir,txt,seed}`)
- **Map**: speaker roster (host/guest + `bio_ru`), segmentation into 5–8 teachable sections, chapter carry-over.
- **Analyze** (fan-out per section): 2–4 concepts per section — `term_en`, `explanation_ru` (70–140 words), `analogy_ru`, `speaker_id`, a quote + `visual.component`; detect **genuine** disagreements only (collaborative episodes → empty `debates`, do NOT invent any).
- **Verify** (adversarial): quotes/attribution checked against the transcript; anything doubtful → null. ASR cleanup (`a genetic` → `agentic`), `quote_provenance="auto-cleaned"`.
- **Synthesize**: global `summary_ru`, deduplicated `glossary`, `qa_seeds`.

**3. Assemble + publish** — `scripts/assemble_podcast.py --dir podcasts/<slug> --result <wf_result.json>`
Builds a candidate from the workflow result + the seed. **Grounds quotes**: token coverage of every `quote_en` against the transcript (threshold 0.70, tolerant of ASR cleanup); below threshold → `quote_en=null`. Writes ONLY the sibling `podcast.json.draft` (atomically) + a quick structural smoke check. The final file is published by a separate command after a real Draft-07 validation against `reference/podcast.schema.json`:
```
uv run ${CLAUDE_SKILL_DIR}/scripts/validate_podcast.py publish \
  podcasts/<slug>/podcast.json.draft podcasts/<slug>/podcast.json --stage assembled
```
(`--stage assembled` temporarily relaxes `tldr_ru`/`key_points_ru` — the enrich step adds them; after enrich, run `validate … --stage final`. On failure the final file is untouched and the draft remains; on success the draft is deleted.)

**4. Translate** — a workflow translates RU fields → `i18n/_global.json` (`summary_en`, `speakers[].bio_en`, `glossary`, `qa`, `debates`) + `i18n/<section>.json` (`intro_en`, concept `explanation_en`/`analogy_en`/`visual_title_en`). Read `podcast.json` by **absolute** path and write exactly one file per agent. The renderer falls back to RU wherever a translation is missing.

**4b. Enrich** (`enrich_podcast.workflow.js`) — per concept: `tldr_ru` (the thesis in one phrase), `key_points_ru` (2–4 bullets) + EN; **hybrid visual choice** — metaphors → `visual.type="image"` + `image_prompt` (rendered by `generate_image.py`, ~40–50% of concepts), structural ideas → CSS/SVG diagram. No leftover text-only "Analogy:" snippets (the analogy becomes the image caption). Concept `id`s **must be unique** (guarded by `assemble_podcast.py`).

**4c. Prune + Russify** (`prune_russify.workflow.js` → `apply_prune_russify.py`) — cleanup pass: **(a) relevance** — aggressively drop what's irrelevant to the core (ads/sponsor/self-promo, intro/outro filler, digressions); **(b) dedup** — a barrier agent finds semantic duplicate concepts (even across sections) and keeps the single best one; **(c) russification** — translate non-core English into Russian, keep only established AI/engineering jargon, and wrap **EVERY** remaining English term in `[[term|translation]]` markup. `apply_prune_russify.py` applies the drops (cleans i18n + orphaned images + empty sections), replaces RU text, and validates.

**5. Build** — `scripts/build_page.py podcasts/<slug>`
Self-contained page: standalone header (podcast name as brandmark + RU/EN toggle), hero, speaker roster (CSS monograms), chapter timeline with deep links; sections → **structured concept cards** (image/diagram visual + caption, highlighted `tldr` thesis, lead paragraph, `key_points` bullets, speaker badge, quote with an `auto` provenance mark); a "Debates" block; a **glossary grid of icon cards** (icon colour groups by section, chip links back to the section) + search; Q&A on `<details>`. **English terms from the `[[term|translation]]` markup render as `<span class="term">` with the translation on hover/focus** (`ru_markup`/`Lc` in the renderer; the EN side is plain English with no markup). RU/EN toggle (`deepdive-lang` key in `localStorage`), auto dark theme, honours `prefers-reduced-motion`.

### Web-article adapter

The same editorial cycle can be reused for a long web article without faking YouTube:

- `<slug>.txt` holds a short source dossier and a link map rather than a full-text copy;
- `episode.youtube_id=""`, `episode.url` points at the original; timings and chapters stay empty;
- the original author's voice and the analytical/red-team voice are registered as separate `speakers`, so objections are never attributed to the authors;
- `sections[].source_docs` carry grounding links, and all `t_seconds` are `null`;
- `build_page.py` switches to article mode automatically: "Original" link, evidence links, editorial hero and an "Authors / Red team" filter, no YouTube deep links.

The schema stays `podcast-1.0`: this is a transport adapter around the same source of truth, not a new incompatible model.

## Key conventions

- **The platform is YouTube**; captions come via `yt-dlp` (scripts import stdlib only; yt-dlp is an external CLI).
- **Glossary and Q&A are self-contained on the episode page** (no cumulative cross-episode index).
- **Speakers are first-class**: `speakers[].id` (`host`/`guest`); concepts carry `speaker_id`; `debates[]` is a separate entity (thesis ↔ counter-thesis), usually sparse.
- **Deep links** — `t_seconds` on sections/chapters/debates → `youtube.com/watch?v=ID&t=Ns`; concepts inherit their section's timing.
- **Quote grounding is mandatory** — anything the transcript doesn't confirm gets nulled (`assemble_podcast.py`).
- **`id`s stay stable** across re-analyses.
- **The visual library is local**, implemented directly in `build_page.py` (`VIZ` components `define/layers/cycle/steps/tug/two_targets/funnel/timeline/many_to_one/split/gauge` + inline SVG); the agent picks `visual.component` from that set, or `type:"image"` for a metaphor.

## Scripts

All 4 workflows are GENERIC over any episode: analyze — `args:{dir,txt,seed}` (the roster comes from the seed/transcript, any number of speakers); enrich/translate/prune_russify — `args:{pj,ids,topic}` (`pj` — ABSOLUTE path to podcast.json, `ids` — list of section ids, `topic` — a short episode topic). `pj` is **required** — without it the workflow throws a clear error. Workflow results arrive WRAPPED — extract `.result` before feeding an apply script. The order is exactly this (enrich → translate → prune, with apply scripts between steps):

```
python3 .../scripts/fetch_transcript.py   <url> podcasts/<slug>/          # 1. transcript + seed (auto OR manual VTT)
# Workflow tool: analyze_podcast.workflow.js   (args: {dir,txt,seed})      # 2. analysis → {map,sections,synth}
python3 .../scripts/assemble_podcast.py   --dir podcasts/<slug> --result <wf.json>   # 3. assemble+ground → podcast.json.draft
uv run  .../scripts/validate_podcast.py   publish podcasts/<slug>/podcast.json.draft podcasts/<slug>/podcast.json --stage assembled   #    Draft-07 + atomic publish
# Workflow tool: enrich_podcast.workflow.js    (args: {pj,ids,topic})      # 4a. tldr+key_points+hybrid visuals
python3 .../scripts/apply_enrich.py       --dir podcasts/<slug> --result <wf.json>   #     write RU + stash EN in i18n_stash + list images to generate
python3 .claude/skills/podcast-deepdive/scripts/generate_image.py "<subject>" <path.png>   #     images for make_image=true
# Workflow tool: translate_podcast.workflow.js (args: {pj,ids,topic})      # 4b. EN → _global + per-section files
python3 .../scripts/apply_translate.py    --dir podcasts/<slug> --result <wf.json>   #     write i18n/ (+merge enrich EN)
# Workflow tool: prune_russify.workflow.js     (args: {pj,ids,topic})      # 4c. relevance+dedup+russification
python3 .../scripts/apply_prune_russify.py --dir podcasts/<slug> --result <wf.json>  #     drops+RU text+i18n cleanup (validates BEFORE writing)
uv run  .../scripts/validate_podcast.py   validate podcasts/<slug>/podcast.json --stage final   #     full contract before rendering
python3 .../scripts/build_page.py         [podcasts/<slug>]                 # 5. render the page
```

Schema: `reference/podcast.schema.json`. Visual components live in `build_page.py` (the `VIZ` set + inline SVG/CSS).
