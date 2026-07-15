"""Tests for validate_podcast.py publish discipline and podcast_io atomic writes.

Requires jsonschema at test time (run via
`uv run --with pytest --with 'jsonschema>=4,<5' pytest podcast-deepdive/tests/ -q`).
"""
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path


def _load(name, script):
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPTS = Path(__file__).parents[1] / "scripts"
validate_podcast = _load("podcast_validate", SCRIPTS / "validate_podcast.py")
podcast_io = _load("podcast_io_module", SCRIPTS / "podcast_io.py")


def minimal_podcast():
    return {
        "schema_version": "podcast-1.0",
        "episode": {
            "title_en": "Sample episode",
            "title_ru": "Пример эпизода",
            "show": "Sample Show",
            "youtube_id": "abc123",
            "url": "https://youtube.com/watch?v=abc123",
            "summary_ru": "Короткое описание эпизода по-русски.",
        },
        "speakers": [
            {"id": "host", "name": "Host Person", "role": "host", "bio_ru": "Ведущий."}
        ],
        "sections": [
            {
                "id": "intro",
                "title_en": "Intro",
                "title_ru": "Введение",
                "intro_ru": "О чём эпизод.",
                "concepts": [
                    {
                        "id": "concept-one",
                        "term_en": "concept",
                        "tldr_ru": "Тезис.",
                        "explanation_ru": "Объяснение концепта по-русски.",
                        "key_points_ru": ["Первый тезис.", "Второй тезис."],
                        "visual": {"type": "svg", "title_ru": "Схема"},
                    }
                ],
            }
        ],
        "qa_seeds": [
            {
                "id": "qa-one",
                "question_ru": "Что такое concept?",
                "expected_answer_points": ["Определение."],
                "difficulty": "easy",
            }
        ],
    }


class PublishPodcastTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.final = self.root / "podcast.json"
        self.draft = self.root / "podcast.json.draft"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, value):
        payload = json.dumps(value, ensure_ascii=False, indent=2)
        path.write_text(payload, encoding="utf-8")
        return path.read_bytes()

    def test_valid_draft_publishes_and_removes_draft(self):
        old = minimal_podcast()
        old["episode"]["title_ru"] = "Старая версия"
        self.write(self.final, old)
        draft_bytes = self.write(self.draft, minimal_podcast())

        code = validate_podcast.main(
            ["publish", str(self.draft), str(self.final), "--stage", "final"]
        )

        self.assertEqual(code, 0)
        self.assertEqual(draft_bytes, self.final.read_bytes())
        self.assertFalse(self.draft.exists(), "draft is removed after success")

    def test_invalid_draft_leaves_final_untouched_and_keeps_draft(self):
        old_bytes = self.write(self.final, minimal_podcast())
        broken = minimal_podcast()
        del broken["speakers"]
        broken["qa_seeds"][0]["difficulty"] = "impossible"
        self.write(self.draft, broken)

        code = validate_podcast.main(
            ["publish", str(self.draft), str(self.final), "--stage", "final"]
        )

        self.assertEqual(code, 1)
        self.assertEqual(old_bytes, self.final.read_bytes())
        self.assertTrue(self.draft.exists(), "failed publish keeps the draft")

    def test_publish_rejects_draft_equal_to_final(self):
        self.write(self.final, minimal_podcast())
        alias = self.root / "sub" / ".." / "podcast.json"

        for draft_arg in (self.final, alias):
            with self.subTest(draft=draft_arg):
                code = validate_podcast.main(
                    ["publish", str(draft_arg), str(self.final), "--stage", "final"]
                )
                self.assertEqual(code, 1)
                self.assertTrue(
                    self.final.exists(),
                    "publish X X must never delete the published artifact",
                )

    def test_assembled_stage_relaxes_only_enrich_fields(self):
        assembled = minimal_podcast()
        concept = assembled["sections"][0]["concepts"][0]
        del concept["tldr_ru"]
        del concept["key_points_ru"]

        self.assertEqual(validate_podcast.validate_object(assembled, "assembled"), [])
        self.assertTrue(validate_podcast.validate_object(assembled, "final"))

        del concept["explanation_ru"]
        self.assertTrue(
            validate_podcast.validate_object(assembled, "assembled"),
            "non-enrich required fields still enforced at assembled stage",
        )


class AtomicWriteJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_preserves_existing_mode(self):
        target = self.root / "podcast.json"
        target.write_text("{}", encoding="utf-8")
        target.chmod(0o640)

        podcast_io.atomic_write_json({"a": 1}, str(target))

        self.assertEqual(0o640, stat.S_IMODE(os.stat(target).st_mode))
        self.assertEqual({"a": 1}, json.loads(target.read_text(encoding="utf-8")))

    def test_creates_new_file_with_default_mode_and_no_temp_leftovers(self):
        target = self.root / "new.json"

        podcast_io.atomic_write_json({"b": 2}, str(target))

        self.assertEqual(0o644, stat.S_IMODE(os.stat(target).st_mode))
        self.assertEqual([target.name], [p.name for p in self.root.iterdir()])


if __name__ == "__main__":
    unittest.main()
