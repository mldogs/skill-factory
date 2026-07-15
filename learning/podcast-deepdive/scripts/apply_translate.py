#!/usr/bin/env python3
"""
apply_translate.py — записать результат workflow translate-podcast-sections в i18n/.

stdlib-only. Делает:
  - i18n/_global.json  из result.global (summary_en, speakers, glossary, qa, debates);
  - i18n/<section>.json из result.sections[], МЕРДЖА в каждый концепт отложенные
    enrich EN-поля (tldr_en, key_points_en) из i18n_stash.json;
  - build_page.py читает эти файлы; отсутствующие поля падают обратно на RU.

Использование:
  python3 apply_translate.py --dir podcasts/<slug> --result <translate_result.json>
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from podcast_io import atomic_write_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--result", required=True)
    a = ap.parse_args()
    PD = a.dir
    res = json.load(open(a.result, encoding="utf-8"))
    idir = os.path.join(PD, "i18n")
    os.makedirs(idir, exist_ok=True)

    stash = {}
    spath = os.path.join(PD, "i18n_stash.json")
    if os.path.isfile(spath):
        stash = json.load(open(spath, encoding="utf-8"))

    # _global.json
    g = res.get("global")
    if g:
        atomic_write_json(g, os.path.join(idir, "_global.json"))

    n_sec = n_con = 0
    for s in res.get("sections", []):
        sid = s["section_id"]
        concepts = []
        for c in s.get("concepts", []):
            st = stash.get(c["id"], {})
            entry = {
                "id": c["id"],
                "explanation_en": c.get("explanation_en"),
                "analogy_en": c.get("analogy_en"),
                "visual_title_en": c.get("visual_title_en"),
            }
            if st.get("tldr_en"):
                entry["tldr_en"] = st["tldr_en"]
            if st.get("key_points_en"):
                entry["key_points_en"] = st["key_points_en"]
            concepts.append(entry)
            n_con += 1
        out = {"intro_en": s.get("intro_en"), "concepts": concepts}
        atomic_write_json(out, os.path.join(idir, sid + ".json"))
        n_sec += 1

    print("✓ i18n записан в %s" % idir)
    print("  _global.json: %s" % ("да" if g else "НЕТ"))
    print("  секций: %d, концептов: %d (с мерджем enrich tldr/key_points)" % (n_sec, n_con))


if __name__ == "__main__":
    main()
