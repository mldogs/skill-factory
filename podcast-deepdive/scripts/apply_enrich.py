#!/usr/bin/env python3
"""
apply_enrich.py — применить результат workflow enrich-podcast-concepts к podcast.json.

stdlib-only. Делает:
  - вписывает tldr_ru + key_points_ru в каждый концепт podcast.json;
  - ГИБРИД-визуал: make_image=true -> visual.type="image" + image_prompt + cache_filename
    (assets/<id>.png) + подпись (caption_ru -> analogy_ru/visual.title_ru); make_image=false ->
    оставляет диаграмму-компонент (если analyze выбрал image без компонента — откат на "define");
  - откладывает EN-поля (tldr_en, key_points_en, caption_en) в i18n_stash.json для мерджа в i18n/
    ПОСЛЕ шага translate (build_page читает tldr_en/key_points_en из i18n/<section>.json);
  - печатает список картинок к генерации (generate_image.py).

Использование:
  python3 apply_enrich.py --dir podcasts/<slug> --result <enrich_result.json>
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

    # id -> enrich payload
    emap = {}
    for s in res.get("sections", []):
        for c in s.get("concepts", []):
            emap[c["id"]] = c

    pj = json.load(open(os.path.join(PD, "podcast.json"), encoding="utf-8"))
    stash = {}          # id -> {tldr_en, key_points_en, caption_en}
    to_generate = []    # (id, prompt, cache_filename)
    n_img = n_diagram = n_missing = 0

    for sec in pj["sections"]:
        for c in sec["concepts"]:
            e = emap.get(c["id"])
            if not e:
                n_missing += 1
                continue
            c["tldr_ru"] = e["tldr_ru"]
            c["key_points_ru"] = e["key_points_ru"]
            stash[c["id"]] = {
                "tldr_en": e["tldr_en"],
                "key_points_en": e["key_points_en"],
                "caption_en": e.get("caption_en"),
            }
            v = c.setdefault("visual", {})
            if e.get("make_image") and e.get("image_prompt"):
                cf = "assets/%s.png" % c["id"]
                v["type"] = "image"
                v["component"] = None
                v["params"] = None
                v["image_prompt"] = e["image_prompt"]
                v["cache_filename"] = cf
                cap = e.get("caption_ru") or v.get("title_ru")
                if cap:
                    v["title_ru"] = cap
                    v["alt_ru"] = v.get("alt_ru") or cap
                    c["analogy_ru"] = cap   # image caption renders from analogy_ru
                to_generate.append((c["id"], e["image_prompt"], cf))
                n_img += 1
            else:
                # diagram: ensure a valid css/svg component (analyze may have set image)
                if v.get("type") == "image" or not v.get("component"):
                    v["type"] = v.get("type") if v.get("type") in ("css", "svg") else "svg"
                    v["component"] = v.get("component") or "define"
                    v["image_prompt"] = None
                    v["cache_filename"] = None
                if v.get("type") == "image":
                    v["type"] = "svg"
                n_diagram += 1

    atomic_write_json(pj, os.path.join(PD, "podcast.json"))
    atomic_write_json(stash, os.path.join(PD, "i18n_stash.json"))

    print("✓ enrich применён к %s" % os.path.join(PD, "podcast.json"))
    print("  концептов: обновлено %d (image %d / diagram %d), без данных enrich: %d"
          % (len(stash), n_img, n_diagram, n_missing))
    print("  EN-поля отложены в i18n_stash.json (мердж после translate)")
    print("  картинок к генерации: %d" % len(to_generate))
    # machine-readable list for the image-gen loop
    atomic_write_json(to_generate, os.path.join(PD, "_images_to_generate.json"))
    for cid, prompt, cf in to_generate:
        print("     - %s -> %s" % (cid, cf))
    print("  проверка полного контракта: uv run %s validate %s --stage final"
          % (os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_podcast.py"),
             os.path.join(PD, "podcast.json")))


if __name__ == "__main__":
    main()
