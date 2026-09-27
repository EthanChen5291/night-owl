"""Held-out ranking and capture for Model A and Model B, by community district.

Why not "accuracy %": only ~10% of swept lots have rats, so a model that always says "no rats"
is ~90% "accurate" and useless. Instead:

  pairwise accuracy  = pooled out-of-fold AUC: how often a positive unit ranks above a
                       negative unit (50% = chance, 100% = perfect).
  top-20% capture    = share of outcome counts in highest-scored units. Entire cell-month
                       rows are included at the cutoff, so the selected share can exceed 20%.

Model A: each cell-month is one AUC unit, positive if it had any complaint; capture
counts all complaints in the highest-scored 20% of cell-month rows.
Model B: each swept lot is one weighted AUC unit, positive if rat activity was found;
all lots in a cell-month get the same score. Capture counts positive swept lots in
the highest-scored cell-months covering at least 20% of swept lots.
These AUCs have different outcomes and units, so their difference is not a measure
of reporting bias. Five spatial folds hold out whole community districts.

Run: python3 model/accuracy_report.py   -> prints, writes model/out/accuracy.json
"""
import importlib
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

models = importlib.import_module("03_models")
OUT = Path(__file__).resolve().parent / "out"


def capture(score: np.ndarray, pos: np.ndarray, total: np.ndarray, top: float = 0.2) -> float:
    """Share of positives in the top `top` share of units (weighted by `total`) ranked by score."""
    order = np.argsort(-score)
    cum = np.cumsum(total[order])
    cut = np.searchsorted(cum, top * cum[-1])
    return float(pos[order][: cut + 1].sum() / pos.sum())


def main() -> None:
    df = models.load()
    real = df[df.real_cd & (df.month <= "2026-08")]
    gkf = GroupKFold(n_splits=5)

    # ---- Model B: swept cell-months, lot-weighted
    b = real[real.n_sweep > 0].reset_index(drop=True)
    pb = np.zeros(len(b))
    for tr, te in gkf.split(b, groups=b.boro_cd):
        pb[te] = models.fit_b(b.iloc[tr]).predict(b.iloc[te][models.B_FEATS])
    pos, neg = b.n_sweep_rat.to_numpy(float), (b.n_sweep - b.n_sweep_rat).to_numpy(float)
    auc_b = roc_auc_score(np.r_[np.ones(len(b)), np.zeros(len(b))], np.r_[pb, pb], sample_weight=np.r_[pos, neg])
    cap_b = capture(pb, pos, b.n_sweep.to_numpy(float))

    # ---- Model A: cell-months since A_TRAIN_FROM, outcome = any complaint
    a = real[real.month >= models.A_TRAIN_FROM].reset_index(drop=True)
    pa = np.zeros(len(a))
    for tr, te in gkf.split(a, groups=a.boro_cd):
        pa[te] = models.fit_a(a.iloc[tr], models.A_FEATS).predict(a.iloc[te][models.A_FEATS])
    ya = (a.n_complaints > 0).to_numpy()
    auc_a = roc_auc_score(ya, pa)
    base_a = roc_auc_score(ya, a.complaints_12m)  # "just use last year's complaints"
    cap_a = capture(pa, a.n_complaints.to_numpy(float), np.ones(len(a)))

    res = {
        "model_b": {"pairwise_accuracy": round(auc_b, 3), "top20_capture_of_rats_found": round(cap_b, 3),
                    "rows": int(len(b)), "outcome": "rat activity on a swept lot"},
        "model_a": {"pairwise_accuracy": round(auc_a, 3), "baseline_last12m_complaints": round(base_a, 3),
                    "top20_capture_of_complaints": round(cap_a, 3), "rows": int(len(a)),
                    "outcome": "at least one rat complaint in the cell-month"},
        "method": "5-fold spatial CV by community district (held-out districts never seen in training)",
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "accuracy.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
