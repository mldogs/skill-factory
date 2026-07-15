// analyze_book.workflow.js — book-deepdive stage 1 (run with the Workflow tool).
//
//   Workflow({ scriptPath: "<this file>",
//              args: { title: "...", author: "...", year: 2010, slug: "..." } })
//
// Map (authoritative structure + 6-9 teachable themes) -> Analyze (deep per-theme
// concepts + RU study doc) -> Verify (skeptical fact-check, esp. quotes) ->
// Synthesize (one ordered RU dataset whose concepts already declare a build-ready
// visual.component). Returns { map, theme_docs, verification, synth }. The skill
// (not this script — workflows can't touch disk) writes book.json + sources/*.md.
//
// COMPONENT CATALOG the synth must choose from (see reference/viz-components.md):
//   pipeline_vs_loop, tree, spiral, cycle, funnel, tug, budget, weights,
//   two_targets, timeline, gauge, principles, grid_style, arch, view_rays,
//   floor_plan, line_chart, floor_ceiling, ladder, split, radial_roles, bridge,
//   channel, many_to_one, verdict_cols, define, foggy_contract.

export const meta = {
  name: 'analyze-book',
  description: 'Deep, fact-checked analysis of a book -> verified bilingual concept dataset + per-theme source notes',
  phases: [
    { title: 'Map', detail: 'Authoritative structure (parts/chapters) + 6-9 teachable themes' },
    { title: 'Analyze', detail: 'Deep per-theme analysis: concepts, framing, modern bridge, quotes, proposed visual' },
    { title: 'Verify', detail: 'Adversarial fact-check per theme: claims, attributions, quotes' },
    { title: 'Synthesize', detail: 'Merge into ordered RU dataset: sections, concepts (+visual.component), glossary, Q&A' },
  ],
}

let A = args || {}
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
if (!A.title || !String(A.title).trim()) {
  throw new Error('analyze_book.workflow.js: `title` is required in args, e.g. { title: "The Design of Design", author: "Frederick P. Brooks Jr.", year: 2010, slug: "the-design-of-design" }')
}
const TITLE = String(A.title).trim()
const AUTHOR = A.author || 'the author'
const YEAR = A.year || ''
const BOOKREF = '"' + TITLE + '"' + (AUTHOR ? ' by ' + AUTHOR : '') + (YEAR ? ' (' + YEAR + ')' : '')

const COMPONENTS = [
  'pipeline_vs_loop', 'tree', 'spiral', 'cycle', 'funnel', 'tug', 'budget', 'weights',
  'two_targets', 'timeline', 'gauge', 'principles', 'grid_style', 'arch', 'view_rays',
  'floor_plan', 'line_chart', 'floor_ceiling', 'ladder', 'split', 'radial_roles', 'bridge',
  'channel', 'many_to_one', 'verdict_cols', 'define', 'foggy_contract',
]

const MAP_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['book', 'parts', 'themes'],
  properties: {
    book: {
      type: 'object', additionalProperties: false,
      required: ['title_en', 'author'],
      properties: {
        title_en: { type: 'string' }, subtitle_en: { type: ['string', 'null'] },
        author: { type: 'string' }, year: { type: ['integer', 'null'] },
        publisher: { type: ['string', 'null'] },
      },
    },
    parts: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['number', 'title_en', 'title_ru'],
        properties: {
          number: { type: 'integer' }, title_en: { type: 'string' }, title_ru: { type: 'string' },
          chapters: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    themes: {
      type: 'array', minItems: 6, maxItems: 9,
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'title_en', 'title_ru', 'one_line_ru', 'key_concepts'],
        properties: {
          id: { type: 'string' }, title_en: { type: 'string' }, title_ru: { type: 'string' },
          part_refs: { type: 'array', items: { type: 'integer' } },
          one_line_ru: { type: 'string' },
          key_concepts: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

const THEME_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['theme_id', 'title_ru', 'overview_ru', 'concepts', 'markdown_ru'],
  properties: {
    theme_id: { type: 'string' }, title_ru: { type: 'string' }, overview_ru: { type: 'string' },
    concepts: {
      type: 'array', minItems: 1,
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'term_en', 'term_ru', 'essence_ru', 'framing_ru', 'modern_application_ru', 'visual'],
        properties: {
          id: { type: 'string' }, term_en: { type: 'string' }, term_ru: { type: 'string' },
          essence_ru: { type: 'string' }, framing_ru: { type: 'string' },
          modern_application_ru: { type: 'string' }, analogy_ru: { type: ['string', 'null'] },
          quotes: {
            type: 'array',
            items: {
              type: 'object', additionalProperties: false, required: ['text_en', 'confidence'],
              properties: {
                text_en: { type: 'string' }, where: { type: ['string', 'null'] },
                confidence: { type: 'string', enum: ['verbatim_confident', 'paraphrase', 'uncertain'] },
              },
            },
          },
          visual: {
            type: 'object', additionalProperties: false, required: ['type', 'idea_ru'],
            properties: { type: { type: 'string', enum: ['css', 'svg', 'image'] }, idea_ru: { type: 'string' } },
          },
        },
      },
    },
    markdown_ru: { type: 'string' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['theme_id', 'overall', 'findings'],
  properties: {
    theme_id: { type: 'string' },
    overall: { type: 'string', enum: ['solid', 'minor_issues', 'major_issues'] },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false, required: ['claim', 'verdict', 'note_ru'],
        properties: {
          claim: { type: 'string' },
          verdict: { type: 'string', enum: ['supported', 'unsupported', 'uncertain'] },
          note_ru: { type: 'string' }, correction_ru: { type: ['string', 'null'] },
        },
      },
    },
    corrected_concepts: {
      type: ['array', 'null'],
      items: {
        type: 'object', additionalProperties: false, required: ['id', 'fix_ru'],
        properties: { id: { type: 'string' }, fix_ru: { type: 'string' } },
      },
    },
  },
}

const SYNTH_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['summary_ru', 'sections', 'glossary', 'qa_seeds'],
  properties: {
    summary_ru: { type: 'string' },
    sections: {
      type: 'array', minItems: 4,
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'title_en', 'title_ru', 'intro_ru', 'concepts'],
        properties: {
          id: { type: 'string' }, title_en: { type: 'string' }, title_ru: { type: 'string' },
          intro_ru: { type: 'string' },
          concepts: {
            type: 'array', minItems: 1,
            items: {
              type: 'object', additionalProperties: false,
              required: ['id', 'term_en', 'explanation_ru', 'visual'],
              properties: {
                id: { type: 'string' }, term_en: { type: 'string' },
                explanation_ru: { type: 'string' },
                analogy_ru: { type: ['string', 'null'] },
                quote_en: { type: ['string', 'null'] },
                visual: {
                  type: 'object', additionalProperties: false,
                  required: ['type', 'component', 'title_ru', 'alt_ru'],
                  properties: {
                    type: { type: 'string', enum: ['css', 'svg', 'image'] },
                    component: { type: 'string', enum: COMPONENTS },
                    params: { type: ['object', 'null'] },
                    title_ru: { type: 'string' }, alt_ru: { type: 'string' },
                    image_prompt: { type: ['string', 'null'] },
                    cache_filename: { type: ['string', 'null'] },
                  },
                },
              },
            },
          },
        },
      },
    },
    glossary: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false, required: ['term_en', 'definition_ru'],
        properties: { term_en: { type: 'string' }, definition_ru: { type: 'string' }, section_id: { type: ['string', 'null'] } },
      },
    },
    qa_seeds: {
      type: 'array', minItems: 6,
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'question_ru', 'expected_answer_points', 'difficulty'],
        properties: {
          id: { type: 'string' }, question_ru: { type: 'string' },
          expected_answer_points: { type: 'array', items: { type: 'string' } },
          difficulty: { type: 'string', enum: ['easy', 'medium', 'hard'] },
          section_id: { type: ['string', 'null'] },
        },
      },
    },
  },
}

// --------------------------------------------------------------------------- //
phase('Map')
async function mapBook(attempt) {
  return await agent(
    'You are a scholar of software-engineering literature. Produce an AUTHORITATIVE structural map of the PUBLISHED book ' + BOOKREF + '. ' +
    'CRITICAL: analyze ONLY this exact book. Do NOT read, infer from, or copy any local repository / workspace files, and never substitute a different book — ' +
    'the metadata you return MUST be the real metadata of ' + BOOKREF + ' (title_en must be its actual title). ' +
    'Use web search/fetch if available to verify the exact part and chapter titles; otherwise rely on solid knowledge of THIS specific book. ' +
    'Return: (1) book metadata; (2) the list of PARTS/chapters (the book\'s actual top-level structure) with their titles; (3) a clustering of the whole book into 6-9 TEACHABLE THEMES ' +
    'that together cover its transferable ideas — each with a stable slug id, EN+RU title, a one-line RU summary, and the key concepts it must cover. ' +
    'Be specific to THIS book, not generic theory.' +
    (attempt > 0 ? ' (RETRY: a previous attempt returned the WRONG book. Double-check that every field is about ' + BOOKREF + ' and nothing else.)' : ''),
    { label: attempt > 0 ? 'map-book-retry' : 'map-book', agentType: 'general-purpose', schema: MAP_SCHEMA }
  )
}
const TITLE_WORDS = (TITLE.split(':')[0] || TITLE).toLowerCase().split(/\s+/).filter((w) => w.length > 4)
function mapLooksRight(m) {
  const t = ((m && m.book && m.book.title_en) || '').toLowerCase()
  return TITLE_WORDS.length === 0 || TITLE_WORDS.some((w) => t.includes(w))
}
let map = await mapBook(0)
if (!mapLooksRight(map)) {
  log('Map returned an unexpected book ("' + ((map.book || {}).title_en) + '"); retrying once.')
  map = await mapBook(1)
}
const themes = (map.themes || []).slice(0, 9)
log('Map: "' + ((map.book || {}).title_en) + '" — ' + (map.parts ? map.parts.length : 0) + ' parts, ' + themes.length + ' themes.')

// --------------------------------------------------------------------------- //
const analyzed = await pipeline(
  themes,
  (t) => agent(
    'You are a senior researcher and teacher doing a DEEP, ACCURATE analysis of one theme from ' + BOOKREF + '.\n\n' +
    'THEME: "' + t.title_en + '" (' + t.title_ru + '). Parts: ' + JSON.stringify(t.part_refs || []) + '. ' +
    'Key concepts to cover (expand as warranted): ' + (t.key_concepts || []).join('; ') + '.\n\n' +
    'Ground everything in the author\'s ACTUAL arguments and examples — name the real examples/cases the book uses. ' +
    'Use web search/fetch to verify titles, terminology and quotes IF available.\n\n' +
    'For each concept: term_en (the author\'s own term), term_ru, essence_ru (plain meaning), framing_ru (the author\'s specific claim and WHY), ' +
    'modern_application_ru (how it transfers to modern software engineering AND AI-assisted / agentic coding — make that bridge concrete), optional analogy_ru. ' +
    'quotes: ONLY ones you are genuinely confident are real; set confidence honestly; NEVER fabricate verbatim text — paraphrase instead. ' +
    'visual: propose a concrete visualization (css/svg for diagrammatic ideas, image for strong metaphors) with idea_ru.\n\n' +
    'Also write markdown_ru: a thorough, well-structured Russian STUDY DOCUMENT for this theme (## / ### headings, English terms inline, the author\'s examples, key takeaways, and a final "## Применение в современной разработке и AI-инжиниринге" section). Aim for ~600-1000 words.',
    { label: 'analyze:' + t.id, phase: 'Analyze', agentType: 'general-purpose', schema: THEME_SCHEMA }
  ),
  (analysis, t) => agent(
    'You are a SKEPTICAL fact-checker reviewing an AI-produced analysis of a theme from ' + BOOKREF + '. ' +
    'Critically verify every substantive claim, attribution, terminology and ESPECIALLY any verbatim quotes (the highest risk — watch for fabricated-but-plausible quotes, ' +
    'and for quotes that actually belong to a different book by the same author or to a critic rather than the author). Use web search/fetch if available. ' +
    'For each finding: claim, verdict (supported/unsupported/uncertain), note_ru, optional correction_ru. List corrected_concepts (id + fix_ru) for anything needing a fix. Default to skepticism.\n\n' +
    'THEME ANALYSIS:\n' + JSON.stringify({
      theme_id: analysis.theme_id, title_ru: analysis.title_ru,
      concepts: (analysis.concepts || []).map((c) => ({ id: c.id, term_en: c.term_en, essence_ru: c.essence_ru, framing_ru: c.framing_ru, quotes: c.quotes || [] })),
    }),
    { label: 'verify:' + t.id, phase: 'Verify', agentType: 'general-purpose', schema: VERIFY_SCHEMA }
  ).then((v) => ({ theme: t, analysis, verification: v }))
)
const clean = analyzed.filter(Boolean)
log('Analyzed ' + clean.length + ' themes; ' + clean.filter((x) => x.verification && x.verification.overall !== 'solid').length + ' flagged.')

// --------------------------------------------------------------------------- //
phase('Synthesize')
const synthInput = clean.map((x) => ({
  theme: { id: x.theme.id, title_en: x.theme.title_en, title_ru: x.theme.title_ru },
  overview_ru: x.analysis.overview_ru,
  concepts: (x.analysis.concepts || []).map((c) => ({
    id: c.id, term_en: c.term_en, term_ru: c.term_ru, essence_ru: c.essence_ru,
    framing_ru: c.framing_ru, modern_application_ru: c.modern_application_ru,
    analogy_ru: c.analogy_ru || null,
    quotes: (c.quotes || []).filter((q) => q.confidence !== 'uncertain'),
    visual_idea: c.visual,
  })),
  verification: x.verification ? { overall: x.verification.overall, findings: x.verification.findings, corrected_concepts: x.verification.corrected_concepts || null } : null,
}))

const synth = await agent(
  'You are assembling the DATA MODEL for a single self-contained interactive Russian-language explainer page about ' + BOOKREF + '. ' +
  'You are given verified per-theme analyses with fact-check findings. APPLY every correction; drop/fix anything marked "unsupported"; qualify "uncertain".\n\n' +
  'Produce:\n' +
  '- summary_ru: 3-5 sentence thesis of the book.\n' +
  '- sections: ordered, ~one per theme (4-8). Each: stable slug id, title_en, title_ru, intro_ru (2-3 sentences), concepts.\n' +
  '- each concept: stable slug id, term_en (author\'s term), explanation_ru (self-contained RU, ~70-140 words, weaving essence + framing + one line of modern software/AI-engineering relevance; English terms inline), optional analogy_ru, optional quote_en (ONLY a verifier-confident quote else null), and a visual.\n' +
  '- visual: choose `component` from this catalog (STRONGLY prefer css/svg): ' + COMPONENTS.join(', ') + '. ' +
  'Set `type` ("css"/"svg", or "image" for AT MOST 2-3 of the most metaphorical concepts), `params` (e.g. {"variant":"descend"} for tree/spiral/timeline/line_chart, or {"left","right","left_good","right_good","cap"} for split, {"center","roles","cap"} for radial_roles; else null), `title_ru` and `alt_ru`. ' +
  'For image concepts also set `image_prompt` (SUBJECT only, English, no style words) and `cache_filename` "assets/<slug>.png", AND still pick a sensible `component` fallback. Match the component SHAPE to the idea.\n' +
  '- glossary: key English terms -> concise RU definitions (section_id where taught).\n' +
  '- qa_seeds: 6-10 active-recall questions (RU) with expected_answer_points + difficulty + section_id.\n\n' +
  'Cover the WHOLE book; keep all ids slug-style and stable.\n\nVERIFIED THEME MATERIAL:\n' + JSON.stringify(synthInput),
  { label: 'synthesize', schema: SYNTH_SCHEMA }
)

return {
  map,
  theme_docs: clean.map((x) => ({
    id: x.theme.id, title_en: x.theme.title_en, title_ru: x.theme.title_ru,
    markdown_ru: x.analysis.markdown_ru,
    verification_overall: x.verification ? x.verification.overall : null,
  })),
  verification: clean.map((x) => ({ id: x.theme.id, verification: x.verification })),
  synth,
}
