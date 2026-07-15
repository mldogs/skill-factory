#!/usr/bin/env python3
"""
apply_prune_russify.py — применить результат workflow prune-russify-podcast к podcast.json.

stdlib-only. Делает:
  - дроп концептов (нерелевантные keep=false + семантические дубли drop_ids);
  - замена RU-полей кепнутых концептов на руссифицированные (с разметкой [[term|перевод]]);
  - руссификация глоссария + дроп нерелевантных терминов;
  - чистка i18n (удаление записей дропнутых концептов / пустых секций);
  - удаление осиротевших картинок assets/<id>.png;
  - удаление пустых секций;
  - структурная валидация ДО записи: невалидный результат не трогает диск;
    записи podcast.json/i18n атомарные (podcast_io.atomic_write_json).

Использование:
  python3 apply_prune_russify.py --dir podcasts/<slug> --result <wf_result.json>
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assemble_podcast import validate  # noqa: E402
from podcast_io import atomic_write_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--result", required=True)
    a = ap.parse_args()
    PD = a.dir
    res = json.load(open(a.result, encoding="utf-8"))

    # 1. drop set + russified map
    russ = {}
    drop = set(res.get("drop_ids") or [])
    drop_reasons = {}
    for s in res.get("reviewed", []):
        for c in s.get("concepts", []):
            if not c.get("keep"):
                drop.add(c["id"])
                drop_reasons[c["id"]] = c.get("reason", "")
            else:
                russ[c["id"]] = {
                    "tldr_ru": c["tldr_ru"],
                    "explanation_ru": c["explanation_ru"],
                    "key_points_ru": c["key_points_ru"],
                }
    # dedup drops (note reason)
    for cid in res.get("drop_ids") or []:
        drop_reasons.setdefault(cid, "семантический дубль")

    # 2. patch podcast.json
    pj = json.load(open(os.path.join(PD, "podcast.json"), encoding="utf-8"))
    removed_imgs, empty_secs, kept_ids = [], [], set()
    new_sections = []
    n_relevance = sum(1 for s in res.get("reviewed", []) for c in s.get("concepts", []) if not c.get("keep"))
    n_dedup = len(res.get("drop_ids") or [])
    for sec in pj["sections"]:
        keep_concepts = []
        for c in sec["concepts"]:
            if c["id"] in drop:
                if c.get("visual", {}).get("cache_filename"):
                    removed_imgs.append(c["visual"]["cache_filename"])
                continue
            r = russ.get(c["id"])
            if r:
                c["tldr_ru"] = r["tldr_ru"]
                c["explanation_ru"] = r["explanation_ru"]
                c["key_points_ru"] = r["key_points_ru"]
            keep_concepts.append(c)
            kept_ids.add(c["id"])
        if keep_concepts:
            sec["concepts"] = keep_concepts
            new_sections.append(sec)
        else:
            empty_secs.append(sec["id"])
    pj["sections"] = new_sections
    if not new_sections:
        print("ERROR: после prune не осталось ни одной секции — ничего не записано",
              file=sys.stderr)
        sys.exit(2)

    # 3. glossary: russify + drop flagged
    gl_new = {g["term_en"]: g for g in res.get("glossary", [])}
    out_gloss, gl_dropped = [], 0
    for g in pj.get("glossary", []):
        ng = gl_new.get(g["term_en"])
        if ng and not ng.get("keep", True):
            gl_dropped += 1
            continue
        if ng:
            g["definition_ru"] = ng["definition_ru"]
        out_gloss.append(g)
    pj["glossary"] = out_gloss

    # 4. validate ДО любой записи: невалидный результат не трогает диск
    errs = validate(pj)
    if errs:
        print("ERROR: результат prune не проходит структурную проверку — ничего не записано:",
              file=sys.stderr)
        for x in errs[:30]:
            print("   -", x, file=sys.stderr)
        sys.exit(2)

    atomic_write_json(pj, os.path.join(PD, "podcast.json"))

    # 5. i18n: drop concept entries for dropped ids; remove files for empty sections
    idir = os.path.join(PD, "i18n")
    for f in list(os.listdir(idir)) if os.path.isdir(idir) else []:
        if f == "_global.json" or not f.endswith(".json"):
            continue
        sid = f[:-5]
        path = os.path.join(idir, f)
        if sid in empty_secs:
            os.remove(path)
            continue
        d = json.load(open(path, encoding="utf-8"))
        d["concepts"] = [c for c in d.get("concepts", []) if c["id"] in kept_ids]
        atomic_write_json(d, path)

    # 6. remove orphaned images
    for cf in removed_imgs:
        p = os.path.join(PD, cf)
        if os.path.isfile(p):
            os.remove(p)

    print("✓ применено к %s" % os.path.join(PD, "podcast.json"))
    print("  дропнуто концептов: %d (нерелевантных %d + дублей %d)"
          % (len(drop), n_relevance, n_dedup))
    print("  пустых секций удалено: %d %s" % (len(empty_secs), empty_secs or ""))
    print("  глоссарий: руссифицирован, дропнуто терминов: %d" % gl_dropped)
    print("  картинок удалено (осиротевших): %d" % len(removed_imgs))
    print("  осталось: %d секций, %d концептов, %d терминов"
          % (len(pj["sections"]), sum(len(s["concepts"]) for s in pj["sections"]), len(pj["glossary"])))
    if drop_reasons:
        print("  причины дропа:")
        for cid, why in list(drop_reasons.items())[:40]:
            print("     - %s: %s" % (cid, why))
    print("  структура: OK")


if __name__ == "__main__":
    main()
