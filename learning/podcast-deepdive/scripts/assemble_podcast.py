#!/usr/bin/env python3
"""
assemble_podcast.py — собрать кандидата podcast.json из результата workflow анализа
+ сида, детерминированно заземлить цитаты по транскрипту и быстро проверить структуру.

stdlib-only. Пишет ТОЛЬКО sibling-draft `podcast.json.draft` (атомарно); публикует
final исключительно `validate_podcast.py publish` после Draft-07-валидации:

  python3 assemble_podcast.py --dir podcasts/<slug> --result <workflow_result.json>
  uv run validate_podcast.py publish podcasts/<slug>/podcast.json.draft \
    podcasts/<slug>/podcast.json --stage assembled

workflow_result.json = объект {map, sections, synth}, который вернул analyze-podcast
workflow (сохрани его из task-notification в файл).
"""
import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from podcast_io import atomic_write_json  # noqa: E402


# ---------- normalization / quote grounding ----------

def _stem(t):
    # crude morphology tolerance for inflected languages: long Cyrillic tokens
    # are compared by prefix, so «кусочки»/«кусочков» count as the same token
    if len(t) > 5 and re.search(r"[а-яё]", t):
        return t[:5]
    return t


def norm_tokens(s):
    # Unicode-aware: keeps any letters/digits (the old [a-z0-9] filter deleted
    # Cyrillic outright, so every Russian quote failed grounding)
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w'\s]", " ", s)
    return [_stem(t) for t in s.split()]


def coverage(quote, transcript_tokens):
    """Доля токенов цитаты, найденных как совпадающие блоки в транскрипте (0..1).
    Терпимо к лёгкой ASR-чистке (agentic vs a genetic) — мы не требуем дословности."""
    q = norm_tokens(quote)
    if not q:
        return 0.0
    sm = difflib.SequenceMatcher(None, transcript_tokens, q, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    return matched / len(q)


def ground_quotes(podcast, transcript_text, threshold=0.7):
    tt = norm_tokens(transcript_text)
    stats = {"kept": 0, "nulled": 0}

    def check(obj, qkey, provkey=None):
        q = obj.get(qkey)
        if not q:
            return
        cov = coverage(q, tt)
        if cov >= threshold:
            stats["kept"] += 1
        else:
            obj[qkey] = None
            if provkey:
                obj[provkey] = None
            stats["nulled"] += 1

    for sec in podcast.get("sections", []):
        for c in sec.get("concepts", []):
            check(c, "quote_en", "quote_provenance")
    for d in podcast.get("debates", []):
        for pos in d.get("positions", []):
            check(pos, "quote_en")
    return stats


# ---------- minimal schema validation ----------

def validate(podcast):
    """Лёгкая структурная проверка (без внешних пакетов): обязательные ключи,
    pattern для id, enum для difficulty/role/type. Возвращает список ошибок.

    Это быстрый smoke-фильтр для немедленной обратной связи; полный контракт
    (Draft-07 podcast.schema.json) принуждает validate_podcast.py на публикации."""
    errs = []
    ID = re.compile(r"^[a-z0-9-]+$")

    def need(obj, keys, where):
        for k in keys:
            if k not in obj or obj[k] in (None, ""):
                errs.append("%s: нет поля '%s'" % (where, k))

    if podcast.get("schema_version") != "podcast-1.0":
        errs.append("schema_version != podcast-1.0")
    episode = podcast.get("episode", {})
    need(episode, ["title_en", "title_ru", "show", "url", "summary_ru"], "episode")
    # youtube_id="" — документированный article-mode (веб-статья без видео),
    # поэтому пустая строка валидна; недопустимо только отсутствие/None
    if episode.get("youtube_id") is None:
        errs.append("episode: нет поля 'youtube_id' (для article-mode используй \"\")")
    if not podcast.get("speakers"):
        errs.append("speakers пуст")
    for s in podcast.get("speakers", []):
        need(s, ["id", "name", "role", "bio_ru"], "speaker")
        if s.get("role") not in ("host", "guest"):
            errs.append("speaker %s: role не host/guest" % s.get("id"))
    sec_ids = set()
    all_concept_ids = []
    for sec in podcast.get("sections", []):
        need(sec, ["id", "title_en", "title_ru", "intro_ru", "concepts"], "section")
        sec_ids.add(sec.get("id"))
        if sec.get("id") and not ID.match(sec["id"]):
            errs.append("section id '%s' не kebab-case" % sec["id"])
        for c in sec.get("concepts", []):
            need(c, ["id", "term_en", "explanation_ru", "visual"], "concept")
            all_concept_ids.append(c.get("id"))
            if c.get("visual", {}).get("type") not in ("css", "svg", "image"):
                errs.append("concept %s: visual.type некорректен" % c.get("id"))
    # id'ы концептов обязаны быть уникальны (иначе ломаются HTML-якоря и кеш картинок)
    dups = sorted({i for i in all_concept_ids if all_concept_ids.count(i) > 1})
    if dups:
        errs.append("дублирующиеся concept id: %s" % ", ".join(dups))
    for d in podcast.get("debates", []):
        need(d, ["id", "topic_ru", "positions"], "debate")
        if len(d.get("positions", [])) < 2:
            errs.append("debate %s: <2 позиций" % d.get("id"))
    if not podcast.get("qa_seeds"):
        errs.append("qa_seeds пуст")
    for q in podcast.get("qa_seeds", []):
        need(q, ["id", "question_ru", "expected_answer_points", "difficulty"], "qa")
        if q.get("difficulty") not in ("easy", "medium", "hard"):
            errs.append("qa %s: difficulty некорректен" % q.get("id"))
    return errs


# ---------- assembly ----------

def assemble(dir_, result):
    seed_path = os.path.join(dir_, "episode_seed.json")
    seed = json.load(open(seed_path, encoding="utf-8"))
    mp = result["map"]
    secs_content = {s["section_id"]: s for s in result["sections"] if s}
    synth = result["synth"]

    date = seed.get("upload_date")
    episode = {
        "title_en": seed.get("title_en"),
        "title_ru": mp.get("episode_title_ru") or seed.get("title_en"),
        "show": seed.get("show"),
        "episode_no": None,
        "date": date,
        "youtube_id": seed["youtube_id"],
        "url": seed["url"],
        "duration_seconds": seed.get("duration_seconds"),
        "duration_hhmmss": seed.get("duration_hhmmss"),
        "captions_kind": seed.get("captions_kind"),
        "summary_ru": synth.get("summary_ru"),
        "cover_alt_ru": synth.get("cover_alt_ru"),
    }

    sections = []
    debates = []
    for ms in mp["sections"]:
        content = secs_content.get(ms["id"], {})
        sec = {
            "id": ms["id"],
            "title_en": ms["title_en"],
            "title_ru": ms["title_ru"],
            "intro_ru": content.get("intro_ru", ms.get("one_line_ru", "")),
            "t_seconds": ms.get("t_seconds"),
            "source_docs": [],
            "concepts": content.get("concepts", []),
        }
        sections.append(sec)
        for d in content.get("debates", []) or []:
            d = dict(d)
            d["section_id"] = ms["id"]
            if d.get("t_seconds") is None:
                d["t_seconds"] = ms.get("t_seconds")
            debates.append(d)

    podcast = {
        "schema_version": "podcast-1.0",
        "episode": episode,
        "speakers": mp["speakers"],
        "chapters": mp.get("chapters", []),
        "sections": sections,
        "debates": debates,
        "glossary": synth.get("glossary", []),
        "qa_seeds": synth.get("qa_seeds", []),
    }
    return podcast


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--threshold", type=float, default=0.7)
    a = ap.parse_args()

    result = json.load(open(a.result, encoding="utf-8"))
    podcast = assemble(a.dir, result)

    # grounding
    slug = os.path.basename(os.path.normpath(a.dir))
    txt = os.path.join(a.dir, slug + ".txt")
    transcript = open(txt, encoding="utf-8").read()
    stats = ground_quotes(podcast, transcript, a.threshold)

    # quick structural check, then draft only — final публикует validate_podcast.py
    errs = validate(podcast)

    final = os.path.join(a.dir, "podcast.json")
    draft = final + ".draft"
    atomic_write_json(podcast, draft)

    print("✓ DRAFT: %s (final не тронут)" % draft)
    print("  секций: %d · концептов: %d · споров: %d · терминов: %d · Q&A: %d"
          % (len(podcast["sections"]),
             sum(len(s["concepts"]) for s in podcast["sections"]),
             len(podcast["debates"]), len(podcast["glossary"]), len(podcast["qa_seeds"])))
    print("  цитаты: подтверждено %d, обнулено %d (порог coverage=%.2f)"
          % (stats["kept"], stats["nulled"], a.threshold))
    if errs:
        print("  ⚠ СТРУКТУРА — %d проблем (исправь draft и повтори):" % len(errs))
        for x in errs[:30]:
            print("     -", x)
        sys.exit(2)
    print("  ✓ структура: OK; публикация:")
    print("    uv run %s publish %s %s --stage assembled"
          % (os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_podcast.py"),
             draft, final))


if __name__ == "__main__":
    main()
