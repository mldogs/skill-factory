#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema>=4,<5"]
# ///
"""validate_book.py — Draft-07-валидация book.json против reference/book.schema.json.

До этого скрипта схема книг нигде реально не принуждалась (SKILL.md предлагал
только `python3 -m json.tool` — чистый синтаксис). Запускать после каждого
изменения book.json и перед build_page.py:

  uv run validate_book.py <books/<slug>/book.json>
  uv run validate_book.py --all            # все books/*/book.json от корня проекта
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR.parent / "reference" / "book.schema.json"


def validate_file(book_path: Path, schema: dict) -> list[str]:
    from jsonschema import Draft7Validator

    try:
        book = json.loads(book_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return ["cannot read: %s" % error]
    errors = sorted(
        Draft7Validator(schema).iter_errors(book),
        key=lambda error: list(error.absolute_path),
    )
    return [
        "%s: %s" % ("/".join(str(p) for p in error.absolute_path) or "$",
                    error.message)
        for error in errors
    ]


def find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists() or (candidate / "CLAUDE.md").is_file():
            return candidate
    return start


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Draft-07 validation for book.json artifacts."
    )
    parser.add_argument("book", nargs="?", type=Path)
    parser.add_argument("--all", action="store_true",
                        help="validate every books/*/book.json under the project root")
    args = parser.parse_args(argv)
    if bool(args.book) == args.all:
        parser.error("pass either a book.json path or --all")

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    targets = (
        sorted(find_project_root(Path.cwd()).glob("books/*/book.json"))
        if args.all
        else [args.book]
    )
    if not targets:
        print("ERROR: no books/*/book.json found", file=sys.stderr)
        return 1

    failed = 0
    for target in targets:
        findings = validate_file(target, schema)
        if findings:
            failed += 1
            print("ERROR: %s — %d violation(s):" % (target, len(findings)),
                  file=sys.stderr)
            for finding in findings[:40]:
                print("  - %s" % finding, file=sys.stderr)
        else:
            print("OK: %s" % target)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
