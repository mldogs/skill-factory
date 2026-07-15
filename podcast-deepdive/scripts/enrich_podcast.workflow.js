export const meta = {
  name: 'enrich-podcast-concepts',
  description: 'Restructure each concept (tldr + key points), pick hybrid image vs diagram, write image prompts, and translate the new fields EN',
  phases: [{ title: 'Enrich', detail: 'One agent per section: tldr + bullets + image decision + EN' }],
}

let A = args || {}
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
if (!A.pj) throw new Error('args.pj is required: absolute path to the target podcast.json (pass {"pj": "/abs/podcasts/<slug>/podcast.json", "ids": [...], "topic": "..."})')
const PJ = A.pj
const IDS = (Array.isArray(A.ids) && A.ids.length) ? A.ids : ["why-the-firm-breaks","organizational-singularity","exo-3-architecture",
  "agents-talking-to-agents","reshaping-the-org-and-four-phases","rewrite-methodology-and-stack",
  "the-100x-firm","what-survives-and-closing"]
const TOPIC = A.topic || "the \"organizational singularity\" (agentic AI, Coase's law, ExO 3.0)"

phase('Enrich')

const CONCEPT = {
  type: 'object', additionalProperties: false,
  required: ['id','tldr_ru','tldr_en','key_points_ru','key_points_en','make_image','image_prompt','caption_ru','caption_en'],
  properties: {
    id: { type: 'string' },
    tldr_ru: { type: 'string' },
    tldr_en: { type: 'string' },
    key_points_ru: { type: 'array', minItems: 2, maxItems: 4, items: { type: 'string' } },
    key_points_en: { type: 'array', minItems: 2, maxItems: 4, items: { type: 'string' } },
    make_image: { type: 'boolean' },
    image_prompt: { type: ['string','null'] },
    caption_ru: { type: ['string','null'] },
    caption_en: { type: ['string','null'] }
  }
}
const SEC = {
  type: 'object', additionalProperties: false,
  required: ['section_id','concepts'],
  properties: { section_id: {type:'string'}, concepts: { type:'array', items: CONCEPT } }
}

const out = await parallel(IDS.map(sid => () => agent(
`You improve the pedagogy of a bilingual (RU/EN) podcast study page about ${TOPIC}.

STRICT: Read the tool on EXACTLY this absolute path: ${PJ} — a PODCAST breakdown. Do NOT search or read any other file. If the file's topic is clearly unrelated to the episode, you opened the wrong file; re-read ${PJ}.

Take the section sections[] with id == "${sid}". For EACH concept in it (keep order, keep its id), produce:
- tldr_ru: ONE punchy Russian sentence (<=140 chars) — the single thesis to remember. Keep English terms inline (agentic, workflow, MTP, ExO...).
- tldr_en: the same in natural English.
- key_points_ru: 2-4 SHORT Russian bullets distilling the concept's explanation (each <=90 chars, no trailing period needed). These replace the dense paragraph as the scannable structure.
- key_points_en: same bullets in English (same count/order).
- make_image: HYBRID rule — true if this concept is best conveyed by a METAPHOR/scene (a vivid analogy is its key intuition); false if it's structural/numeric/diagrammatic (better as a CSS/SVG chart). Aim for roughly 40-50% true across the section. Look at the concept's analogy_ru: a strong concrete analogy => true.
- image_prompt: if make_image=true, an ENGLISH subject-only scene prompt illustrating the analogy (concrete objects/scene; NO style/color/lighting words, NO text or letters in the image). Else null.
- caption_ru / caption_en: if make_image=true, a SHORT caption (the analogy in one phrase) for the image; else null.

Return strictly per schema (section_id="${sid}").`,
  { label: `enrich:${sid}`, schema: SEC, agentType: 'general-purpose' })))

return { sections: out.filter(Boolean) }
