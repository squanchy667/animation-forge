"""Phase 9 — Game Refinement: motion-aware keypose selection, global bbox normalization,
per-animation cleanup, and game-appropriate frame counts.

Auto-activates for 2d_platformer and 2d_roguelite game types.
Loads per-animation config from config/refinement_profiles/{profile_name}.json.
"""

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console()

# Default fallback config for animations not listed in the profile
DEFAULT_ANIM_CONFIG = {
    "target_frames": 6,
    "action_start": 3,
    "action_end": 50,
    "loop": False,
    "white_kill": [30, 200],
    "alpha_thresh": 80,
    "trim_pct": 0.05,
}


# ── Image Processing ───────────────────────────────────────────────────────


def _kill_white_smoke(img: Image.Image, sat_thresh: int, val_thresh: int) -> Image.Image:
    """Remove white/grey smoke artifacts via saturation + value thresholds."""
    arr = np.array(img)
    if arr.shape[2] != 4:
        return img
    alpha = arr[:, :, 3]
    visible = alpha > 10
    r, g, b = arr[:, :, 0].astype(float), arr[:, :, 1].astype(float), arr[:, :, 2].astype(float)
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin
    with np.errstate(divide="ignore", invalid="ignore"):
        sat = np.where(cmax > 0, (delta / cmax) * 255, 0).astype(np.uint8)
    val = cmax.astype(np.uint8)
    is_white = visible & (sat < sat_thresh) & (val > val_thresh)
    arr[:, :, 3] = np.where(is_white, 0, alpha)
    return Image.fromarray(arr)


def _clean_alpha(img: Image.Image, threshold: int) -> Image.Image:
    """Binary alpha threshold — alpha > threshold → 255, else → 0."""
    arr = np.array(img)
    if arr.shape[2] == 4:
        alpha = arr[:, :, 3]
        arr[:, :, 3] = np.where(alpha > threshold, 255, 0).astype(np.uint8)
    return Image.fromarray(arr)


def _normalize_frame(img: Image.Image, norm_w: int, norm_h: int) -> Image.Image:
    """Resize source frame to standard resolution so all frames are at the same scale."""
    if img.size == (norm_w, norm_h):
        return img
    src_w, src_h = img.size
    scale = min(norm_w / src_w, norm_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img_scaled = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (norm_w, norm_h), (0, 0, 0, 0))
    ox = (norm_w - new_w) // 2
    oy = norm_h - new_h  # Bottom-align
    canvas.paste(img_scaled, (ox, oy))
    return canvas


def _crop_to_global_bbox(
    img: Image.Image, global_bbox: tuple[int, int, int, int], extra_pct: float
) -> Image.Image:
    """Crop using global bounding box so all characters are same scale."""
    gx0, gy0, gx1, gy1 = global_bbox
    gw = gx1 - gx0
    ex = int(gw * extra_pct)
    cx0 = max(0, gx0 + ex)
    cx1 = min(img.width, gx1 - ex)
    cy0 = max(0, gy0)
    cy1 = min(img.height, gy1)
    if cx1 <= cx0 or cy1 <= cy0:
        return img
    return img.crop((cx0, cy0, cx1, cy1))


def _resize_sharp(img: Image.Image, w: int, h: int) -> Image.Image:
    """Resize to target canvas, bottom-aligned, with sharpening."""
    img.thumbnail((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    offset_x = (w - img.width) // 2
    offset_y = h - img.height  # Bottom-align
    canvas.paste(img, (offset_x, offset_y))
    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=1, percent=40, threshold=2))
    return canvas


# ── Frame Selection ────────────────────────────────────────────────────────


def _frame_motion_score(fp1: Path, fp2: Path) -> float:
    """Compute motion difference between two frames using alpha channel geometry."""
    def sig(fp: Path) -> tuple[float, float, float, float]:
        img = Image.open(fp).convert("RGBA")
        arr = np.array(img)[:, :, 3]
        ys, xs = np.where(arr > 128)
        if len(xs) == 0:
            return (0.5, 0.5, 0, 0)
        h, w = arr.shape
        return (xs.mean() / w, ys.mean() / h, (xs.max() - xs.min()) / w, (ys.max() - ys.min()) / h)

    s1, s2 = sig(fp1), sig(fp2)
    return (abs(s1[0] - s2[0]) * 2.0 + abs(s1[1] - s2[1]) * 1.5
            + abs(s1[2] - s2[2]) + abs(s1[3] - s2[3]))


def _select_action_frames(all_frames: list[Path], config: dict) -> list[Path]:
    """Select frames with maximum motion variety from the action core.

    Uses keypose selection: greedily pick frames at motion milestones,
    ensuring every frame shows distinct motion.
    """
    start = config.get("action_start", 1) - 1  # Convert to 0-indexed
    end = config.get("action_end") or len(all_frames)
    end = min(end, len(all_frames))
    target = config["target_frames"]

    subset = all_frames[start:end]
    if len(subset) <= target:
        return subset

    # Compute motion scores between consecutive frames
    motion_scores = []
    for i in range(len(subset) - 1):
        score = _frame_motion_score(subset[i], subset[i + 1])
        motion_scores.append(score)

    # Cumulative motion — pick frames at evenly-spaced motion milestones
    cum_motion = [0.0]
    for s in motion_scores:
        cum_motion.append(cum_motion[-1] + s)
    total_motion = cum_motion[-1]

    if total_motion < 0.001:
        # No motion detected, fall back to even subsample
        indices = [int(i * (len(subset) - 1) / (target - 1)) for i in range(target)]
        return [subset[i] for i in indices]

    # Pick frames at evenly-spaced motion milestones
    selected_indices: list[int] = []
    for t in range(target):
        target_motion = t * total_motion / (target - 1)
        best_idx = 0
        best_dist = float("inf")
        for i, cm in enumerate(cum_motion):
            dist = abs(cm - target_motion)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        if best_idx not in selected_indices:
            selected_indices.append(best_idx)
        else:
            for offset in range(1, len(subset)):
                for candidate in [best_idx + offset, best_idx - offset]:
                    if 0 <= candidate < len(subset) and candidate not in selected_indices:
                        selected_indices.append(candidate)
                        break
                if len(selected_indices) > len(selected_indices) - 1:
                    break

    selected_indices.sort()
    return [subset[i] for i in selected_indices[:target]]


# ── Global Bounding Box ──────────────────────────────────────────────────


def _compute_global_bbox(
    anim_configs: dict[str, dict],
    nobg_dir: Path,
    norm_w: int,
    norm_h: int,
) -> tuple[int, int, int, int]:
    """Scan ALL source frames across ALL animations to find global character bbox.

    All frames are normalized to the same resolution first.
    """
    global_x0, global_y0, global_x1, global_y1 = 9999, 9999, 0, 0

    for anim_id, config in anim_configs.items():
        src_dir = nobg_dir / config["source_dir"]
        if not src_dir.exists():
            continue
        frames = sorted(src_dir.glob("frame_*.png"))
        if not frames:
            continue

        # Sample evenly (don't need every frame)
        step = max(1, len(frames) // 10)
        for fp in frames[::step]:
            img = _normalize_frame(Image.open(fp).convert("RGBA"), norm_w, norm_h)
            wk = config.get("white_kill")
            if wk:
                img = _kill_white_smoke(img, wk[0], wk[1])
            img = _clean_alpha(img, config.get("alpha_thresh", 80))
            bbox = img.getbbox()
            if not bbox:
                continue
            x0, y0, x1, y1 = bbox
            global_x0 = min(global_x0, x0)
            global_y0 = min(global_y0, y0)
            global_x1 = max(global_x1, x1)
            global_y1 = max(global_y1, y1)

    console.print(
        f"  [dim]Global bbox: x:{global_x0}-{global_x1} y:{global_y0}-{global_y1} "
        f"({global_x1 - global_x0}x{global_y1 - global_y0})[/dim]"
    )
    return (global_x0, global_y0, global_x1, global_y1)


# ── Animation Category ───────────────────────────────────────────────────


def _category(anim_id: str) -> str:
    if anim_id in ("idle", "walk", "run", "jump", "fall", "land", "dash"):
        return "locomotion"
    if anim_id in ("attack_1", "attack_2", "block", "guard", "hurt", "death"):
        return "combat"
    return "utility"


# ── Profile Loading ──────────────────────────────────────────────────────


def _load_refinement_profile(profile_name: str) -> dict:
    """Load a refinement profile from config/refinement_profiles/{name}.json."""
    profile_path = Path(__file__).parent.parent / "config" / "refinement_profiles" / f"{profile_name}.json"
    if not profile_path.exists():
        console.print(f"  [yellow]Refinement profile not found: {profile_path}[/yellow]")
        return {}
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_anim_configs(
    animation_map: dict, refinement_profile: dict
) -> dict[str, dict]:
    """Build per-animation configs by merging refinement profile with animation_map.

    Maps each animation_id to its nobg source directory and refinement settings.
    """
    profile_anims = refinement_profile.get("animations", {})
    configs: dict[str, dict] = {}

    for anim_id, anim_info in animation_map.items():
        # Determine source directory from animation_map
        video_name = anim_info.get("video", "")
        source_dir = Path(video_name).stem

        # Get per-animation config from profile, or use defaults
        if anim_id in profile_anims:
            anim_cfg = {**DEFAULT_ANIM_CONFIG, **profile_anims[anim_id]}
        else:
            anim_cfg = {**DEFAULT_ANIM_CONFIG}
            # Inherit loop flag from animation_map
            anim_cfg["loop"] = anim_info.get("loop", False)

        anim_cfg["source_dir"] = source_dir
        configs[anim_id] = anim_cfg

    return configs


# ── Main Phase Entry Point ───────────────────────────────────────────────


def run_refinement(session: dict) -> dict:
    """Run game refinement phase — Phase 9.

    Inputs from session:
    - output_dir, character_name, animation_map, game_profile

    Outputs stored in session:
    - refined_frames: {anim_id: {frame_count, loop, category, frames_dir}}
    - global_bbox: cached for re-runs
    """
    output_dir = Path(session["output_dir"])
    character = session["character_name"]
    animation_map = session.get("animation_map", {})
    game_profile = session.get("game_profile", {}) or {}

    if not animation_map:
        console.print("  [yellow]No animations mapped — skipping refinement[/yellow]")
        return session

    # Load refinement profile
    profile_name = game_profile.get("refinement_profile")
    if not profile_name:
        console.print("  [dim]No refinement profile configured — skipping[/dim]")
        return session

    refinement_profile = _load_refinement_profile(profile_name)
    if not refinement_profile:
        return session

    # Canvas and normalization settings from profile
    canvas = refinement_profile.get("canvas", {"width": 128, "height": 256})
    target_w = canvas["width"]
    target_h = canvas["height"]
    norm_res = refinement_profile.get("normalize_resolution", {"width": 784, "height": 1168})
    norm_w = norm_res["width"]
    norm_h = norm_res["height"]

    nobg_dir = output_dir / "frames" / "nobg"
    refined_base = output_dir / "frames" / "refined"

    # Clean previous refined output
    if refined_base.exists():
        shutil.rmtree(refined_base)

    # Build per-animation configs
    anim_configs = _build_anim_configs(animation_map, refinement_profile)

    console.print(f"  [dim]Profile: {profile_name} | Canvas: {target_w}x{target_h} | "
                  f"Normalize: {norm_w}x{norm_h}[/dim]")

    # Pass 1: compute global character bounding box
    console.print("  Computing global character bounding box...")
    global_bbox = _compute_global_bbox(anim_configs, nobg_dir, norm_w, norm_h)

    # Pass 2: process each animation
    refined_frames: dict[str, dict] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan][Phase 9][/bold cyan] Game Refinement"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("refine", total=len(anim_configs))

        for anim_id, config in anim_configs.items():
            src_dir = nobg_dir / config["source_dir"]
            if not src_dir.exists():
                console.print(f"  [yellow]Warning:[/yellow] No source dir for '{anim_id}' "
                              f"(expected {src_dir.name}) — skipping")
                progress.update(task, advance=1)
                continue

            all_frames = sorted(src_dir.glob("frame_*.png"))
            if not all_frames:
                console.print(f"  [yellow]Warning:[/yellow] No frames in {src_dir.name} — skipping")
                progress.update(task, advance=1)
                continue

            # Select action frames with motion-aware keypose selection
            selected = _select_action_frames(all_frames, config)
            if not selected:
                progress.update(task, advance=1)
                continue

            # Process each frame
            wk = config.get("white_kill")
            alpha_t = config.get("alpha_thresh", 80)
            trim_pct = config.get("trim_pct", 0.05)

            processed = []
            for fp in selected:
                img = Image.open(fp).convert("RGBA")
                img = _normalize_frame(img, norm_w, norm_h)
                if wk:
                    img = _kill_white_smoke(img, wk[0], wk[1])
                img = _clean_alpha(img, alpha_t)
                img = _crop_to_global_bbox(img, global_bbox, trim_pct)
                img = _resize_sharp(img, target_w, target_h)
                img = _clean_alpha(img, alpha_t)  # Final pass after resize
                processed.append(img)

            # Save refined frames
            dst_dir = refined_base / anim_id
            dst_dir.mkdir(parents=True, exist_ok=True)

            for i, img in enumerate(processed, 1):
                out_path = dst_dir / f"frame_{i:04d}.png"
                img.save(out_path)

            loop = config.get("loop", False)
            refined_frames[anim_id] = {
                "frame_count": len(processed),
                "loop": loop,
                "category": _category(anim_id),
                "frames_dir": str(dst_dir),
            }

            console.print(
                f"  {anim_id:15s}: {len(all_frames):3d} → {len(processed):2d} frames "
                f"({'loop' if loop else 'shot'}) [from {config['source_dir']}]"
            )
            progress.update(task, advance=1)

    session["refined_frames"] = refined_frames
    session["global_bbox"] = list(global_bbox)
    session["refinement_canvas"] = {"width": target_w, "height": target_h}

    total_frames = sum(r["frame_count"] for r in refined_frames.values())
    console.print(f"  [green]Refined {len(refined_frames)} animations ({total_frames} total frames)[/green]")

    return session
