"""Phase 4 — Frame segmentation.

Slices nobg frames into per-animation directories based on animation_map.
"""

import json
import shutil
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console()


def _load_animation_types() -> dict[str, dict]:
    """Load animation type definitions keyed by ID."""
    config_path = Path(__file__).parent.parent / "config" / "animation_types.json"
    with open(config_path, "r", encoding="utf-8") as f:
        types = json.load(f)
    return {t["id"]: t for t in types}


def segment_animations(session: dict) -> dict[str, list[str]]:
    """Slice nobg frames into per-animation buckets.

    For each animation in animation_map, copies the relevant frame range
    into a dedicated directory with re-numbered filenames starting from 0001.

    Args:
        session: Session config with animation_map and nobg frame paths.

    Returns:
        Dict mapping animation_id → list of segmented frame paths.
    """
    animation_map = session.get("animation_map", {})
    if not animation_map:
        console.print("  [yellow]No animations mapped — skipping segmentation[/yellow]")
        return {}

    anim_types = _load_animation_types()
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

            # Create output directory
            anim_dir = output_base / anim_id
            anim_dir.mkdir(parents=True, exist_ok=True)

            # Copy and re-number (1-indexed, 4-digit padded)
            segmented = []
            for i, src in enumerate(anim_frames, 1):
                dst = anim_dir / f"frame_{i:04d}.png"
                shutil.copy2(str(src), str(dst))
                segmented.append(str(dst))

            segments[anim_id] = segmented

            # Validate frame count against typical_frames
            n = len(segmented)
            anim_def = anim_types.get(anim_id)
            if anim_def and anim_def.get("typical_frames"):
                typical_min, typical_max = anim_def["typical_frames"]
                if n < typical_min:
                    console.print(
                        f"  [yellow]Warning:[/yellow] '{anim_id}' has {n} frames "
                        f"(typical minimum: {typical_min})"
                    )
                elif n > typical_max * 2:
                    console.print(
                        f"  [yellow]Warning:[/yellow] '{anim_id}' has {n} frames "
                        f"(typical maximum: {typical_max}, got 2x+)"
                    )

            progress.update(task, advance=1)

    console.print(f"  [green]Segmented {len(segments)} animations[/green]")
    for anim_id, frames in segments.items():
        console.print(f"    [dim]{anim_id}: {len(frames)} frames[/dim]")

    return segments
