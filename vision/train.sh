#!/usr/bin/env bash
# Fine-tune YOLO11n on dataset/data.yaml, export to ONNX, copy to pi/rat.onnx, print mAP50.
#
# Defaults are the ones in the handoff: yolo11n.pt, imgsz 416, 60 epochs, batch 32, project runs/,
# name rat. Override with env vars, e.g.  EPOCHS=5 ./train.sh  for a smoke run, DEVICE=mps on a Mac.
# Needs: pip install ultralytics onnx onnxslim   (onnxslim is what `simplify=True` uses)
#
# Gate (RUNBOOK): mAP50 for the rat class > 0.9 on the held-out val clips. The number printed at the
# end is that; the person class is reported too but does not gate.
set -euo pipefail
cd "$(dirname "$0")"

DATA="${DATA:-dataset/data.yaml}"
MODEL="${MODEL:-yolo11n.pt}"
IMGSZ="${IMGSZ:-416}"
EPOCHS="${EPOCHS:-60}"
BATCH="${BATCH:-32}"
PROJECT="${PROJECT:-runs}"
NAME="${NAME:-rat}"
DEVICE="${DEVICE:-}"           # "" = ultralytics picks; mps / cpu / 0
OUT_ONNX="${OUT_ONNX:-pi/rat.onnx}"

[ -f "$DATA" ] || { echo "no $DATA: run make_dataset.py first" >&2; exit 2; }

python3 - "$DATA" "$MODEL" "$IMGSZ" "$EPOCHS" "$BATCH" "$PROJECT" "$NAME" "$DEVICE" "$OUT_ONNX" <<'PY'
import shutil, sys
from pathlib import Path
data, model, imgsz, epochs, batch, project, name, device, out_onnx = sys.argv[1:]
from ultralytics import YOLO

kw = dict(data=data, imgsz=int(imgsz), epochs=int(epochs), batch=int(batch), project=project, name=name,
          exist_ok=True, plots=True, patience=20,
          # grayscale data: colour jitter is wasted, flips are fine, mosaic helps the small set
          hsv_h=0.0, hsv_s=0.0, hsv_v=0.4, fliplr=0.5, mosaic=1.0, close_mosaic=10)
if device:
    kw["device"] = device
yolo = YOLO(model)
yolo.train(**kw)

best = Path(project) / name / "weights" / "best.pt"
print(f"\nbest weights: {best}")

# held-out numbers, per class
m = YOLO(str(best)).val(data=data, imgsz=int(imgsz), plots=False, verbose=False, **({"device": device} if device else {}))
names = m.names
ap50 = m.box.ap50  # per class, in the order of names present in val
idx = list(m.box.ap_class_index)
print("\nheld-out val (whole clips):")
print(f"  mAP50 all classes : {m.box.map50:.3f}")
for ci, v in zip(idx, ap50):
    print(f"  AP50 {names[int(ci)]:<7}: {v:.3f}")
rat = {int(ci): v for ci, v in zip(idx, ap50)}.get(0)
if rat is not None:
    print(f"  GATE rat AP50 > 0.9 : {'PASS' if rat > 0.9 else 'FAIL'} ({rat:.3f})")

onnx = YOLO(str(best)).export(format="onnx", imgsz=int(imgsz), opset=12, simplify=True, dynamic=False)
dst = Path(out_onnx)
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(onnx, dst)
print(f"\nexported {onnx} -> {dst} ({dst.stat().st_size / 1e6:.1f} MB)")
print("next: scp pi/ to the node, then python3 detect.py --model rat.onnx  (or eval_events.py first)")
PY
