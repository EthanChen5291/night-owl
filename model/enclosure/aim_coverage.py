#!/usr/bin/env -S uv run --with matplotlib --with numpy python
"""Camera coverage vs hanger tilt for the NightOwl D3 node (side view).

Writes aim-coverage.png (1600x900) next to this file.

Geometry, all from the CAD in ~/div-hacks-26/enclosure and the IMX219 datasheet:
  * IMX219 full field of view 62.2 deg (wide axis) x 48.8 deg (narrow axis).
    HANDOFF-D3.md in Bruno's repo rounds this to 62 x 49; the datasheet value is used here.
  * In node_d3.scad the camera's 25 mm edge lies along y (cam_board = [25, 24], line 27),
    and the hanger tilts the box about y (hung(): rotate([0, a, 0]), line 212). The image's
    wide axis is parallel to that 25 mm edge, so it is parallel to the tilt axis: the axis
    that sweeps toward the far rail when you tilt is the NARROW 48.8 deg one.
  * Tilt 0 = sensor face straight down (hanger.scad line 22).

Run:  ./aim_coverage.py   (uv fetches matplotlib + numpy)
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle

FOV_WIDE, FOV_NARROW = 62.2, 48.8          # deg, IMX219 datasheet
HW, HN = FOV_WIDE / 2, FOV_NARROW / 2       # half angles

# palette (validated pair on white: CVD-safe, >= 3:1)
C0, C45 = "#2a78d6", "#eb6834"              # tilt 0 deg, tilt 45 deg
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
STRUCT = "#c3c2b7"
FONT = {"family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]}
plt.rcParams.update({"font.family": FONT["family"], "font.size": 11})


def tan(deg: float) -> float:
    return math.tan(math.radians(deg))


def floor_hit(h: float, ang_from_vertical: float) -> float:
    """Horizontal distance (same units as h) where a ray at ang from vertical meets the floor."""
    return h * tan(ang_from_vertical)


def coverage(h: float, tilt: float, half: float = HN) -> tuple[float, float]:
    """Near/far floor distance of the narrow-axis cone at a given tilt (deg from vertical)."""
    return floor_hit(h, tilt - half), floor_hit(h, tilt + half)


def draw_cone(ax, h, tilt, color, wall_x=None, reach=None, label_alpha=0.16):
    """Fill the cone from the camera at (0, h). Rays stop at the floor or at a vertical wall."""
    near, far = coverage(h, tilt)
    pts = [(0.0, h)]
    if wall_x is not None and far > wall_x:
        wall_y = h - wall_x / tan(tilt + HN)
        pts += [(near, 0.0), (wall_x, 0.0), (wall_x, wall_y)]
    else:
        pts += [(near, 0.0), (far, 0.0)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=color, edgecolor="none", alpha=label_alpha, zorder=1))
    for a in (tilt - HN, tilt + HN):
        x = floor_hit(h, a)
        y = 0.0
        if wall_x is not None and x > wall_x:
            x, y = wall_x, h - wall_x / tan(a)
        if reach is not None and x > reach:            # open-ground continuation, dashed
            ax.plot([0, reach], [h, h - reach / tan(a)], color=color, lw=1.6, zorder=3)
            ax.plot([reach, x], [h - reach / tan(a), y], color=color, lw=1.2, ls=(0, (3, 3)), zorder=3)
        else:
            ax.plot([0, x], [h, y], color=color, lw=1.6, zorder=3)
    # centre ray
    xc, yc = floor_hit(h, tilt), 0.0
    if wall_x is not None and xc > wall_x:
        xc, yc = wall_x, h - wall_x / tan(tilt)
    ax.plot([0, xc], [h, yc], color=color, lw=0.9, ls=(0, (1, 2)), zorder=3)
    return near, far


def node_box(ax, h, tilt, color, L=9.5, H=4.9):
    """Small side-view outline of the D3 box (95.2 x 48.8 mm), pivot at mid-height of the box."""
    # box sits face-down with its face at y = h; pivot at box centre (x=0, y=h+H/2)
    cx, cy = 0.0, h + H / 2
    corners = [(-L / 2, -H / 2), (L / 2, -H / 2), (L / 2, H / 2), (-L / 2, H / 2)]
    t = math.radians(-tilt)
    rot = [(cx + x * math.cos(t) - y * math.sin(t), cy + x * math.sin(t) + y * math.cos(t)) for x, y in corners]
    ax.add_patch(Polygon(rot, closed=True, facecolor="white", edgecolor=color, lw=1.4, zorder=4))
    # sensor face highlight (the frosted band edge)
    (x0, y0), (x1, y1) = rot[0], rot[1]
    ax.plot([x0, x1], [y0, y1], color=color, lw=3, zorder=5, solid_capstyle="butt")


def bar(ax, y, x0, x1, color, text, text_y=None, ha="center", tx=None, end_dy=1.6, end_labels=None):
    ax.plot([x0, x1], [y, y], color=color, lw=5, solid_capstyle="butt", zorder=4)
    for x in (x0, x1):
        ax.plot([x, x], [y - 0.9, y + 0.9], color=color, lw=1.4, zorder=4)
    for x, lab, h in zip((x0, x1), end_labels or (f"{x0:.0f}", f"{x1:.0f}"), ("right", "left")):
        ax.text(x, y + end_dy, lab, ha=h, va="bottom", color=INK2, fontsize=9, zorder=6)
    ax.text(tx if tx is not None else (x0 + x1) / 2, text_y if text_y is not None else y,
            text, ha=ha, va="center", color=INK, fontsize=10.5, zorder=6,
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.9))


def panel_guard(ax):
    H = 60.0                      # camera face above the pit, cm
    RAIL_FAR = 127.0              # far rail of the tree guard, cm from the camera's nadir
    # structure: pit floor, two guard posts and the rail
    ax.axhline(0, color=STRUCT, lw=2, zorder=2)
    for x in (-10, RAIL_FAR):
        ax.plot([x, x], [0, H], color=STRUCT, lw=2.5, zorder=2)
    ax.plot([-10, RAIL_FAR], [H, H], color=STRUCT, lw=2.5, zorder=2)
    ax.plot([-10, 0], [H, H], color=INK2, lw=4, zorder=2)          # arm reaching from the rail
    # tree trunk, faint (it occludes part of the strip; not measured)
    ax.add_patch(Rectangle((55, 0), 8, H + 8, facecolor=GRID, edgecolor="none", zorder=0))
    ax.text(59, H + 9.5, "trunk", ha="center", color=MUTED, fontsize=9)

    n0, f0 = draw_cone(ax, H, 0, C0)
    n45, f45 = draw_cone(ax, H, 45, C45, wall_x=RAIL_FAR, reach=RAIL_FAR)
    # open-ground far edge of the 45 deg cone, dashed past the rail
    ax.plot([RAIL_FAR, f45], [0, 0], color=C45, lw=1.2, ls=(0, (3, 3)), zorder=3)
    post_h = H - RAIL_FAR / tan(45 + HN)

    node_box(ax, H, 0, C0)
    node_box(ax, H, 45, C45)

    w0 = 2 * H * tan(HW)
    bar(ax, -5, n0, f0, C0, f"0°: {f0 - n0:.0f} cm along the tilt axis x {w0:.0f} cm across\n(README quotes ~50 x 67, which needs a ~45° x 58° effective FOV)",
        text_y=-14, ha="left", tx=n0 - 2, end_dy=1.8, end_labels=(f"{n0:.0f}", f"+{f0:.0f}"))
    bar(ax, -22, n45, RAIL_FAR, C45, f"45°: floor from {n45:.0f} cm out to the far rail at {RAIL_FAR:.0f} cm ({RAIL_FAR - n45:.0f} cm strip)\n+ the bottom {post_h:.0f} cm of the far post; on open ground the edge lands at {f45:.0f} cm",
        text_y=-31, end_dy=1.8)
    ax.annotate(f"far ray hits the post\n{post_h:.0f} cm up", xy=(RAIL_FAR, post_h), xytext=(96, 30),
                color=INK2, fontsize=9.5, ha="center",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.text(-8, H + 2.5, f"camera face {H:.0f} cm\nabove the pit", ha="right", va="bottom", color=INK2, fontsize=9.5)
    ax.text(RAIL_FAR + 2, H + 1.5, "far rail", color=MUTED, fontsize=9)
    ax.text(f45 + 2, 1.5, f"{f45:.0f}", color=C45, fontsize=9, va="bottom")
    ax.set_xlim(-40, 175); ax.set_ylim(-36, 78)
    ax.set_title("(a) Real tree guard: 60 cm rail, camera 60 cm over the pit", loc="left", fontsize=13, color=INK, pad=10)


def panel_diorama(ax):
    H = 25.0                     # faceplate above the diorama floor, cm
    WALL = 35.0                  # far wall distance from the camera's nadir (assumed; reproduces the README's 12 cm)
    ax.axhline(0, color=STRUCT, lw=2, zorder=2)
    ax.plot([WALL, WALL], [0, 30], color=STRUCT, lw=2.5, zorder=2)
    ax.plot([-12, 0], [H + 4.9, H + 4.9], color=INK2, lw=4, zorder=2)   # arm from the diorama roof/edge
    ax.plot([-12, -12], [0, H + 6], color=STRUCT, lw=2.5, zorder=2)

    n0, f0 = draw_cone(ax, H, 0, C0)
    n45, f45 = draw_cone(ax, H, 45, C45, wall_x=WALL)
    wall_h = H - WALL / tan(45 + HN)

    node_box(ax, H, 0, C0)
    node_box(ax, H, 45, C45)

    w0 = 2 * H * tan(HW)
    bar(ax, -2.2, n0, f0, C0, f"0°: {f0 - n0:.0f} cm of floor (x {w0:.0f} cm across); README says 22", text_y=-6,
        end_dy=0.8, end_labels=(f"{n0:.0f}", f"+{f0:.0f}"))
    bar(ax, -10.5, n45, WALL, C45, f"45°: floor from {n45:.0f} cm to the wall at {WALL:.0f} cm ({WALL - n45:.0f} cm)\n+ {wall_h:.0f} cm of the far wall (README: ~12 cm)", text_y=-15, end_dy=0.8)
    ax.plot([WALL + 1.2, WALL + 1.2], [0, wall_h], color=C45, lw=5, solid_capstyle="butt", zorder=4)
    ax.text(WALL + 2.4, wall_h / 2, f"{wall_h:.0f} cm\nup the wall", color=INK, fontsize=10, va="center")
    ax.text(-13, H + 7.5, f"faceplate {H:.0f} cm\nabove the floor", ha="right", va="bottom", color=INK2, fontsize=9.5)
    ax.text(WALL, 31, "far wall (assumed 35 cm away)", ha="center", va="bottom", color=MUTED, fontsize=9)
    ax.set_xlim(-24, 52); ax.set_ylim(-18.5, 36)
    ax.set_title("(b) Diorama: faceplate 25 cm above the floor", loc="left", fontsize=13, color=INK, pad=10)


def main() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 9), dpi=100, gridspec_kw={"width_ratios": [1.45, 1]})
    fig.patch.set_facecolor("white")
    for ax in axes:
        ax.set_facecolor("white")
        ax.set_aspect("equal")
        for s in ("top", "right", "left", "bottom"):
            ax.spines[s].set_visible(False)
        ax.set_yticks([])
        ax.tick_params(axis="x", colors=MUTED, length=0, labelsize=9.5)
        ax.grid(axis="x", color=GRID, lw=0.8, zorder=0)
        ax.set_xlabel("horizontal distance from the camera's nadir, cm", color=MUTED, fontsize=10)
    panel_guard(axes[0]); axes[0].set_xticks(range(-25, 176, 25))
    panel_diorama(axes[1]); axes[1].set_xticks(range(-10, 51, 10))

    # legend by colour + text (identity never colour-alone: every bar is labelled)
    fig.text(0.5, 0.945, "NightOwl node: camera coverage vs hanger tilt (side view, tilt swings the 48.8° axis)",
             ha="center", fontsize=16, color=INK, weight="bold")
    fig.text(0.5, 0.905,
             "IMX219 full FOV 62.2° x 48.8° (datasheet; HANDOFF-D3 rounds to 62° x 49°). The camera's 25 mm edge lies along the hanger's pivot axis, "
             "so tilting sweeps the narrow 48.8° axis toward the far rail. Tilt steps: 0-90° every 15° (hanger.scad `angles`).",
             ha="center", fontsize=10, color=INK2)
    fig.text(0.5, 0.045,
             "Blue = tilt 0° (straight down, pin hole 0).  Orange = tilt 45° (pin hole 45).  Solid rays stop at the floor or the far post/wall; dashed = continuation on open ground.\n"
             "Footprints are geometric (pinhole model, no lens distortion); the trunk and any guard bars occlude part of the strip.",
             ha="center", va="center", fontsize=9.5, color=MUTED, linespacing=1.6)
    fig.subplots_adjust(left=0.03, right=0.985, top=0.87, bottom=0.12, wspace=0.06)
    out = Path(__file__).with_name("aim-coverage.png")
    fig.savefig(out, dpi=100, facecolor="white")
    print(f"wrote {out} ({int(fig.get_figwidth()*100)}x{int(fig.get_figheight()*100)})")
    # numbers, for the notes
    for h, tilt, wall in ((60, 0, None), (60, 45, 127), (25, 0, None), (25, 45, 35)):
        n, f = coverage(h, tilt)
        extra = "" if wall is None or f <= wall else f"; wall/post at {wall} cm lit {h - wall / tan(tilt + HN):.1f} cm up"
        print(f"h={h} tilt={tilt:2d}: narrow-axis floor {n:6.1f} -> {f:6.1f} cm (len {f - n:5.1f}); wide axis at nadir {2*h*tan(HW):.1f} cm{extra}")


if __name__ == "__main__":
    main()
