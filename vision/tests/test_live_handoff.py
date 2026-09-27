import base64
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

PI = Path(__file__).resolve().parents[1] / "pi"
sys.path.insert(0, str(PI))

from detect import Det  # noqa: E402
from live_bridge import HEADER, FrameHandoff, from_env  # noqa: E402
from live_worker import FrameProcessor, serve  # noqa: E402


def jpeg(color=(20, 40, 80)):
    image = np.full((80, 80, 3), color, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def packet(seq, mono, color=(20, 40, 80)):
    return HEADER.pack(mono, 1_700_000_000 + mono, seq) + jpeg(color)


class RatDetector:
    def infer(self, _gray):
        return [Det("rat", .91, .25, .25, .5, .5)]


class SuppressedDetector:
    def infer(self, _gray):
        return [Det("rat", .91, .25, .25, .5, .5),
                Det("person", .95, .2, .2, .6, .6)]


class BridgeTests(unittest.TestCase):
    def test_default_off_and_one_slot_latest_frame(self):
        self.assertIsNone(from_env({}))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(FrameHandoff, "_send_loop", lambda self: self.stopping.wait()):
                bridge = FrameHandoff(str(Path(tmp) / "absent.sock"))
                start = time.monotonic()
                for _ in range(1000):
                    bridge(b"frame")
                elapsed = time.monotonic() - start
                self.assertLess(elapsed, 1)
                self.assertEqual(bridge.pending.qsize(), 1)
                self.assertEqual(bridge.pending.get_nowait()[0], 1000)
                self.assertEqual(bridge.overwritten, 999)
                bridge.close()
                self.assertFalse(bridge.thread.is_alive())

    def test_sender_recovers_when_worker_socket_reappears(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "frames.sock")
            bridge = FrameHandoff(path)
            try:
                bridge(b"before-worker")
                deadline = time.monotonic() + 1
                while bridge.send_failed == 0 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertGreater(bridge.send_failed, 0)
                for seq, payload in ((2, b"first-worker"), (3, b"restarted-worker")):
                    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                        receiver.bind(path)
                        receiver.settimeout(1)
                        bridge(payload)
                        data = receiver.recv(1024)
                        self.assertEqual(HEADER.unpack_from(data)[2], seq)
                        self.assertEqual(data[HEADER.size:], payload)
                    Path(path).unlink()
            finally:
                bridge.close()
            self.assertFalse(bridge.thread.is_alive())


class WorkerTests(unittest.TestCase):
    def test_gap_cannot_complete_streak_and_crop_uses_current_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            processor = FrameProcessor(RatDetector(), out, hits=3, window=1, cooldown=2)
            self.assertIsNone(processor.process(packet(1, 1.0), now_monotonic=1.0))
            self.assertIsNone(processor.process(packet(3, 1.1), now_monotonic=1.1))
            self.assertIsNone(processor.process(packet(4, 1.2), now_monotonic=1.2))
            event = processor.process(packet(5, 1.3, (160, 20, 10)), now_monotonic=1.3)
            self.assertIsNotNone(event)
            self.assertEqual(processor.stats["sequence_gaps"], 1)
            self.assertEqual(event["n_hits"], 3)
            crop = cv2.imdecode(np.frombuffer(base64.b64decode(event["crop_b64"]), np.uint8),
                                cv2.IMREAD_COLOR)
            self.assertLess(crop.shape[0], 80)
            self.assertAlmostEqual(float(crop[:, :, 0].mean()), 160, delta=12)
            self.assertEqual(len(list(out.glob("event_*.jpg"))), 1)
            saved = json.loads(next(out.glob("event_*.json")).read_text())
            self.assertEqual(saved["bbox"], event["bbox"])
            self.assertNotIn("frame_b64", saved)

    def test_person_suppression_prevents_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            processor = FrameProcessor(SuppressedDetector(), Path(tmp), hits=3)
            for seq in (1, 2, 3):
                mono = 1 + seq * .1
                self.assertIsNone(processor.process(packet(seq, mono), now_monotonic=mono))
            self.assertEqual(processor.stats["rat_suppressed"], 3)
            self.assertEqual(processor.stats["events"], 0)

    def test_server_closes_socket_and_keeps_only_crop_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "frames.sock"
            processor = FrameProcessor(RatDetector(), root / "events", hits=3)
            ready, stop = threading.Event(), threading.Event()
            result = {}

            def run():
                result.update(serve(path, processor, stop, ready, max_frames=3))

            thread = threading.Thread(target=run)
            thread.start()
            self.assertTrue(ready.wait(1))
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
                for seq in (1, 2, 3):
                    sender.sendto(packet(seq, time.monotonic()), str(path))
                    time.sleep(.03)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertFalse(path.exists())
            self.assertEqual(result["frames_received"], 3)
            self.assertEqual(result["events"], 1)
            self.assertGreater(result["received_fps"], 0)
            self.assertGreater(result["processed_fps"], 0)
            self.assertGreater(result["inference_ms_total"], 0)

    def test_stale_and_nonfinite_timestamps_reset_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            processor = FrameProcessor(RatDetector(), Path(tmp), hits=3)
            self.assertIsNone(processor.process(packet(1, 1.0), now_monotonic=1.0))
            self.assertIsNone(processor.process(packet(2, 1.1), now_monotonic=3.0))
            self.assertIsNone(processor.process(packet(3, float("nan")), now_monotonic=3.1))
            self.assertIsNone(processor.process(packet(4, 3.2), now_monotonic=3.2))
            self.assertIsNone(processor.process(packet(5, 3.3), now_monotonic=3.3))
            self.assertIsNotNone(processor.process(packet(6, 3.4), now_monotonic=3.4))
            self.assertEqual(processor.stats["stale_frames"], 1)
            self.assertEqual(processor.stats["invalid_timestamps"], 1)

    def test_backlog_drops_to_newest_without_inventing_hits(self):
        class SlowDetector(RatDetector):
            def __init__(self):
                self.started = threading.Event()
                self.release = threading.Event()

            def infer(self, gray):
                self.started.set()
                self.release.wait(1)
                return super().infer(gray)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "frames.sock"
            detector = SlowDetector()
            processor = FrameProcessor(detector, root / "events", hits=3)
            ready, stop = threading.Event(), threading.Event()
            result = {}
            thread = threading.Thread(target=lambda: result.update(
                serve(path, processor, stop, ready, max_frames=6)))
            thread.start()
            self.assertTrue(ready.wait(1))
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
                sender.sendto(packet(1, time.monotonic()), str(path))
                self.assertTrue(detector.started.wait(1))
                for seq in range(2, 7):
                    sender.sendto(packet(seq, time.monotonic()), str(path))
            detector.release.set()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result["packets_received"], 6)
            self.assertEqual(result["backlog_dropped"], 4)
            self.assertEqual(result["frames_inferred"], 2)
            self.assertEqual(result["sequence_gaps"], 1)
            self.assertEqual(result["events"], 0)


if __name__ == "__main__":
    unittest.main()
