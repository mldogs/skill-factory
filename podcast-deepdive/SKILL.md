---
name: podcast-deepdive
description: Turns one YouTube podcast episode into a fact-checked, bilingual (RU/EN), interactive self-contained HTML deep-dive — fetches the transcript via yt-dlp, runs a multi-agent analysis (map → per-section analyze → adversarial verify → synthesize) into a single podcast.json source of truth with speakers, topic sections, concepts, attributed speaker quotes, sparse debate cards and deep-link timestamps, grounds every quote against the transcript, translates RU↔EN, and renders a page with inline-SVG/CSS visuals, a chapter timeline, a searchable glossary and active-recall Q&A. Use when the user wants to разобрать / сделать разбор подкаста, "podcast deep-dive", or упаковать/собрать разбор YouTube-эпизода.
---

# podcast-deepdive

Превращает **один YouTube-эпизод подкаста** в двуязычный (RU/EN) интерактивный разбор `podcasts/<slug>/<slug>.html` — самодостаточную HTML-страницу (CSS/JS inline, картинки по относительному пути), которую можно открыть двойным кликом.

Суть разбора — это **разговор нескольких голосов**: тезисы атрибутируются спикерам, фиксируются (редкие) точки спора, у секций/глав есть **deep-link** в YouTube на нужный момент.

## Пред-реквизиты

- **`yt-dlp`** — внешний CLI, единственная сторонняя зависимость пайплайна; нужен только шагу Fetch (`fetch_transcript.py` шеллит его). Импорты всех Python-скриптов — только stdlib.
- **`.env`** в корне проекта с `OPEN_ROUTER_API_KEY` (+ опц. `IMG_MODEL`, `IMG_STYLE`) — нужен только для генерации картинок (`generate_image.py` читает `.env` сам, в шелл он не подгружается). Без картинок разбор собирается и без ключа.
- **`uv`** — для запуска `validate_podcast.py` (у него Draft-07 зависимость `jsonschema` в PEP 723 metadata).

Выход всегда пишется в `podcasts/<slug>/` относительно корня проекта пользователя.

## Единый источник истины

```
podcasts/<show>-<тема>/
  <slug>.txt                 вход: транскрипт "MM:SS [>>] текст" (yt-dlp; >> = смена говорящего)
  episode_seed.json          метаданные эпизода (title, show, главы, спикеры, captions_kind)
        │  analyze-podcast.workflow.js → assemble_podcast.py → podcast.json.draft
        │  → validate_podcast.py publish (Draft-07 + atomic replace)
        ▼
  podcast.json               ← ИСТОЧНИК ИСТИНЫ (схема reference/podcast.schema.json)
        │            episode • speakers • chapters • sections[].concepts[] • debates[] • glossary • qa_seeds
        ├─ i18n/_global.json + i18n/<section>.json   (EN-перевод полей)
        ├─ assets/*.png                              (обложка/метафоры, кешируются; опц.)
        └─ build_page.py ─▶ <slug>.html
```

## Пайплайн (5 шагов)

**1. Fetch** — `scripts/fetch_transcript.py <youtube-url> podcasts/<slug>/`
Шеллит внешний `yt-dlp` (пред-реквизит). Предпочитает РУЧНЫЕ субтитры; иначе авто (`en-orig`). Парсит VTT в чистый `MM:SS`-транскрипт (снимает «бегущее окно» и word-timing теги, сохраняет `>>`). Пишет `<slug>.txt` + `episode_seed.json` (title, show, duration, 10 YouTube-глав, `captions_kind`, подсказки по спикерам из description). Если субтитров нет — падает мягко, вставь `<slug>.txt` вручную.

**2. Analyze** — workflow `scripts/analyze_podcast.workflow.js` (Workflow tool, `args:{dir,txt,seed}`)
- **Map**: ростер (host/guest + bio_ru), сегментация на 5-8 учебных секций, перенос глав.
- **Analyze** (веером по секциям): 2-4 концепта/секция — `term_en`, `explanation_ru` (70-140 слов), `analogy_ru`, `speaker_id`, цитата + `visual.component`; детект **реальных** споров (коллаборативные эпизоды → `debates` пустой, НЕ выдумывать).
- **Verify** (адверсариально): проверка цитат/атрибуции против транскрипта; сомнительное → null. ASR-чистка (`a genetic`→`agentic`), `quote_provenance="auto-cleaned"`.
- **Synthesize**: глобальные `summary_ru`, `glossary` (дедуп), `qa_seeds`.

**3. Assemble + publish** — `scripts/assemble_podcast.py --dir podcasts/<slug> --result <wf_result.json>`
Собирает кандидата из результата workflow + сида. **Заземляет цитаты**: token-coverage каждой `quote_en` против транскрипта (порог 0.70, терпимо к ASR-чистке); ниже порога → `quote_en=null`. Пишет ТОЛЬКО sibling `podcast.json.draft` (атомарно) + быстрый структурный smoke-check. Final публикует отдельная команда после настоящей Draft-07-валидации против `reference/podcast.schema.json`:
```
uv run ${CLAUDE_SKILL_DIR}/scripts/validate_podcast.py publish \
  podcasts/<slug>/podcast.json.draft podcasts/<slug>/podcast.json --stage assembled
```
(`--stage assembled` временно ослабляет `tldr_ru`/`key_points_ru` — их добавит enrich; после enrich гоняй `validate … --stage final`. При ошибке final не меняется, draft остаётся; после успеха draft удаляется.)

**4. Translate** — workflow переводит RU-поля → `i18n/_global.json` (`summary_en`, `speakers[].bio_en`, `glossary`, `qa`, `debates`) + `i18n/<section>.json` (`intro_en`, concepts `explanation_en`/`analogy_en`/`visual_title_en`). Читай `podcast.json` по **абсолютному** пути и строго один файл. Рендер падает обратно на RU, если перевода нет.

**4b. Enrich** (`enrich_podcast.workflow.js`) — по концептам: `tldr_ru` (тезис одной фразой), `key_points_ru` (2-4 буллета) + EN; **гибрид-выбор визуала** — метафоры → `visual.type="image"` + `image_prompt` (генерит `generate_image.py`, ~40-50% концептов), структурные идеи → CSS/SVG-диаграмма. Текстовых «Аналогия:»-снипетов не остаётся (аналогия → подпись к картинке). `id` концептов **обязаны быть уникальны** (guard в `assemble_podcast.py`).

**4c. Prune + Russify** (`prune_russify.workflow.js` → `apply_prune_russify.py`) — чистка «на старте»: **(а) релевантность** — агрессивно дропаем нерелевантное ядру (реклама/спонсор/самопромо, интро/аутро-вода, отступления); **(б) дедуп** — барьер-агент находит семантические дубли концептов (даже в разных секциях), оставляет один лучший; **(в) руссификация** — переводим неядровый английский на русский, оставляем только устоявшийся AI/eng-жаргон, и **КАЖДЫЙ** оставшийся английский термин оборачиваем разметкой `[[term|перевод]]`. `apply_prune_russify.py` применяет дропы (чистит i18n + осиротевшие картинки + пустые секции), заменяет RU-текст и валидирует.

**5. Build** — `scripts/build_page.py podcasts/<slug>`
Самодостаточная страница: standalone-шапка (название подкаста как brandmark + переключатель RU/EN), hero, ростер спикеров (CSS-монограммы), тайм-лайн глав с deep-link; секции → **структурированные карточки концептов** (визуал картинка/диаграмма + подпись, выделенный `tldr`-тезис, лид-абзац, буллеты `key_points`, бейдж спикера, цитата с пометкой `auto`); блок «Споры»; **глоссарий-сетка карточек с иконками** (цвет иконки группирует по секции, чип-ссылка на секцию) + поиск; Q&A на `<details>`. **Английские термины из разметки `[[term|перевод]]` рендерятся как `<span class="term">` с переводом по наведению/фокусу** (`ru_markup`/`Lc` в рендерере; EN-сторона — чистый английский без разметки). RU/EN-тоггл (ключ `deepdive-lang` в `localStorage`), тёмная тема, `prefers-reduced-motion`.

### Адаптер для веб-статей

Редакционный цикл можно переиспользовать для длинной веб-статьи без имитации YouTube:

- `<slug>.txt` хранит краткий source dossier и карту ссылок, а не копию полного текста;
- `episode.youtube_id=""`, `episode.url` ведёт на оригинал, время и главы остаются пустыми;
- исходный авторский голос и аналитический/red-team голос заводятся как разные `speakers`, чтобы не приписывать авторам возражения;
- `sections[].source_docs` содержат заземляющие ссылки, а все `t_seconds` равны `null`;
- `build_page.py` автоматически включает article-mode: «Оригинал», evidence links, editorial hero и фильтр «Авторы / Red team», без YouTube deep-links.

Схема остаётся `podcast-1.0`: это transport adapter вокруг того же источника истины, а не новая несовместимая модель.

## Ключевые конвенции

- **Платформа — YouTube**; выкачка через `yt-dlp` (импорты скриптов — только stdlib; yt-dlp — внешний CLI).
- **Глоссарий и Q&A самодостаточны на странице** эпизода (никакого накопительного индекса across-эпизодов).
- **Спикеры first-class**: `speakers[].id` (`host`/`guest`); концепты несут `speaker_id`; `debates[]` — отдельная сущность (тезис↔контртезис), обычно разрежена.
- **Deep-link** — `t_seconds` у секций/глав/споров → `youtube.com/watch?v=ID&t=Ns`; концепты наследуют тайминг секции.
- **Заземление цитат обязательно** — что не подтверждено транскриптом, обнуляется (`assemble_podcast.py`).
- **`id` стабильны** между переразборами.
- **Библиотека визуалов — своя**, реализована прямо в `build_page.py` (`VIZ`-компоненты `define/layers/cycle/steps/tug/two_targets/funnel/timeline/many_to_one/split/gauge` + inline-SVG); агент выбирает `visual.component` из этого набора либо `type:"image"` для метафоры.

## Скрипты

Все 4 workflow ОБОБЩЕНЫ под любой эпизод: analyze — `args:{dir,txt,seed}` (ростер берётся из сида/транскрипта, любое число спикеров); enrich/translate/prune_russify — `args:{pj,ids,topic}` (`pj` — АБСОЛЮТНЫЙ путь к podcast.json, `ids` — список id секций, `topic` — короткая тема эпизода). `pj` **обязателен** — без него workflow бросает понятную ошибку. Результат workflow приходит ОБёрнутым — извлекай `.result` перед подачей в apply-скрипт. Порядок именно такой (enrich → translate → prune, apply-скрипты между шагами):

```
python3 .../scripts/fetch_transcript.py   <url> podcasts/<slug>/          # 1. транскрипт + сид (auto ИЛИ manual VTT)
# Workflow tool: analyze_podcast.workflow.js   (args: {dir,txt,seed})      # 2. анализ → {map,sections,synth}
python3 .../scripts/assemble_podcast.py   --dir podcasts/<slug> --result <wf.json>   # 3. сборка+заземление → podcast.json.draft
uv run  .../scripts/validate_podcast.py   publish podcasts/<slug>/podcast.json.draft podcasts/<slug>/podcast.json --stage assembled   #    Draft-07 + атомарная публикация
# Workflow tool: enrich_podcast.workflow.js    (args: {pj,ids,topic})      # 4a. tldr+key_points+гибрид-картинки
python3 .../scripts/apply_enrich.py       --dir podcasts/<slug> --result <wf.json>   #     впис. RU + отложить EN в i18n_stash + список картинок
python3 .claude/skills/podcast-deepdive/scripts/generate_image.py "<сюжет>" <путь.png>   #     картинки для make_image=true
# Workflow tool: translate_podcast.workflow.js (args: {pj,ids,topic})      # 4b. EN → _global + секции
python3 .../scripts/apply_translate.py    --dir podcasts/<slug> --result <wf.json>   #     записать i18n/ (+мердж enrich EN)
# Workflow tool: prune_russify.workflow.js     (args: {pj,ids,topic})      # 4c. релевантность+дедуп+руссификация
python3 .../scripts/apply_prune_russify.py --dir podcasts/<slug> --result <wf.json>  #     дропы+RU-текст+чистка i18n (валидирует ДО записи)
uv run  .../scripts/validate_podcast.py   validate podcasts/<slug>/podcast.json --stage final   #     полный контракт перед рендером
python3 .../scripts/build_page.py         [podcasts/<slug>]                 # 5. рендер страницы
```

Схема: `reference/podcast.schema.json`. Визуальные компоненты — в `build_page.py` (набор `VIZ` + inline-SVG/CSS).
