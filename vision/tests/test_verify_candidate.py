import json
import sys
import tempfile
import unittest
from pathlib import Path

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))

from verify_candidate import (file_pair_fingerprint, inventory, match_counts,
                              sha256, verify_selection_disjoint,
                              verify_test_provenance)  # noqa: E402


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

    def test_test_only_manifest_requires_complete_hashed_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            source = project / "vision/final_test"
            dataset = source / "eval_dataset"
            (source / "frames").mkdir(parents=True)
            (source / "labels").mkdir()
            (project / "vision/clips").mkdir(parents=True)
            (dataset / "images/val").mkdir(parents=True)
            (dataset / "labels/val").mkdir(parents=True)
            stems = ["short_32_00000", "new_scene_203035_00000"]
            for stem in stems:
                (source / "frames" / f"{stem}.jpg").write_bytes(stem.encode())
                (source / "labels" / f"{stem}.txt").write_text("")
                (dataset / "images/val" / f"{stem}.jpg").write_bytes(stem.encode())
                (dataset / "labels/val" / f"{stem}.txt").write_text("")
            files = {
                "labels/_reviewed.txt": "short_32_00000\tmanual\ttoday\n",
                "labels/_reviewed_new_scene.txt": "new_scene_203035_00000\n",
                "excluded.txt": "",
                "new_scene_excluded.txt": "",
                "../clips/short_32.mp4": "clip",
                "new_scene_203035.mp4": "clip",
            }
            for name, contents in files.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents)
            def items(names):
                return [{"path": name, "sha256": sha256(source / name)} for name in names]
            manifest = {
                "gray": True, "reviewed_only": True, "test_only": True,
                "train_tags": [], "val_tags": ["short_32", "new_scene_203035"],
                "frames": {"train": [], "val": [f"{stem}.jpg" for stem in stems]},
                "provenance": {
                    "path_base": "vision/final_test",
                    "source_markers": items(["labels/_reviewed.txt", "labels/_reviewed_new_scene.txt"]),
                    "exclusion_files": items(["excluded.txt", "new_scene_excluded.txt"]),
                    "source_clips": items(["../clips/short_32.mp4", "new_scene_203035.mp4"]),
                    "source_image_label_sha256": file_pair_fingerprint(source, {f"{s}.jpg" for s in stems}, "frames", "labels"),
                    "eval_image_label_sha256": file_pair_fingerprint(dataset, {f"{s}.jpg" for s in stems}, "images/val", "labels/val"),
                },
            }
            (dataset / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(len(inventory(dataset, test_only=True)[1]), 2)
            self.assertEqual(verify_test_provenance(dataset, manifest, project)["reviewed_frames"], 2)
            with self.assertRaisesRegex(ValueError, "training validation"):
                inventory(dataset)
            (source / "labels" / "short_32_00000.txt").write_text("changed")
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                verify_test_provenance(dataset, manifest, project)

    def test_test_set_rejects_model_selection_clip_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            selection = Path(tmp)
            (selection / "manifest.json").write_text(json.dumps({
                "train_tags": ["short_32"], "val_tags": ["table_c"],
                "frames": {"train": ["short_32_00001.jpg"],
                           "val": ["table_c_00001.jpg"]},
            }))
            test = {"val_tags": ["short_32"],
                    "frames": {"val": ["short_32_00002.jpg"]}}
            with self.assertRaisesRegex(ValueError, "overlaps"):
                verify_selection_disjoint(test, selection)


if __name__ == "__main__":
    unittest.main()
