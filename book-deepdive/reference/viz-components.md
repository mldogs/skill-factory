# Visual components — book-deepdive

Each concept in `book.json` declares `visual.component` (+ optional `visual.params`). `build_page.py` renders it as a compact, crisp, theme-coloured inline-SVG/CSS figure (auto dark mode, honours `prefers-reduced-motion`). Diagram labels are kept short/neutral (English terms are language-neutral); the bilingual `title_ru`/`title_en` caption carries the meaning.

Pick the component whose *shape* matches the idea. Reuse freely — many concepts share an archetype with different `params`.

| component | params | depicts |
|---|---|---|
| `pipeline_vs_loop` | — | a straight box-pipeline (idealised/linear) vs a tangled loop (real/iterative). Rational model, rationalism-vs-empiricism. |
| `tree` | `variant`: `explode` \| `descend` \| `grow` \| `backtrack` \| `crack` \| `maze` | a decision tree: combinatorial blow-up / descend a path / grows as you go / dead-end then back up / a crack from a wrong root / search a space. |
| `spiral` | `variant`: `single` \| `double` | risk-reducing spiral (Boehm) / two interlocked spirals (co-evolution of problem & solution). |
| `cycle` | — | a circular design→build→fail→learn loop (e.g. Petroski; how experts go wrong). |
| `funnel` | — | a sieve/funnel: many inputs in, few survive (requirements churn; what a process keeps). |
| `tug` | — | tug-of-war rope between two pulls (contract vs iteration; fixed scope vs learning). |
| `budget` | — | **interactive** segmented bar of a scarce resource + a slider that reallocates and goes "over!" (budgeted resource). |
| `weights` | — | bars whose heights (criteria weights) drift; quality only legible at the end (unknowable goodness function). |
| `two_targets` | — | two dartboards: a foggy/vague one vs an explicit guess that can be hit (better wrong than vague). |
| `timeline` | `variant`: `change` \| `brookslaw` | a horizontal timeline: freeze vs expect-change / adding people slips the date (Brooks's Law). |
| `gauge` | — | a half-dial needle on a spectrum (e.g. parsimony ↔ bloat; elegance; motivation balance). |
| `principles` | — | one parent node branching to three derived principles (consistency → orthogonality/propriety/generality). |
| `grid_style` | — | a tidy grid vs a jittered one (consistent vs ad-hoc style; thousands of micro-decisions). |
| `arch` | — | a stone arch with a highlighted keystone + a style sheet (document the style). |
| `view_rays` | — | a small floor-plan with view rays fanning 360° (the controlling commodity; View/360). |
| `floor_plan` | — | walls with a load-bearing line and a new wing flowing around it (additions/remodels). |
| `line_chart` | `variant`: `up` \| `down` | a single curve: cost of a defect rising over time / integrity falling as minds are added. |
| `floor_ceiling` | — | a band with a rising floor and a higher rising ceiling (process lifts the floor; talent the ceiling). |
| `ladder` | — | a dual career ladder (management vs technical) bridged in the middle (dual ladder; growing designers). |
| `split` | `left`,`right` (labels), `left_good`,`right_good` (bool → ✓/✗), `cap` | generic two-pane comparison with check/cross marks (with-architect vs by-committee; corridor vs remote; book vs org; tech-push vs need-pull). |
| `radial_roles` | `center` (label), `roles` (list of labels), `cap` | a central node amplified by surrounding support roles (surgical team; single architect representing users; two-person pair). |
| `bridge` | — | a broken bridge over a chasm with a thin temporary plank (divorce of design; AI re-planks it). |
| `channel` | — | a bidirectional mind↔machine channel (thin intent out, rich feedback back). |
| `many_to_one` | — | several silos converging into one box (six incompatible lines → one family; System/360). |
| `verdict_cols` | — | three columns: worked / went wrong / why (honest post-hoc; recorded rationale). |
| `define` | — | a definition card stating a redefinition (e.g. "design = the whole process"). |
| `foggy_contract` | — | a document with blurred lines and a wax seal (a contract signed over fog; enshrined ignorance). |
| `image` | (use `visual.type:"image"`) | a generated illustration (`cache_filename`); used only if the file exists, else falls back to `component`. |

## Notes for authors / the analysis stage
- **Captions & labels are data-driven.** Most components carry book-specific default labels (the first deep-dive was Brooks' *Design of Design*). For ANY other book, pass `params` to override them so the figure reads correctly:
  - `cap` — the bottom caption line (every generalized component honours it): `spiral, cycle, tree, ladder, tug, principles, define, gauge, two_targets, funnel, many_to_one, split, radial_roles, line_chart, weights`.
  - extra label params: `tug`/`gauge`/`two_targets`/`ladder` → `left`,`right`; `principles` → `parent`,`kids` (≤3); `define` → `big`,`sub`; `cycle` → `nodes` (list; only then are node labels drawn); `many_to_one` → `target`; `split` → `left`,`right`,`left_good`,`right_good`; `radial_roles` → `center`,`roles`.
  - Keep all in-SVG labels SHORT and language-neutral (they render inside the figure); the bilingual `title_ru`/`title_en` caption carries the real meaning. Omitting `params` keeps the original Brooks defaults.
- Strongly prefer `css`/`svg` components; reserve `image` (paid generation) for 2–3 of the most metaphorical concepts plus the cover.
- For every `image` concept, also set a `component` fallback so the page still renders if the image is absent.
- `split` and `radial_roles` carry their labels in `params`; keep them short (they render inside the SVG). Other components need no params beyond an optional `variant`.
- Unknown or omitted `component` → the concept simply renders with no figure (the build never breaks).
- To add a brand-new component: implement `v_<name>(params)` in `scripts/build_page.py`, register it in the `GEN` dict, add the CSS classes it uses, and document it here.
