export const meta = {
  name: 'prune-russify-podcast',
  description: 'Aggressively prune irrelevant/duplicate concepts and russify RU text (keep core jargon, mark every remaining English term with [[term|gloss]] for hover-translation)',
  phases: [
    { title: 'Review', detail: 'Per section: keep/drop relevance + russify RU with markup' },
    { title: 'Dedup', detail: 'Barrier: drop semantic-duplicate concepts' },
    { title: 'Glossary', detail: 'Russify glossary defs + flag irrelevant terms' },
  ],
}

let A = args || {}
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
if (!A.pj) throw new Error('args.pj is required: absolute path to the target podcast.json (pass {"pj": "/abs/podcasts/<slug>/podcast.json", "ids": [...], "topic": "..."})')
const PJ = A.pj
if (!PJ) throw new Error("args.pj is required: absolute path to podcast.json")
if (!Array.isArray(A.ids) || !A.ids.length) throw new Error("args.ids is required: list of section ids to process")
const IDS = A.ids
const TOPIC = A.topic || "the episode's core topic"

const RULES = `ПРАВИЛА РУССИФИКАЦИИ (умеренно):
- Оставляй В АНГЛИЙСКОМ только устоявшийся AI/eng-жаргон: agentic, workflow, API, RAG, LLM, evals, harness, pipeline и подобные.
- Переводи на русский всё остальное: execution->исполнение, coordination->координация, transaction costs->транзакционные издержки, hierarchy->иерархия, headcount->штат, oversight->надзор, и т.п.
- Разметку [[term|короткий русский перевод (<=6 слов)]] ставь ТОЛЬКО на ПЕРВОЕ вхождение термина внутри концепта (первое по порядку: tldr_ru -> explanation_ru -> key_points_ru); все последующие вхождения оставляй голым термином без разметки. Пример: "…[[harness|каркас-обвязка агента]] делает X. Дальше harness делает Y."
- НЕ размечай общеизвестные аббревиатуры и слова, перевод которых очевиден любому читателю: AI, IT, CEO, CTO, HR, PR, URL, PDF. Не оборачивай имена людей/продуктов (Vercel, Dropbox, Claude Code).
- Глосса — короткая справка в именительном падеже; сам термин в тексте должен читаться грамматично в своём предложении.
- Если исходная речь эпизода уже русская, руссификация почти не нужна: не переписывай естественный русский текст, только расставь разметку на первые вхождения англо-жаргона.
- Смысл и факты сохраняй точно; не добавляй нового.`

const CONCEPT_PROPS = {
  id: { type: 'string' },
  keep: { type: 'boolean' },
  reason: { type: 'string' },
  tldr_ru: { type: 'string' },
  explanation_ru: { type: 'string' },
  key_points_ru: { type: 'array', items: { type: 'string' } },
}
const SEC_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['section_id', 'concepts'],
  properties: {
    section_id: { type: 'string' },
    concepts: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['id', 'keep', 'reason', 'tldr_ru', 'explanation_ru', 'key_points_ru'],
      properties: CONCEPT_PROPS } },
  },
}
const DEDUP_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['drop_ids'],
  properties: {
    drop_ids: { type: 'array', items: { type: 'string' } },
    note: { type: ['string', 'null'] },
  },
}
const GTERM_PROPS = {
  term_en: { type: 'string' },
  definition_ru: { type: 'string' },
  keep: { type: 'boolean' },
}
const GLOSS_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['glossary'],
  properties: {
    glossary: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['term_en', 'definition_ru', 'keep'], properties: GTERM_PROPS } },
  },
}

phase('Review')
const reviewed = await parallel(IDS.map(sid => () => agent(
`Ты редактор русского учебного разбора подкаста про ${TOPIC}.
STRICT: Read tool на ТОЧНО этот абсолютный путь: ${PJ}. Не ищи и не читай другие файлы. Если тема файла явно не про этот эпизод — ты открыл не тот файл, перечитай ${PJ}.

Возьми секцию sections[] с id=="${sid}". Для КАЖДОГО её концепта реши и верни:
- id (без изменений), keep (bool), reason (1 фраза почему).
- keep=false если концепт АГРЕССИВНО нерелевантен учебному ядру: реклама/спонсор/самопромо, интро/аутро-вода, светская болтовня, анекдот/отступление без учебной ценности, или почти дубликат соседнего по смыслу.
- keep=true для содержательных тезисов о модели/механизме/прогнозе.
Если keep=true — верни РУССИФИЦИРОВАННЫЕ tldr_ru, explanation_ru, key_points_ru (тот же смысл и кол-во буллетов) по правилам ниже. Если keep=false — продублируй исходные значения.

${RULES}

Верни строго по схеме (section_id="${sid}").`,
  { label: `review:${sid}`, phase: 'Review', schema: SEC_SCHEMA, agentType: 'general-purpose' })))

phase('Dedup')
const kept = []
for (const s of reviewed.filter(Boolean))
  for (const c of s.concepts)
    if (c.keep) kept.push({ id: c.id, section_id: s.section_id, tldr: c.tldr_ru })

const dedup = await agent(
`Вот список оставшихся концептов (id + section_id + тезис; разметку [[term|перевод]] игнорируй, смотри смысл):
${JSON.stringify(kept, null, 1)}

Найди СЕМАНТИЧЕСКИЕ дубли — по сути об одном и том же (даже в разных секциях). В каждом кластере оставь ОДИН лучший, остальные id — в drop_ids.`,
  { label: 'dedup', phase: 'Dedup', schema: DEDUP_SCHEMA })

phase('Glossary')
const gloss = await agent(
`STRICT: Read tool на ТОЧНО этот путь: ${PJ}. Возьми массив glossary[].
Для каждого термина верни {term_en (без изменений), definition_ru (РУССИФИЦИРОВАННОЕ с разметкой [[term|перевод]]), keep (false если реклама/мусор/нерелевантно ядру)}.

${RULES}`,
  { label: 'glossary', phase: 'Glossary', schema: GLOSS_SCHEMA })

return { reviewed: reviewed.filter(Boolean), drop_ids: dedup.drop_ids, dedup_note: dedup.note, glossary: gloss.glossary }
