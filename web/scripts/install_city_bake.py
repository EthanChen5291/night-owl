#!/usr/bin/env python3
"""Install the pinned city-bake-v1 release asset into web/public/city.

Run from any directory: python3 web/scripts/install_city_bake.py
Requires the GitHub CLI with access to EthanChen5291/poc. Existing city data is
left untouched; remove or archive it deliberately before installing a new bake.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

REPO = "EthanChen5291/poc"
TAG = "city-bake-v1"
ASSET = "city-bake.tar.gz"
SHA256 = "5c7f43dcf1dffdcff79da49d657065e04a6e67e25dfc0c297fc98774ec57e802"
PUBLIC = Path(__file__).resolve().parents[1] / "public"
TARGET = PUBLIC / "city"
CLEAN_COAST = Path(__file__).resolve().parents[2] / "city" / "clean_coast.py"  # smooths the citywide land.json


def install() -> None:
    if TARGET.exists():
        raise SystemExit(f"City bake already exists; preserving it: {TARGET}")

    with tempfile.TemporaryDirectory(prefix=".city-bake-", dir=PUBLIC) as scratch:
        stage = Path(scratch)
        archive = stage / ASSET
        subprocess.run(
            ["gh", "release", "download", TAG, "--repo", REPO,
             "--pattern", ASSET, "--output", str(archive)],
            check=True,
        )
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != SHA256:
            raise ValueError(f"City bake SHA-256 mismatch: {digest}")

        payload = stage / "payload"
        seen: set[str] = set()
        with tarfile.open(archive, "r:gz") as members:
            for member in members:
                path = PurePosixPath(member.name)
                parts = path.parts
                if not parts or path.is_absolute() or ".." in parts:
                    raise ValueError(f"Unsafe archive path: {member.name}")
                # The asset was made on macOS and carries AppleDouble sidecars.
                if any(part.startswith("._") for part in parts):
                    continue
                if parts[0] != "city" or not (member.isdir() or member.isfile()):
                    raise ValueError(f"Unexpected archive member: {member.name}")
                if member.isdir():
                    continue
                relative = path.as_posix()
                if relative in seen:
                    raise ValueError(f"Duplicate archive path: {relative}")
                seen.add(relative)
                output = payload.joinpath(*parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                source = members.extractfile(member)
                if source is None:
                    raise ValueError(f"Unreadable archive member: {relative}")
                with source, output.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
                os.chmod(output, 0o644)

        city = payload / "city"
        required = ("meta.json", "areas.json", "tiles.json", "land.json", "parks.json", "water.json")
        if any(not (city / name).is_file() for name in required):
            raise ValueError("City bake is missing a required manifest or ground layer")
        meta = json.loads((city / "meta.json").read_text())
        areas = json.loads((city / "areas.json").read_text())
        tiles = json.loads((city / "tiles.json").read_text())
        if not (meta["centre"] == areas["centre"] == tiles["centre"] and
                tiles["res"] == 7 and len(areas["areas"]) == 5 and len(tiles["tiles"]) == 220):
            raise ValueError("City bake manifests do not match the expected release")
        if any(not (city / "tiles" / f"{tile_id}.json").is_file() for tile_id in tiles["tiles"]):
            raise ValueError("City bake is missing a tile listed in its manifest")
        if TARGET.exists():
            raise SystemExit(f"City bake appeared during installation; preserving it: {TARGET}")
        os.replace(city, TARGET)

    print(f"Installed {len(tiles['tiles'])} city tiles at {TARGET} (SHA-256 {digest})")
    smooth_coast()


def smooth_coast() -> None:
    """The release ships the coast at survey detail; the map view wants it smoothed (needs uv, see city/README.md)."""
    if shutil.which("uv") is None:
        print(f"uv not found: run {CLEAN_COAST} later to smooth the citywide coastline")
        return
    result = subprocess.run(["uv", "run", "--with", "shapely", "python", str(CLEAN_COAST)])
    if result.returncode != 0:
        print(f"Coast smoothing failed: run {CLEAN_COAST} by hand once shapely is available")


if __name__ == "__main__":
    install()
