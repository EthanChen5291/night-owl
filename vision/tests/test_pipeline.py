import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))
sys.path.insert(0, str(VISION / "pi"))

from detect import Det, EventGate, post_event  # noqa: E402
from eval_events import score_pushes  # noqa: E402
from make_dataset import check_label, main as make_dataset  # noqa: E402
from promote_model import main as promote  # noqa: E402
from replay_video import clip_time  # noqa: E402
from train_model import sha256  # noqa: E402


class EventTests(unittest.TestCase):
    def test_http_success_without_acceptance_is_not_score_update(self):
        for accepted in (True, False):
            response = io.BytesIO(json.dumps({"ok": True, "accepted": accepted}).encode())
            response.status = 200
            with patch("urllib.request.urlopen", return_value=response):
                updated, note = post_event("http://127.0.0.1:8000", {"class": "rat"})
            self.assertIs(updated, accepted)
            self.assertIn(f"accepted={str(accepted).lower()}", note)

    def test_video_time_uses_recorded_pts_or_fps(self):
        self.assertEqual(clip_time(0, 15, 0, None), 0)
        self.assertAlmostEqual(clip_time(1, 15, 66.67, 0), .06667)
        self.assertAlmostEqual(clip_time(2, 15, 0, .06667), 2 / 15)

    def test_requires_consecutive_hits_and_uses_current_box(self):
        gate = EventGate(hits_needed=3, window_s=1, cooldown_s=2)
        a = Det("rat", .9, .1, .5, .1, .1)
        b = Det("rat", .6, .5, .5, .1, .1)
        self.assertIsNone(gate.update(0, a))
        self.assertIsNone(gate.update(.1, None))
        self.assertIsNone(gate.update(.2, a))
        self.assertIsNone(gate.update(.3, a))
        fired = gate.update(.4, b)
        self.assertIs(fired[0], b)
        self.assertEqual(fired[1], 3)
        self.assertIsNone(gate.update(1, a))
        self.assertEqual(len(gate.hits), 0)

    def test_window_restarts_streak(self):
        gate = EventGate(hits_needed=3, window_s=.5)
        d = Det("rat", .9, .1, .5, .1, .1)
        self.assertIsNone(gate.update(0, d))
        self.assertIsNone(gate.update(.4, d))
        self.assertIsNone(gate.update(.6, d))
        self.assertIsNone(gate.update(.7, d))
        self.assertIsNotNone(gate.update(.8, d))

    def test_one_event_cannot_hit_two_pushes_and_extra_event_is_false(self):
        hit, false = score_pushes([(1.1, .9)], [1.0, 1.2], .5, .5)
        self.assertEqual((hit, false), (1, []))
        hit, false = score_pushes([(1.1, .9), (1.15, .8)], [1.0], .5, .5)
        self.assertEqual(hit, 1)
        self.assertEqual(len(false), 1)


class DataTests(unittest.TestCase):
    def test_missing_label_is_not_a_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "missing.txt"
            with self.assertRaisesRegex(ValueError, "missing label"):
                check_label(p)
            p.write_text("")
            self.assertEqual(check_label(p), [])
            p.write_text("0 0.99 0.5 0.1 0.2\n")
            with self.assertRaisesRegex(ValueError, "outside image"):
                check_label(p)

    def test_dataset_has_disjoint_clip_tags_and_reviewed_negatives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames, labels, out = root / "frames", root / "labels", root / "dataset"
            frames.mkdir()
            labels.mkdir()
            stems = [f"{tag}_{i:05d}" for tag in ("train_a", "val_b") for i in (0, 1)]
            for stem in stems:
                (frames / f"{stem}.jpg").write_bytes(b"test frame")
                (labels / f"{stem}.txt").write_text("0 0.5 0.5 0.2 0.2\n" if stem.endswith("00000") else "")
            (labels / "_reviewed.txt").write_text("".join(f"{stem}\tkeep\t2026-09-26\n" for stem in stems))
            self.assertEqual(make_dataset(["--frames", str(frames), "--labels", str(labels),
                                           "--out", str(out), "--val-tags", "val_b", "--color"]), 0)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["train_tags"], ["train_a"])
            self.assertEqual(manifest["val_tags"], ["val_b"])
            self.assertEqual((manifest["train_empty"], manifest["val_empty"]), (1, 1))

    def test_promotion_requires_both_gates_for_same_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "candidate.onnx"
            model.write_bytes(b"candidate")
            digest = sha256(model)
            train_path, event_path = root / "train.json", root / "event.json"
            train = {"candidate": str(model), "candidate_sha256": digest,
                     "gate_a_pass": False, "onnx_parity": {"pass": True}, "reviewed_only": True}
            event = {"gate_status": "PASS", "model_sha256": digest, "hits": 3,
                     "gray": True, "selected_conf": .5, "floor_y": .4,
                     "min_rat_width": .01, "max_rat_width": .65,
                     "window": 1.0, "cooldown": 2.0,
                     "results": [{"conf": .5, "pushes": 20, "neg_minutes": 3,
                                  "recall": .95, "neg_per_min": .1}]}
            train_path.write_text(json.dumps(train))
            event_path.write_text(json.dumps(event))
            args = ["--training-report", str(train_path), "--event-report", str(event_path),
                    "--out", str(root / "pi" / "rat.onnx")]
            with self.assertRaises(SystemExit):
                promote(args)
            self.assertFalse((root / "pi" / "rat.onnx").exists())
            train["gate_a_pass"] = True
            train_path.write_text(json.dumps(train))
            self.assertEqual(promote(args), 0)
            self.assertEqual((root / "pi" / "rat.onnx").read_bytes(), b"candidate")
            self.assertEqual(json.loads((root / "pi" / "rat_config.json").read_text())["conf"], .5)
            event["selected_conf"] = .4
            event["results"][0]["conf"] = .4
            event_path.write_text(json.dumps(event))
            with self.assertRaises(SystemExit):
                promote(args)
            self.assertEqual(promote(args + ["--api-min-conf", ".4"]), 0)
            train["candidate"] = model.name
            train_path.write_text(json.dumps(train))
            self.assertEqual(promote(args + ["--api-min-conf", ".4"]), 0)


if __name__ == "__main__":
    unittest.main()
