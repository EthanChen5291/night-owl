#!/usr/bin/env python3
"""Deploy a candidate only after box, ONNX, and held-out event gates pass."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from train_model import sha256


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--training-report", required=True)
    ap.add_argument("--event-report", required=True)
    ap.add_argument("--out", default="pi/rat.onnx")
    ap.add_argument("--api-min-conf", type=float, default=0.5,
                    help="BARN_OWL_MIN_CONF used by the API (default 0.5)")
    ap.add_argument("--allow-unreviewed", action="store_true",
                    help="explicit demo override when training used unreviewed auto-labels")
    args = ap.parse_args(argv)
    report_path = Path(args.training_report).resolve()
    train = json.loads(report_path.read_text())
    events = json.loads(Path(args.event_report).read_text())
    candidate = Path(train["candidate"])
    if not candidate.is_absolute():
        candidate = report_path.parent / candidate
    if not candidate.is_file() or sha256(candidate) != train.get("candidate_sha256"):
        ap.error("candidate missing or changed after training report")
    if not train.get("gate_a_pass") or not train.get("onnx_parity", {}).get("pass"):
        ap.error("rat AP50 or PT/ONNX parity gate failed")
    if not train.get("reviewed_only", False) and not args.allow_unreviewed:
        ap.error("training data was unreviewed; explicit --allow-unreviewed required")
    if events.get("gate_status") != "PASS" or events.get("model_sha256") != sha256(candidate):
        ap.error("passing event report for this exact candidate is required")
    selected = next((row for row in events.get("results", []) if row.get("conf") == events.get("selected_conf")), None)
    if not selected or selected.get("pushes", 0) < 20 or selected.get("neg_minutes", 0) < 3 or \
            selected.get("recall", 0) < 0.9 or selected.get("neg_per_min", float("inf")) >= 0.5:
        ap.error("event report lacks 20 pushes, 3 minutes of negatives, or the required rates")
    if events.get("hits") != 3 or events.get("gray") is not True:
        ap.error("event gate must use three consecutive hits and grayscale input")
    conf = events.get("selected_conf")
    if conf is None:
        ap.error("event report has no selected confidence threshold")
    if conf < args.api_min_conf:
        ap.error(f"selected detector confidence {conf} is below API minimum {args.api_min_conf}; "
                 "set --api-min-conf and BARN_OWL_MIN_CONF to the same lower value")
    dst = Path(args.out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate, dst)
    config = {"model_sha256": sha256(dst), "conf": conf,
              "floor_y": events["floor_y"], "min_rat_width": events["min_rat_width"],
              "max_rat_width": events["max_rat_width"], "hits": events["hits"],
              "window": events["window"], "cooldown": events["cooldown"],
              "api_min_conf": args.api_min_conf, "gray": True}
    config_path = dst.with_name("rat_config.json")
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(f"deployed {dst} ({config['model_sha256']}) with {config_path}\n"
          f"start the API with BARN_OWL_MIN_CONF={args.api_min_conf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
