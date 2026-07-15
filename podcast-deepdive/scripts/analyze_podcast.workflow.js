export const meta = {
  name: 'analyze-podcast',
  description: 'Analyze a fetched YouTube podcast transcript into a grounded bilingual podcast.json dataset (speakers, sections, concepts, debates, glossary, Q&A)',
  phases: [
    { title: 'Map', detail: 'Roster + section segmentation aligned to chapters' },
    { title: 'Analyze', detail: 'Per-section: concepts, attributed quotes, debates, visual component' },
    { title: 'Verify', detail: 'Adversarial: quote presence + attribution defensibility; null unconfirmed' },
    { title: 'Synthesize', detail: 'Global summary, deduped glossary, Q&A' },
  ],
}

let A = args || {}
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
const DIR = A.dir
const TXT = A.txt
const SEED = A.seed

// Компоненты визуалов, реализованные в build_page.py (агент выбирает из них; иначе type:image для метафоры)
const COMPONENTS = [
  'define (карточка-определение)', 'layers (вертикальный стек слоёв)', 'cycle (замкнутый цикл/петля)',
  'steps (нумерованные шаги/фазы)', 'tug (противопоставление двух сил)', 'two_targets (старое vs новое)',
  'funnel (воронка/сужение)', 'timeline (горизонтальная шкала времени)', 'many_to_one (много→один, оркестратор)',
  'split (две колонки)', 'gauge (шкала/индикатор)',
  'debate (ПОДКАСТ: тезис↔контртезис со спикерами)', 'speaker_roster (ПОДКАСТ: участники)',
  'chapter_timeline (ПОДКАСТ: тайм-лайн глав)'
]
const COMP_LIST = COMPONENTS.join('; ')

const RU = 'Объяснения — ПО-РУССКИ; английские технические термины (agentic, workflow, orchestration, recursive self-improvement…) сохраняй инлайн как есть. Не переводи устоявшиеся термины.'
const ASR = 'Это АВТО-субтитры YouTube с ASR-ошибками: «a genetic AI»/«gen ticket» = agentic AI; «open clock» ≈ a laptop; имена/слова могут быть искажены. При цитировании можно мягко чинить очевидные ASR-ошибки и пунктуацию БЕЗ изменения смысла; ставь quote_provenance="auto-cleaned".'
const SPK = 'Спикеры перечислены в сиде (host_hint + guest_hints) и в description. В транскрипте «>>» в начале строки = смена говорящего. Присвой каждому участнику стабильный kebab-case id по имени (напр. "peter", "dave", "salim", "alex", "philip"). Атрибутируй реплики по контексту и границам «>>»: ведущий (host) чаще задаёт вопросы/резюмирует, гости излагают свои тезисы. Если по контексту говорящий неясен — ставь speaker_id=null.'

// ---------- Phase 1: Map ----------
phase('Map')
const MAP_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['speakers', 'sections', 'chapters', 'episode_title_ru'],
  properties: {
    episode_title_ru: { type: 'string' },
    speakers: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['id', 'name', 'role', 'bio_ru'],
      properties: { id: {type:'string'}, name: {type:'string'}, role: {enum:['host','guest']}, bio_ru: {type:'string'} } } },
    chapters: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['t_seconds','title_en','title_ru'],
      properties: { t_seconds:{type:'integer'}, title_en:{type:'string'}, title_ru:{type:'string'} } } },
    sections: { type: 'array', minItems: 5, maxItems: 8, items: { type: 'object', additionalProperties: false,
      required: ['id','title_en','title_ru','t_seconds','t_end_seconds','one_line_ru'],
      properties: {
        id: {type:'string', pattern:'^[a-z0-9-]+$'}, title_en:{type:'string'}, title_ru:{type:'string'},
        t_seconds:{type:'integer'}, t_end_seconds:{type:'integer'}, one_line_ru:{type:'string'} } } }
  }
}
const map = await agent(
`Ты структурируешь разбор одного эпизода подкаста для двуязычного учебного сайта.

Прочитай файл-сид: ${SEED} (там title, show, duration, 10 YouTube-глав с тайм-кодами, подсказки по спикерам, description).
Прочитай транскрипт: ${TXT} (строки вида "MM:SS [>>] текст"; MM:SS — минуты:секунды от начала; общая длительность — в сиде (duration)).

${SPK}
${RU}

Задача:
1) speakers[] — ВСЕ участники из сида (host + гости, включая упомянутых в description): каждому стабильный kebab-case id по имени, role ("host" для ведущего, "guest" для остальных), name, bio_ru 1-2 предложения из description. Если участников много — оставь тех, кто реально говорит по существу.
2) chapters[] — перенеси 10 YouTube-глав, добавь title_ru (перевод). t_seconds бери из сида.
3) sections[] — слей 10 глав в 5-8 УЧЕБНЫХ тематических секций (близкие главы можно объединить). Для каждой: стабильный kebab-case id, title_en, title_ru, t_seconds (начало в секундах), t_end_seconds (конец = начало следующей секции или длительность), one_line_ru (одна фраза о чём секция). Секции покрывают эпизод по порядку без дыр.

Верни строго по схеме.`,
  { label: 'map', schema: MAP_SCHEMA, agentType: 'general-purpose' })

// Ростер спикеров из map — прокидываем в analyze/verify, чтобы атрибуция шла по реальным id
const ROSTER = (map.speakers || []).map(s => `${s.id} = ${s.name} (${s.role})`).join('; ') || 'peter = host'

// ---------- Phase 2+3: Analyze -> Verify (pipeline per section) ----------
const SECTION_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['section_id', 'intro_ru', 'concepts', 'debates'],
  properties: {
    section_id: { type: 'string' },
    intro_ru: { type: 'string' },
    concepts: { type: 'array', minItems: 1, maxItems: 4, items: { type: 'object', additionalProperties: false,
      required: ['id','term_en','explanation_ru','speaker_id','quote_en','quote_provenance','visual'],
      properties: {
        id: {type:'string', pattern:'^[a-z0-9-]+$'},
        term_en: {type:'string'},
        explanation_ru: {type:'string'},
        analogy_ru: {type:['string','null']},
        speaker_id: {type:['string','null']},
        quote_en: {type:['string','null']},
        quote_provenance: {enum:['manual','auto-cleaned',null]},
        visual: { type:'object', additionalProperties:false, required:['type','component','title_ru'],
          properties: {
            type: {enum:['css','svg','image']},
            component: {type:['string','null']},
            params: {type:['object','null']},
            title_ru: {type:'string'},
            alt_ru: {type:['string','null']},
            image_prompt: {type:['string','null']},
            cache_filename: {type:['string','null']} } } } } },
    debates: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['id','topic_ru','positions'],
      properties: {
        id: {type:'string', pattern:'^[a-z0-9-]+$'},
        topic_ru: {type:'string'},
        t_seconds: {type:['integer','null']},
        positions: { type:'array', minItems:2, items: { type:'object', additionalProperties:false,
          required:['speaker_id','claim_ru'],
          properties:{ speaker_id:{type:'string'}, claim_ru:{type:'string'}, quote_en:{type:['string','null']} } } },
        resolution_ru: {type:['string','null']} } } }
  }
}

const sections = await pipeline(map.sections,
  // STAGE 1: Analyze
  (sec) => agent(
`Ты — аналитик учебного контента. Эпизод: «${map.episode_title_ru}».
Прочитай транскрипт: ${TXT}. Работаешь над ОДНОЙ секцией:

СЕКЦИЯ: ${sec.title_en} / ${sec.title_ru}
Окно: ${sec.t_seconds}s … ${sec.t_end_seconds}s (т.е. примерно ${Math.floor(sec.t_seconds/60)}:${String(sec.t_seconds%60).padStart(2,'0')}–${Math.floor(sec.t_end_seconds/60)}:${String(sec.t_end_seconds%60).padStart(2,'0')}). О чём: ${sec.one_line_ru}

${SPK}
Ростер (используй эти id для speaker_id): ${ROSTER}
${RU}
${ASR}

Извлеки 2-4 ключевых УЧЕБНЫХ концепта из этого окна:
- id (kebab-case, стабильный), term_en (англ. термин/идея, напр. "agentic workflow", "fiduciary wedge", "ExO 3.0").
- explanation_ru: 70-140 слов, по-русски, с инлайн-терминами. Объясняй СУТЬ, не пересказ.
- analogy_ru: бытовая аналогия, если уместна (иначе null).
- speaker_id: кто это ввёл — id из ростера выше, либо null если неясно.
- quote_en: КОРОТКАЯ (<=25 слов) подтверждающая фраза из транскрипта этого окна, можно мягко почистить ASR (provenance="auto-cleaned"). Если нет хорошей — null.
- visual: выбери component из списка [${COMP_LIST}] и type "css"/"svg"; либо для МЕТАФОРЫ type:"image" + image_prompt (ТОЛЬКО сюжет, без стиля) + cache_filename "assets/<slug>.png". title_ru обязателен. params — по желанию (напр. {labels:[...]}).

intro_ru: 2-3 предложения, вводка к секции по-русски.

debates: ТОЛЬКО если в этом окне есть РЕАЛЬНОЕ несогласие/вызов между участниками панели (один возражает/уточняет/сомневается). speaker_id в positions — из ростера. Это коллаборативное интервью — чаще debates ПУСТОЙ ([]). НЕ ВЫДУМЫВАЙ спор.

Верни строго по схеме (section_id="${sec.id}").`,
    { label: `analyze:${sec.id}`, phase: 'Analyze', schema: SECTION_SCHEMA, agentType: 'general-purpose' }),
  // STAGE 2: Verify (adversarial)
  (res, sec) => agent(
`Ты — придирчивый фактчекер. Транскрипт: ${TXT}. Секция "${sec.id}".
Ростер (допустимые speaker_id): ${ROSTER}.
Вот черновой разбор секции (JSON):
${JSON.stringify(res)}

Проверь КАЖДЫЙ пункт против реального транскрипта и верни ИСПРАВЛЕННЫЙ объект той же схемы:
1) quote_en: найди фразу в транскрипте (с поправкой на ASR/пунктуацию/регистр). Если её там НЕТ по смыслу и словам — поставь quote_en=null, quote_provenance=null. Если есть, но криво — приведи к минимально-почищенному виду реально сказанного, provenance="auto-cleaned".
2) speaker_id: атрибуция обоснована «>>»-границами и содержанием? id должен быть из ростера. Если сомнительно — поставь null.
3) explanation_ru: убери галлюцинации/факты, которых нет в эпизоде. Термины — корректны (agentic, не "a genetic").
4) debates: оставь только подтверждённые транскриптом реальные расхождения; выдуманное — выкинь.
5) visual.component — должен быть из [${COMP_LIST}] либо type:"image". Иначе замени на ближайший или "define".

Верни строго по схеме (исправленный объект, section_id="${sec.id}").`,
    { label: `verify:${sec.id}`, phase: 'Verify', schema: SECTION_SCHEMA, agentType: 'general-purpose' })
)

// ---------- Phase 4: Synthesize ----------
phase('Synthesize')
const verified = sections.filter(Boolean)
const SYNTH_SCHEMA = {
  type:'object', additionalProperties:false,
  required:['summary_ru','cover_alt_ru','glossary','qa_seeds'],
  properties:{
    summary_ru: {type:'string'},
    cover_alt_ru: {type:'string'},
    glossary: { type:'array', minItems:6, items:{ type:'object', additionalProperties:false,
      required:['term_en','definition_ru','section_id'],
      properties:{ term_en:{type:'string'}, definition_ru:{type:'string'}, section_id:{type:['string','null']} } } },
    qa_seeds: { type:'array', minItems:6, maxItems:10, items:{ type:'object', additionalProperties:false,
      required:['id','question_ru','expected_answer_points','difficulty','section_id'],
      properties:{ id:{type:'string', pattern:'^[a-z0-9-]+$'}, question_ru:{type:'string'},
        expected_answer_points:{type:'array', minItems:2, items:{type:'string'}},
        difficulty:{enum:['easy','medium','hard']}, section_id:{type:['string','null']} } } }
  }
}
const conceptsFlat = verified.flatMap(s => (s.concepts||[]).map(c => ({section_id:s.section_id, term_en:c.term_en, explanation_ru:c.explanation_ru})))
const synth = await agent(
`Эпизод: «${map.episode_title_ru}». Секции и их концепты (JSON):
${JSON.stringify(conceptsFlat)}

${RU}
Собери ГЛОБАЛЬНЫЕ части разбора:
1) summary_ru: 3-5 предложений — о чём эпизод и зачем его учить.
2) cover_alt_ru: краткое описание обложки (alt).
3) glossary: 8-14 ключевых терминов (term_en + definition_ru 1-2 предложения + section_id где впервые). Дедуп — каждый термин один раз.
4) qa_seeds: 6-10 вопросов активного припоминания. Каждый: стабильный id, question_ru, expected_answer_points (2-4 пункта рубрики по-русски), difficulty, section_id. Покрой разные секции и сложности.

Верни строго по схеме.`,
  { label: 'synthesize', schema: SYNTH_SCHEMA, agentType: 'general-purpose' })

return { map, sections: verified, synth }
