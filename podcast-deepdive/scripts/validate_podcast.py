#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema>=4,<5"]
# ///
"""validate_podcast.py — Draft-07-валидация и атомарная публикация podcast.json.

Publish-дисциплина: assemble пишет sibling-draft, а final
заменяется только здесь и только после успешной валидации против
reference/podcast.schema.json (реально загружаемой, а не подмножества в коде).

Команды (запуск через `uv run`):
  validate <podcast.json|draft> [--stage assembled|final]
  publish  <draft> <final>     [--stage assembled|final]

Стадии конвейера:
  assembled — сразу после assemble_podcast.py: у концептов ещё нет
              tldr_ru/key_points_ru (их добавляет enrich-стадия), поэтому эти
              два required временно ослабляются. Остальной контракт полный.
  final     — полный контракт схемы (после enrich; обязателен перед build_page).

publish: валидирует байтовый снимок draft, атомарно заменяет final
(mkstemp+fsync+os.replace, права сохраняются) и удаляет draft после успеха;
при любой ошибке final не меняется, draft остаётся для инспекции.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR.parent / "reference" / "podcast.schema.json"

# Поля концепта, которые появляются только на enrich-стадии.
ENRICH_ONLY_CONCEPT_FIELDS = ("tldr_ru", "key_points_ru")


def load_schema(stage: str) -> dict:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if stage == "assembled":
        schema = copy.deepcopy(schema)
        concept_schema = (
            schema["properties"]["sections"]["items"]
            ["properties"]["concepts"]["items"]
        )
        concept_schema["required"] = [
            key for key in concept_schema["required"]
            if key not in ENRICH_ONLY_CONCEPT_FIELDS
        ]
    return schema


def validate_object(podcast: object, stage: str) -> list[str]:
    """Полная Draft-07-валидация; возвращает список строк-ошибок."""
    from jsonschema import Draft7Validator

    validator = Draft7Validator(load_schema(stage))
    errors = sorted(
        validator.iter_errors(podcast),
        key=lambda error: list(error.absolute_path),
    )
    findings = []
    for error in errors:
        where = "/".join(str(part) for part in error.absolute_path) or "$"
        findings.append("%s: %s" % (where, error.message))
    return findings


def _read_json_bytes(path: Path) -> tuple[bytes, object]:
    payload = path.read_bytes()
    return payload, json.loads(payload.decode("utf-8"))


def _atomic_replace(payload: bytes, destination: Path) -> None:
    mode = (
        stat.S_IMODE(destination.stat().st_mode)
        if destination.exists()
        else 0o644
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="." + destination.name + ".",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _print_errors(findings: list[str], subject: Path) -> None:
    print("ERROR: %s — %d schema violation(s):" % (subject, len(findings)),
          file=sys.stderr)
    for finding in findings[:40]:
        print("  - %s" % finding, file=sys.stderr)


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        _, podcast = _read_json_bytes(args.podcast)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print("ERROR: cannot read %s: %s" % (args.podcast, error), file=sys.stderr)
        return 1
    findings = validate_object(podcast, args.stage)
    if findings:
        _print_errors(findings, args.podcast)
        return 1
    print("OK: %s valid against podcast.schema.json (stage=%s)"
          % (args.podcast, args.stage))
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    if args.draft.resolve(strict=False) == args.final.resolve(strict=False):
        print("ERROR: draft and final resolve to the same file: %s\n"
              "publish would delete the just-published artifact — pass the "
              "sibling *.draft as the first argument" % args.final,
              file=sys.stderr)
        return 1
    try:
        payload, podcast = _read_json_bytes(args.draft)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print("ERROR: cannot read draft %s: %s" % (args.draft, error),
              file=sys.stderr)
        return 1
    findings = validate_object(podcast, args.stage)
    if findings:
        _print_errors(findings, args.draft)
        print("final не изменён: %s" % args.final, file=sys.stderr)
        return 1
    if args.final.is_symlink() or (args.final.exists() and not args.final.is_file()):
        print("ERROR: publish destination must be a regular file: %s" % args.final,
              file=sys.stderr)
        return 1
    try:
        _atomic_replace(payload, args.final)
    except OSError as error:
        print("ERROR: cannot publish %s: %s" % (args.final, error), file=sys.stderr)
        return 1
    try:
        args.draft.unlink()
    except OSError:
        pass  # публикация уже состоялась; повисший draft — не ошибка
    print("PUBLISHED: %s (stage=%s; draft удалён)" % (args.final, args.stage))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Draft-07 validation and atomic publication for podcast.json."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("podcast", type=Path)
    validate_parser.add_argument(
        "--stage", choices=("assembled", "final"), default="final"
    )
    validate_parser.set_defaults(handler=cmd_validate)

    publish_parser = commands.add_parser("publish")
    publish_parser.add_argument("draft", type=Path)
    publish_parser.add_argument("final", type=Path)
    publish_parser.add_argument(
        "--stage", choices=("assembled", "final"), default="final"
    )
    publish_parser.set_defaults(handler=cmd_publish)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
