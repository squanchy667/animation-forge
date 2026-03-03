"""Phase 4 — Frame segmentation with motion-based auto-trim.

Slices nobg frames into per-animation directories based on animation_map.
Then auto-trims still/idle frames from the start and end of each animation
by comparing consecutive frames for pixel-level motion.
"""

import json
import shutil
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from utils.motion import frame_pose_signature

console = Console()


def auto_trim_animation(
    frames: list[Path],
    min_motion_frames: int = 3,
) -> tuple[int, int]:
    """Detect motion start and end by tracking character pose changes.

    Computes center-of-mass and bounding box for each frame, then identifies
    the transition from standing (stable pose) to action (shifting pose).
    Works reliably with AI-generated video where per-pixel diffs are noisy.

    Args:
        frames: Sorted list of frame paths.
        min_motion_frames: Require this many consecutive motion frames to confirm start.

    Returns:
        Tuple of (trim_start, trim_end) as 0-indexed indices into the frames list.
        The range frames[trim_start:trim_end+1] contains the actual motion.
    """
    if len(frames) < min_motion_frames + 4:
        return 0, len(frames) - 1

    # Compute pose signature for each frame
    signatures = [frame_pose_signature(f) for f in frames]

    # Compute pose change between consecutive frames
    # Track combined shift in center-of-mass + bbox height change
    pose_diffs = []
    for i in range(len(signatures) - 1):
        cx1, cy1, bh1 = signatures[i]
        cx2, cy2, bh2 = signatures[i + 1]
        # Weighted combination: horizontal shift matters most for walk/run,
        # vertical shift for jump, bbox height for crouch/stand transitions
        diff = abs(cx2 - cx1) * 2.0 + abs(cy2 - cy1) * 1.5 + abs(bh2 - bh1) * 1.0
        pose_diffs.append(diff)

    # Find threshold: use the median of all diffs as the motion baseline
    # Standing frames have lower pose changes, action frames have higher
    sorted_diffs = sorted(pose_diffs)
    median_diff = sorted_diffs[len(sorted_diffs) // 2]

    # Motion threshold: frames with pose change above 70% of median are "in motion"
    # This adapts to each animation's own motion intensity
    motion_threshold = median_diff * 0.7

    # Find motion start: first sustained run above threshold
    trim_start = 0
    for i in range(len(pose_diffs) - min_motion_frames + 1):
        window = pose_diffs[i:i + min_motion_frames]
        if all(d >= motion_threshold for d in window):
            trim_start = max(0, i - 1)
            break

    # Find motion end: last sustained run above threshold
    trim_end = len(frames) - 1
    for i in range(len(pose_diffs) - 1, min_motion_frames - 2, -1):
        window = pose_diffs[max(0, i - min_motion_frames + 1):i + 1]
        if all(d >= motion_threshold for d in window):
            trim_end = min(len(frames) - 1, i + 2)
            break

    return trim_start, trim_end


def _load_animation_types() -> dict[str, dict]:
    """Load animation type definitions keyed by ID."""
    config_path = Path(__file__).parent.parent / "config" / "animation_types.json"
    with open(config_path, "r", encoding="utf-8") as f:
        types = json.load(f)
    return {t["id"]: t for t in types}


def segment_animations(session: dict) -> dict[str, list[str]]:
    """Slice nobg frames into per-animation buckets with motion-based auto-trim.

    For each animation in animation_map:
    1. Copies the relevant frame range into a dedicated directory
    2. Runs auto-trim to detect and remove still/idle frames at start and end
    3. Re-numbers remaining frames starting from 0001

    Auto-trim can be disabled per-animation by setting "auto_trim": false
    in the animation_map entry, or globally via session["auto_trim"] = false.

    Args:
        session: Session config with animation_map and nobg frame paths.

    Returns:
        Dict mapping animation_id → list of segmented frame paths.
    """
    animation_map = session.get("animation_map", {})
    if not animation_map:
        console.print("  [yellow]No animations mapped — skipping segmentation[/yellow]")
        return {}

    global_auto_trim = session.get("auto_trim", True)
    anim_types = _load_animation_types()
    profile = session.get("game_profile", {})
    output_base = Path(session["output_dir"]) / "frames" / "animations"
    segments: dict[str, list[str]] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan][Phase 5/6][/bold cyan] Frame Segmentation"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("segment", total=len(animation_map))

        for anim_id, anim_info in animation_map.items():
            video_name = anim_info["video"]
            video_stem = Path(video_name).stem
            nobg_dir = Path(session["output_dir"]) / "frames" / "nobg" / video_stem

            frame_start = anim_info["frame_start"]
            frame_end = anim_info["frame_end"]

            # Get all nobg frames sorted
            all_frames = sorted(nobg_dir.glob("frame_*.png"))

            # Slice to animation range (0-indexed)
            anim_frames = all_frames[frame_start:frame_end + 1]
            original_count = len(anim_frames)

            # Auto-trim: detect and remove still frames at start/end
            should_trim = global_auto_trim and anim_info.get("auto_trim", True)
            if should_trim and len(anim_frames) > 6:
                trim_start, trim_end = auto_trim_animation(anim_frames)
                trimmed_frames = anim_frames[trim_start:trim_end + 1]

                trimmed_start = trim_start
                trimmed_end = original_count - 1 - trim_end

                if trimmed_start > 0 or trimmed_end > 0:
                    console.print(
                        f"  [cyan]Auto-trim {anim_id}:[/cyan] "
                        f"{original_count} → {len(trimmed_frames)} frames "
                        f"(cut {trimmed_start} start, {trimmed_end} end)"
                    )
                anim_frames = trimmed_frames

            # Create output directory (clean it first for re-runs)
            anim_dir = output_base / anim_id
            if anim_dir.exists():
                shutil.rmtree(anim_dir)
            anim_dir.mkdir(parents=True, exist_ok=True)

            # Copy and re-number (1-indexed, 4-digit padded)
            segmented = []
            for i, src in enumerate(anim_frames, 1):
                dst = anim_dir / f"frame_{i:04d}.png"
                shutil.copy2(str(src), str(dst))
                segmented.append(str(dst))

            segments[anim_id] = segmented

            # Validate frame count against profile-aware targets
            n = len(segmented)
            anim_def = anim_types.get(anim_id)
            if anim_def and anim_def.get("typical_frames"):
                if profile:
                    from utils.game_profile import get_frame_target
                    target_min, target_max = get_frame_target(profile, anim_def)
                else:
                    target_min, target_max = anim_def["typical_frames"]

                if n < target_min:
                    console.print(
                        f"  [yellow]Warning:[/yellow] '{anim_id}' has {n} frames "
                        f"(target minimum: {target_min})"
                    )
                elif n > target_max * 2:
                    console.print(
                        f"  [yellow]Warning:[/yellow] '{anim_id}' has {n} frames "
                        f"(target maximum: {target_max}, got 2x+)"
                    )

            progress.update(task, advance=1)

    console.print(f"  [green]Segmented {len(segments)} animations[/green]")
    for anim_id, frames in segments.items():
        console.print(f"    [dim]{anim_id}: {len(frames)} frames[/dim]")

    return segments
