export const meta = {
  name: 'translate-podcast-sections',
  description: 'Translate podcast.json per-section RU fields to EN (sections only; absolute path, explicit ids)',
  phases: [{ title: 'Translate', detail: 'One agent per section, strict single-file read' }],
}

let A = args || {}
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
if (!A.pj) throw new Error('args.pj is required: absolute path to the target podcast.json (pass {"pj": "/abs/podcasts/<slug>/podcast.json", "ids": [...], "topic": "..."})')
const PJ = A.pj
if (!Array.isArray(A.ids) || !A.ids.length) throw new Error("args.ids is required: list of section ids to process")
const IDS = A.ids
const TOPIC = A.topic || "the episode's core topic"

phase('Translate')

const SECTION_I18N = {
  type: 'object', additionalProperties: false,
  required: ['section_id', 'intro_en', 'concepts'],
  properties: {
    section_id: { type: 'string' },
    intro_en: { type: 'string' },
    concepts: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['id', 'explanation_en', 'visual_title_en'],
      properties: {
        id: { type: 'string' },
        explanation_en: { type: 'string' },
        analogy_en: { type: ['string', 'null'] },
        visual_title_en: { type: 'string' } } } }
  }
}

const sections = await parallel(IDS.map(sid => () => agent(
`You translate RU->EN for a bilingual study site about an AI/technology podcast on ${TOPIC}.

STRICT: Use the Read tool on EXACTLY this absolute path: ${PJ}
Do NOT use Glob, Grep, or any search. Do NOT read any other .json file. That file is a PODCAST breakdown. If the topic of what you read is clearly unrelated to the episode, you opened the WRONG file — stop and re-read ${PJ}.

In that file, find the section in sections[] whose id == "${sid}". Translate its RU fields to natural English (keep inline English terms like agentic, workflow, MTP, ExO, OODA as-is):
- intro_ru -> intro_en
- for each concept (same order): { id (unchanged), explanation_ru -> explanation_en, analogy_ru -> analogy_en (or null), visual.title_ru -> visual_title_en }

Return strictly per schema with section_id="${sid}".`,
  { label: `i18n:${sid}`, schema: SECTION_I18N, agentType: 'general-purpose' })))

// ---------- _global: summary, speakers, glossary, qa, debates ----------
const GLOBAL_I18N = {
  type: 'object', additionalProperties: false,
  required: ['summary_en','speakers','glossary','qa','debates'],
  properties: {
    summary_en: { type: 'string' },
    speakers: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['id','bio_en'], properties: { id:{type:'string'}, bio_en:{type:'string'} } } },
    glossary: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['term_en','definition_en'], properties: { term_en:{type:'string'}, definition_en:{type:'string'} } } },
    qa: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['id','question_en','expected_answer_points_en'],
      properties: { id:{type:'string'}, question_en:{type:'string'}, expected_answer_points_en:{type:'array', items:{type:'string'}} } } },
    debates: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['id','topic_en','positions'],
      properties: { id:{type:'string'}, topic_en:{type:'string'}, resolution_en:{type:['string','null']},
        positions: { type:'array', items: { type:'object', additionalProperties:false,
          required:['claim_en'], properties:{ claim_en:{type:'string'} } } } } } }
  }
}
const globalI18n = await agent(
`You translate RU->EN for a bilingual study site about an AI/technology podcast on ${TOPIC}.

STRICT: Use the Read tool on EXACTLY this absolute path: ${PJ}. Do NOT search or read any other file.

Translate the GLOBAL fields (keep inline English terms as-is, natural English):
- summary_ru -> summary_en
- for each speakers[] item: { id (unchanged), bio_ru -> bio_en }
- for each glossary[] item: { term_en (unchanged), definition_ru -> definition_en }
- for each qa_seeds[] item: { id (unchanged), question_ru -> question_en, expected_answer_points -> expected_answer_points_en (same count/order) }
- for each debates[] item (may be empty []): { id (unchanged), topic_ru -> topic_en, resolution_ru -> resolution_en (or null), positions: [ { claim_ru -> claim_en } ] in order }

Return strictly per schema.`,
  { label: 'i18n:_global', schema: GLOBAL_I18N, agentType: 'general-purpose' })

return { sections: sections.filter(Boolean), global: globalI18n }
