import json
import sys
import tempfile
import unittest
from pathlib import Path

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))

from verify_candidate import inventory, match_counts  # noqa: E402


class CandidateVerificationTests(unittest.TestCase):
    def test_duplicate_with_higher_confidence_counts_as_false_positive(self):
        frames = [{"gt": [{"cls": 0, "xyxy": [10, 10, 30, 30]}],
                   "pred": [{"cls": 0, "conf": .7, "xyxy": [0, 0, 18, 18]},
                            {"cls": 0, "conf": .1, "xyxy": [11, 11, 29, 29]}]}]
        self.assertEqual(match_counts(frames, .5)["tp"], 0)
        self.assertEqual(match_counts(frames, .5)["fp"], 1)
        self.assertEqual(match_counts(frames, .05)["tp"], 1)
        self.assertEqual(match_counts(frames, .05)["fp"], 1)

    def test_rejects_train_manifest_with_validation_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "images/val").mkdir(parents=True)
            (root / "labels/val").mkdir(parents=True)
            (root / "images/val/table_c_00001.jpg").write_bytes(b"sample")
            (root / "labels/val/table_c_00001.txt").write_text("")
            (root / "manifest.json").write_text(json.dumps({
                "reviewed_only": True, "gray": True,
                "train_tags": ["table_a"], "val_tags": ["table_c"],
                "frames": {"train": ["table_c_00002.jpg"],
                           "val": ["table_c_00001.jpg"]},
            }))
            with self.assertRaisesRegex(ValueError, "held-out"):
                inventory(root)


if __name__ == "__main__":
    unittest.main()
