import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from seed_pilot import build_golden, build_pilot
from validate_dataset import load_taxonomy, validate


class DatasetToolTests(unittest.TestCase):
    def test_pilot_count_and_language_balance(self):
        rows = build_pilot()
        self.assertEqual(len(rows), 200)
        self.assertEqual(Counter(row["language"] for row in rows), {"bengali": 90, "banglish": 50, "hindi": 30, "english": 30})

    def test_behavior_balance(self):
        rows = build_pilot()
        self.assertEqual(sum(row["mode"] == "adult" for row in rows), 20)
        self.assertGreaterEqual(sum(row["category"] in {"deescalation", "boundary_setting", "topic_change"} for row in rows), 10)

    def test_multiturn_share(self):
        rows = build_pilot()
        self.assertEqual(sum(len(row["messages"]) > 3 for row in rows), 56)

    def test_pilot_includes_eight_turn_continuity_arcs(self):
        rows = build_pilot()
        long_rows = [row for row in rows if len(row["messages"]) == 9]
        self.assertEqual(len(long_rows), 8)
        self.assertEqual(Counter(row["language"] for row in long_rows), {
            "bengali": 2,
            "banglish": 2,
            "hindi": 2,
            "english": 2,
        })

    def test_all_adult_examples_have_marker(self):
        for row in build_pilot():
            if row["mode"] == "adult":
                self.assertIn("explicitly opted", row["messages"][0]["content"])

    def test_golden_is_separate_and_excluded(self):
        pilot = build_pilot()
        golden = build_golden(pilot)
        self.assertEqual(len(golden), 50)
        self.assertTrue(all(row["training_excluded"] for row in golden))
        pilot_prompts = {item["content"] for row in pilot for item in row["messages"] if item["role"] == "user"}
        self.assertTrue(all(row["user"] not in pilot_prompts for row in golden))

    def test_validator_accepts_pilot(self):
        root = Path(__file__).resolve().parents[1]
        taxonomy = load_taxonomy(root / "config/taxonomy.json")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.jsonl"
            path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in build_pilot()) + "\n", encoding="utf-8")
            report = validate(path, taxonomy)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["exact_duplicate_prompts"], [])
        self.assertEqual(report["exact_duplicate_replies"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
