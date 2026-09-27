#!/usr/bin/env python3
"""Prepare, then seal, the V6 development evidence after root releases the result.

Inventory is read-only. Sealing requires an explicit release JSON, complete model
outputs, and matching frozen data. The original formal MP4s stay in the V5
formal evidence archive and are referenced by hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

VISION = Path(__file__).resolve().parent
REPO = VISION.parent
DATASET = VISION / "dataset_v6"
SOURCE = VISION / "dataset_v6_hard_negatives"
RUN = VISION / "runs/modal-rat-v6-20260927"
OUTPUT = RUN / "recovery_output"
ARTIFACTS = VISION / "artifacts"
NAME = "rat-litroom-v6-development-candidate-20260927"
CORE_ZIP = ARTIFACTS / f"{NAME}.zip"
SOURCE_ZIP = ARTIFACTS / f"{NAME}-source-review.zip"
MAX_ZIP_BYTES = 99_000_000
MANIFEST_SHA = "4c93e15d309b1cd4fd8758bf1938642d7f37a95b0023bee18253a0b110bfe515"
PAIR_SHA = "9346b7f24af41366c3f75cc97339ef22cc8aaecec678edc6134c5fffa5f10335"
FORMAL_ARCHIVE = ARTIFACTS / "rat-litroom-v5-formal-event-evidence-20260927.zip"
FORMAL_ARCHIVE_SHA = "518f0a9c0c4aef94ee7f6a3ae318613fbc37e6689d8d9dfe2d8dfa40a98eb75f"
FORMAL_VIDEOS = {
    "formal_040512.mp4": "701e40f5c24691acdd602152ea0208dd9fa25c3ec57f6b0616c9118a969b623a",
    "formal_041054.mp4": "30c7f71326910f5b182e7af73ae03eb6e43f260ac2c1501814a074c6c7bcc3ec",
}
SOURCE_RESERVE_SHA = "1c87585db4bddd09bd083523a4170aebfacd184ddffdc2fd3e5537abc21a9091"
SOURCE_TRUTH_SHA = "754fa86b0dc8ed02ea3fd533454fcf0a4c07101fc5337afac6421290b312891b"
SOURCE_RELEASE_SHA = "9c37bbbf63ad95123464a3cec3c8cc764e0dfa5e72062acd7d58e6496dc116eb"
V5_LOCK_SHA = "22ffcee2d241eb0c016d0a3ae5d178ef8d35e1f6541d1b20674f2c9a81237259"
V5_ONNX_SHA = "652a05e8c08aaee11a2b4d3c9ae4c737387bf8ffcac3372a4d83d0df7d80ed3d"
CODE_DEPENDENCIES = (
    "replay_video.py", "eval_events.py", "verify_candidate.py", "pyproject.toml", "uv.lock",
    "pi/detect.py", "pi/camera.py", "pi/runtime-requirements.txt",
    "runs/modal-rat-v5-20260927/run_formal_event_once.py",
    "runs/modal-rat-v5-20260927/run_fresh_test_once.py",
    "runs/modal-rat-v5-20260927/candidate_lock.json",
    "runs/modal-rat-v5-20260927/rat.onnx",
    "dataset_v5/manifest.json", "dataset_v5/selection_manifest.json",
    "v5_formal_test/reserve.json",
    "v5_formal_test/capture_evidence_formal_040512.json",
    "v5_formal_test/capture_evidence_formal_041054.json",
    "v5_formal_test/review/root_release.json",
    "v5_formal_test/review/source_intervals.json",
    "v5_formal_test/review/formal_040512_frame_pts.csv",
    "v5_formal_test/review/formal_040512_indexed_pts.csv",
    "v5_formal_test/review/formal_040512_source_truth.json",
    "v5_formal_test/review/source_review_formal_041054.json",
    "v5_formal_test/review/source_review_formal_041054.md",
    "v5_formal_test/review/SOURCE_REVIEW.md",
    "v5_formal_test/review/SOURCE_OWNER_CONFIRMATION.md",
)
REQUIRED_OUTPUT = (
    "rat.onnx", "best.pt", "last.pt", "metrics.json", "training_report.json",
    "checkpoint_selection.json", "results.csv", "resolved_train_args.json",
)
OPTIONAL_OUTPUT = ("rat_best.pt", "trainer_best.pt", "ultralytics_args.yaml")
ALLOWED_RUN_SUFFIXES = {".md", ".json", ".log", ".py", ".csv", ".yaml", ".txt"}
ALLOWED_REPLAY_SUFFIXES = {".md", ".json", ".log", ".csv", ".jpg", ".jpeg", ".png", ".txt", ".py"}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pair_fingerprint(dataset: Path) -> str:
    digest = hashlib.sha256()
    for split in ("train", "val"):
        for image in sorted((dataset / "images" / split).iterdir()):
            label = dataset / "labels" / split / f"{image.stem}.txt"
            for path in (image, label):
                if not path.is_file() or path.is_symlink():
                    raise ValueError(f"missing or linked dataset file: {path}")
                digest.update(str(path.relative_to(dataset)).encode())
                digest.update(bytes.fromhex(sha(path)))
    return digest.hexdigest()


def checked_files(directory: Path):
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"linked input: {path}")
        if path.is_file():
            yield path


def add_file(files: dict[str, Path], path: Path, relative: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    if relative in files:
        raise ValueError(f"duplicate package path: {relative}")
    files[relative] = path


def verify_frozen_inputs() -> dict:
    freeze = json.loads((DATASET / "freeze.json").read_text())
    manifest = json.loads((DATASET / "manifest.json").read_text())
    if sha(DATASET / "manifest.json") != MANIFEST_SHA or freeze["manifest_sha256"] != MANIFEST_SHA:
        raise ValueError("V6 manifest changed")
    if pair_fingerprint(DATASET) != PAIR_SHA or freeze["image_label_fingerprint"] != PAIR_SHA:
        raise ValueError("V6 image/label pairs changed")
    if (manifest["train_frames"], manifest["val_frames"], manifest["extra_train_frames"]) != (694, 146, 42):
        raise ValueError("V6 frame counts changed")
    if set(manifest["train_tags"]) & set(manifest["val_tags"]):
        raise ValueError("train/validation clip overlap")
    source = json.loads((SOURCE / "source_selection.json").read_text())
    receipt = json.loads((SOURCE / "annotation_receipt.json").read_text())
    if len(source["selected_frames"]) != 67 or receipt["accepted_count"] != 42:
        raise ValueError("source-review partition changed")
    accepted = [row for row in source["selected_frames"] if row["review_status"] == "VISUALLY_REVIEWED_NO_VISIBLE_PLUSH"]
    excluded = [row for row in source["selected_frames"] if row["review_status"] != "VISUALLY_REVIEWED_NO_VISIBLE_PLUSH"]
    if len(accepted) != 42 or len(excluded) != 25:
        raise ValueError("source-review acceptance changed")
    for row in source["selected_frames"]:
        if sha(SOURCE / row["native_image_relpath"]) != row["native_image_sha256"]:
            raise ValueError(f"native source frame changed: {row['stem']}")
    for row in accepted:
        for source_path, dataset_path, digest_key in (
            (SOURCE / row["image_relpath"], DATASET / "images/train" / f"{row['stem']}.jpg", "image_sha256"),
            (SOURCE / row["label_relpath"], DATASET / "labels/train" / f"{row['stem']}.txt", "label_sha256"),
        ):
            if sha(source_path) != row[digest_key] or sha(dataset_path) != row[digest_key]:
                raise ValueError(f"accepted source or dataset pair changed: {row['stem']}")
    if sha(SOURCE / "source_selection.json") != freeze["source_selection_sha256"]:
        raise ValueError("source selection changed")
    if sha(SOURCE / "annotation_receipt.json") != freeze["source_annotation_receipt_sha256"]:
        raise ValueError("source annotation receipt changed")
    for rel, key in (("labels/_reviewed.txt", "review_marker_sha256"),
                     ("excluded.txt", "exclusion_file_sha256"),
                     ("empty_label_policy_audit.json", "empty_label_policy_audit_sha256")):
        if sha(SOURCE / rel) != receipt[key]:
            raise ValueError(f"source review changed: {rel}")
    if sha(FORMAL_ARCHIVE) != FORMAL_ARCHIVE_SHA:
        raise ValueError("V5 formal evidence archive changed")
    for path, expected in (
        (VISION / "v5_formal_test/reserve.json", SOURCE_RESERVE_SHA),
        (VISION / "v5_formal_test/review/source_intervals.json", SOURCE_TRUTH_SHA),
        (VISION / "v5_formal_test/review/root_release.json", SOURCE_RELEASE_SHA),
        (VISION / "runs/modal-rat-v5-20260927/candidate_lock.json", V5_LOCK_SHA),
        (VISION / "runs/modal-rat-v5-20260927/rat.onnx", V5_ONNX_SHA),
    ):
        if sha(path) != expected:
            raise ValueError(f"fixed replay input changed: {path}")
    formal_release = json.loads((VISION / "v5_formal_test/review/root_release.json").read_text())
    implementation = formal_release["implementation_sha256"]
    for role, rel in (
        ("formal_runner", "runs/modal-rat-v5-20260927/run_formal_event_once.py"),
        ("shared_runner_helpers", "runs/modal-rat-v5-20260927/run_fresh_test_once.py"),
        ("video_replay", "replay_video.py"), ("pi_detector", "pi/detect.py"),
    ):
        if sha(VISION / rel) != implementation[role]:
            raise ValueError(f"replay implementation differs from fixed root release: {rel}")
    launch = json.loads((RUN / "RECOVERY_LAUNCH.json").read_text())
    if sha(RUN / "modal_train_v6.py") != launch["launcher_sha256"]:
        raise ValueError("corrected trainer differs from launched source")
    with zipfile.ZipFile(FORMAL_ARCHIVE) as archive:
        for name, expected in FORMAL_VIDEOS.items():
            member = f"rat-litroom-v5-formal-event-evidence-20260927/vision/v5_formal_test/clips/{name}"
            digest = hashlib.sha256()
            with archive.open(member) as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError(f"referenced formal video changed: {name}")
    return {"manifest_sha256": MANIFEST_SHA, "image_label_fingerprint": PAIR_SHA,
            "freeze_sha256": sha(DATASET / "freeze.json"), "source_clip_sha256": FORMAL_VIDEOS["formal_041054.mp4"]}


def collect(release: dict | None) -> tuple[dict[str, Path], dict[str, Path], list[str]]:
    core: dict[str, Path] = {}
    review: dict[str, Path] = {}
    for path in checked_files(DATASET):
        add_file(core, path, f"dataset_v6/{path.relative_to(DATASET)}")
    for name in ("source_selection.json", "annotation_receipt.json", "empty_label_policy_audit.json",
                 "empty_label_policy_audit.md", "excluded.txt", "labels/_reviewed.txt"):
        add_file(core, SOURCE / name, f"source_review/{name}")
    for path in checked_files(SOURCE / "native_frames"):
        add_file(review, path, f"source_review/native_frames/{path.name}")
    for path in checked_files(SOURCE / "review_grids"):
        add_file(review, path, f"source_review/review_grids/{path.name}")
    for relative in CODE_DEPENDENCIES:
        add_file(core, VISION / relative, f"code/vision/{relative}")
    for relative in ("runs/modal-rat-v6-20260927/modal_train_v6.py",
                     "runs/modal-rat-v6-20260927/modal_train_v6_failed_import.py",
                     "runs/modal-rat-v6-20260927/run_development_replay_once.py"):
        add_file(core, VISION / relative, f"code/vision/{relative}")
    for path in sorted(RUN.iterdir()):
        if path.is_file() and path.suffix in ALLOWED_RUN_SUFFIXES:
            add_file(core, path, f"run/{path.name}")
    add_file(core, VISION / "V6_PLAN.md", "V6_PLAN.md")
    add_file(core, VISION / "V6_RESULTS.md", "V6_RESULTS.md")
    add_file(core, VISION / "runs/modal-rat-v5-20260927/V6_HARD_NEGATIVE_RECIPE.md", "V6_HARD_NEGATIVE_RECIPE.md")
    add_file(core, Path(__file__), "code/build_v6_bundle.py")
    missing = [name for name in REQUIRED_OUTPUT if not (OUTPUT / name).is_file()]
    if not missing:
        for path in checked_files(OUTPUT):
            if path.parent == OUTPUT and path.suffix in ALLOWED_RUN_SUFFIXES | {".pt", ".onnx"}:
                add_file(core, path, f"run/output/{path.name}")
        for name in REQUIRED_OUTPUT:
            if f"run/output/{name}" not in core:
                raise FileNotFoundError(OUTPUT / name)
    if release is not None:
        for raw in release.get("replay_paths", []):
            relative = Path(raw)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"invalid replay path: {raw}")
            replay_path = RUN / relative
            paths = checked_files(replay_path) if replay_path.is_dir() else [replay_path]
            for path in paths:
                if path.suffix not in ALLOWED_REPLAY_SUFFIXES:
                    raise ValueError(f"unsupported replay file: {path}")
                add_file(core, path, f"run/{path.relative_to(RUN)}")
    return core, review, missing


VERIFY_SCRIPT = '''#!/usr/bin/env python3
"""Run after extracting both V6 ZIPs into the same parent directory."""
import hashlib
from pathlib import Path
root = Path(__file__).resolve().parent
lines = (root / "SHA256SUMS").read_text().splitlines()
expected = {}
for line in lines:
    digest, relative = line.split("  ", 1)
    if relative in expected or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise SystemExit(f"Invalid checksum entry: {relative}")
    expected[relative] = digest
actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
if actual != set(expected):
    raise SystemExit(f"File inventory differs: missing={sorted(set(expected)-actual)}, extra={sorted(actual-set(expected))}")
for relative, digest in expected.items():
    h = hashlib.sha256()
    with (root / relative).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    if h.hexdigest() != digest:
        raise SystemExit(f"Checksum mismatch: {relative}")
print(f"Verified {len(expected)} files from V6 core and source-review archives")
'''


def write_zip(path: Path, stage: Path, names: list[str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in names:
            archive.write(stage / relative, f"{NAME}/{relative}")
    if path.stat().st_size >= MAX_ZIP_BYTES:
        raise ValueError(f"archive exceeds 99 MB GitHub margin: {path}")
    with zipfile.ZipFile(path) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError(f"ZIP CRC failure: {corrupt}")


def seal(release_path: Path, frozen: dict) -> None:
    release = json.loads(release_path.read_text())
    if (release.get("status") != "APPROVED_V6_BUNDLE" or
            release.get("candidate_status") != "REJECTED_DEVELOPMENT_CANDIDATE" or
            release.get("manifest_sha256") != MANIFEST_SHA or
            release.get("image_label_fingerprint") != PAIR_SHA or
            release.get("replay_paths") != [] or
            not release.get("candidate_onnx_sha256")):
        raise ValueError("root release must mark this exact V6 candidate rejected with no replay")
    core, review, missing = collect(release)
    if missing:
        raise FileNotFoundError(f"training output incomplete: {missing}")
    if CORE_ZIP.exists() or SOURCE_ZIP.exists():
        raise FileExistsError("V6 artifact already exists; preserve prior bundles")
    metrics = json.loads((OUTPUT / "metrics.json").read_text())
    report = json.loads((OUTPUT / "training_report.json").read_text())
    if (sha(OUTPUT / "rat.onnx") != release["candidate_onnx_sha256"] or
            metrics["dataset_manifest_sha256"] != MANIFEST_SHA or
            report["dataset_manifest_sha256"] != MANIFEST_SHA or
            metrics["dataset"]["dataset_sha256"] != PAIR_SHA):
        raise ValueError("training report, model, and frozen input do not match")
    if sha(OUTPUT / "rat.onnx") != metrics["artifacts_sha256"]["rat.onnx"]:
        raise ValueError("downloaded ONNX differs from Modal receipt")
    if not (metrics["epochs_completed"] == 30 and
            metrics["selection_gate_pass"] is False and
            metrics["checkpoint_selection_pass"] is False and
            metrics["v6_post_export_pass"] is False and
            metrics["person_nonregression_pass"] is False and
            metrics["onnx_parity_pass"] is True and
            report["gate_a_pass"] is False and
            report["selection_gate_pass"] is False):
        raise ValueError("V6 rejection or parity status differs from the audited result")
    source_reference = {
        "archive": str(FORMAL_ARCHIVE.relative_to(REPO)), "archive_sha256": FORMAL_ARCHIVE_SHA,
        "videos_in_archive": FORMAL_VIDEOS,
        "note": "The original 288s positive and 190s no-plush videos are in the immutable V5 formal evidence ZIP. This V6 package carries hashes and selected source frames, not duplicate videos."
    }
    with tempfile.TemporaryDirectory(prefix="v6-bundle-") as tmp:
        stage = Path(tmp) / NAME
        stage.mkdir()
        for relative, source in (core | review).items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        (stage / "source_review/formal_video_reference.json").write_text(json.dumps(source_reference, indent=2) + "\n")
        shutil.copy2(release_path, stage / "release.json")
        (stage / "bundle_meta.json").write_text(json.dumps({
            "purpose": "Rejected V6 development candidate, not fresh test or Pi promotion",
            "frozen_dataset": frozen, "candidate_onnx_sha256": release["candidate_onnx_sha256"],
            "core_archive": CORE_ZIP.name, "source_review_archive": SOURCE_ZIP.name,
            "replay_paths": release.get("replay_paths", []),
        }, indent=2) + "\n")
        (stage / "README.md").write_text(
            "# Rejected V6 development candidate evidence\n\n"
            "Extract both ZIPs into the same parent directory, then run `python3 verify_bundle.py` "
            "from this directory. The builder checked each ZIP CRC and capped each archive below 99 MB. "
            "`SHA256SUMS` checks every other extracted file. `bundle_meta.json` and `release.json` "
            "bind the model to the frozen reviewed data.\n\n"
            "This dataset consumes the failed V5 formal negative as development training data. "
            "The original formal MP4s remain in the immutable V5 formal evidence archive; "
            "`source_review/formal_video_reference.json` gives their exact hashes. "
            "V6 failed the predeclared development regression guards despite PT/ONNX parity. "
            "No V6 replay or Pi switch occurred. V6 needs new, independently recorded whole clips "
            "before a fresh 0.90 claim. `V6_RESULTS.md` gives the exact failed scores.\n\n"
            "`code/vision/` retains the original source-relative layout for the V6 trainer, "
            "V5 replay validators, Pi detector, runtime lockfiles, and frozen formal reserve/truth/release. "
            "To restore the original relative paths for source inspection or authorized replay, "
            "run the commands below from this extracted bundle directory. Set POC and V5_FORMAL_ZIP "
            "to your checkout and the separately verified V5 formal evidence archive.\n\n"
            "```sh\n"
            "mkdir -p \"$POC/vision/runs/modal-rat-v6-20260927/recovery_output\" \"$POC/vision/v5_formal_test/clips\"\n"
            "cp -R code/vision/. \"$POC/vision/\"\n"
            "cp -R dataset_v6 \"$POC/vision/\"\n"
            "cp -R run/output/. \"$POC/vision/runs/modal-rat-v6-20260927/recovery_output/\"\n"
            "mkdir -p \"$POC/vision/dataset_v6_hard_negatives/images\" \"$POC/vision/dataset_v6_hard_negatives/labels\"\n"
            "cp -R source_review/. \"$POC/vision/dataset_v6_hard_negatives/\"\n"
            "cp dataset_v6/images/train/formal_041054_*.jpg \"$POC/vision/dataset_v6_hard_negatives/images/\"\n"
            "cp dataset_v6/labels/train/formal_041054_*.txt \"$POC/vision/dataset_v6_hard_negatives/labels/\"\n"
            "unzip -p \"$V5_FORMAL_ZIP\" rat-litroom-v5-formal-event-evidence-20260927/vision/v5_formal_test/clips/formal_040512.mp4 > \"$POC/vision/v5_formal_test/clips/formal_040512.mp4\"\n"
            "unzip -p \"$V5_FORMAL_ZIP\" rat-litroom-v5-formal-event-evidence-20260927/vision/v5_formal_test/clips/formal_041054.mp4 > \"$POC/vision/v5_formal_test/clips/formal_041054.mp4\"\n"
            "```\n\n"
            "Check the archive and extracted MP4 hashes in `source_review/formal_video_reference.json`. "
            "The fixed replay code checks every source, model, implementation, and runtime hash again.\n"
        )
        (stage / "verify_bundle.py").write_text(VERIFY_SCRIPT)
        all_files = sorted(p for p in stage.rglob("*") if p.is_file())
        sums = "".join(f"{sha(p)}  {p.relative_to(stage)}\n" for p in all_files)
        (stage / "SHA256SUMS").write_text(sums)
        core_names = [str(p.relative_to(stage)) for p in stage.rglob("*") if p.is_file() and
                      not str(p.relative_to(stage)).startswith("source_review/native_frames/") and
                      not str(p.relative_to(stage)).startswith("source_review/review_grids/")]
        review_names = [str(p.relative_to(stage)) for p in stage.rglob("*") if p.is_file() and
                        (str(p.relative_to(stage)).startswith("source_review/native_frames/") or
                         str(p.relative_to(stage)).startswith("source_review/review_grids/"))]
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        try:
            write_zip(CORE_ZIP, stage, sorted(core_names))
            write_zip(SOURCE_ZIP, stage, sorted(review_names))
            # Hash verification against the exact stage contents, with both archives present.
            for archive_path in (CORE_ZIP, SOURCE_ZIP):
                with zipfile.ZipFile(archive_path) as archive:
                    for info in archive.infolist():
                        relative = Path(info.filename).relative_to(NAME)
                        if hashlib.sha256(archive.read(info)).hexdigest() != sha(stage / relative):
                            raise ValueError(f"archive member hash mismatch: {relative}")
        except Exception:
            CORE_ZIP.unlink(missing_ok=True)
            SOURCE_ZIP.unlink(missing_ok=True)
            raise
    print(json.dumps({"core": {"path": str(CORE_ZIP), "bytes": CORE_ZIP.stat().st_size, "sha256": sha(CORE_ZIP)},
                      "source_review": {"path": str(SOURCE_ZIP), "bytes": SOURCE_ZIP.stat().st_size, "sha256": sha(SOURCE_ZIP)},
                      "files_hashed": len(all_files)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seal", action="store_true", help="create both ZIPs after explicit root release")
    parser.add_argument("--release-note", type=Path, help="JSON with status APPROVED_V6_BUNDLE and exact candidate hash")
    args = parser.parse_args()
    frozen = verify_frozen_inputs()
    if args.seal:
        if args.release_note is None:
            parser.error("--seal needs --release-note")
        seal(args.release_note, frozen)
    else:
        core, review, missing = collect(None)
        print(json.dumps({"status": "inventory only; no archive written", "frozen": frozen,
                          "core_files_present": len(core), "source_review_files_present": len(review),
                          "missing_required_run_output": missing}, indent=2))


if __name__ == "__main__":
    main()
