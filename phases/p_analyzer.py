"""Frame Analyzer — post-segmentation validation using Vision AI and motion analysis.

For each segmented animation:
1. Validates frame count against game profile expectations
2. Computes motion consistency (pose signature tracking)
3. Checks transparency quality (alpha channel stats)
4. Optionally sends sample frames to Claude Vision for type verification

Gracefully degrades without Vision API — runs basic validation only.
"""

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from utils.game_profile import get_frame_target
from utils.motion import compute_motion_consistency, compute_transparency_quality

console = Console()


def _load_animation_types() -> dict[str, dict]:
    """Load animation type definitions keyed by ID."""
    config_path = Path(__file__).parent.parent / "config" / "animation_types.json"
    with open(config_path, "r", encoding="utf-8") as f:
        types = json.load(f)
    return {t["id"]: t for t in types}


def _get_sample_frames(anim_dir: Path, count: int = 5) -> list[str]:
    """Get evenly-spaced sample frames from an animation directory."""
    frames = sorted(anim_dir.glob("frame_*.png"))
    if not frames:
        return []

    n = len(frames)
    if n <= count:
        return [str(f) for f in frames]

    indices = [int(i * (n - 1) / (count - 1)) for i in range(count)]
    return [str(frames[idx]) for idx in sorted(set(indices))]


def _run_vision_analysis(
    frame_paths: list[str],
    declared_type: str,
) -> dict | None:
    """Run Claude Vision analysis on sample frames.

    Returns analysis dict or None if Vision is unavailable.
    """
    from utils.vision import analyze_animation_frames, get_vision_client

    client = get_vision_client()
    if client is None:
        return None

    return analyze_animation_frames(frame_paths, declared_type, client)


def _show_analysis_result(anim_id: str, result: dict) -> None:
    """Display analysis result for a single animation."""
    lines = []

    # Frame count
    fc = result.get("frame_count_check", {})
    if fc.get("status") == "ok":
        lines.append(f"  [green]Frames:[/green] {fc.get('actual', '?')} (target: {fc.get('target_min', '?')}-{fc.get('target_max', '?')})")
    elif fc.get("status") == "low":
        lines.append(f"  [yellow]Frames:[/yellow] {fc.get('actual', '?')} — below target minimum {fc.get('target_min', '?')}")
    elif fc.get("status") == "high":
        lines.append(f"  [yellow]Frames:[/yellow] {fc.get('actual', '?')} — above target maximum {fc.get('target_max', '?')}")

    # Motion consistency
    mc = result.get("motion_consistency", {})
    score = mc.get("motion_score", 0)
    if score >= 0.9:
        lines.append(f"  [green]Motion:[/green] smooth ({score:.0%})")
    elif score >= 0.7:
        lines.append(f"  [yellow]Motion:[/yellow] some anomalies ({score:.0%}, {mc.get('anomaly_count', 0)} jumps)")
    else:
        lines.append(f"  [red]Motion:[/red] inconsistent ({score:.0%}, {mc.get('anomaly_count', 0)} jumps)")

    # Transparency
    tq = result.get("transparency_quality", {})
    rating = tq.get("quality_rating", "unknown")
    if rating == "good":
        lines.append(f"  [green]Alpha:[/green] good ({tq.get('mean_opaque_ratio', 0):.0%} opaque)")
    elif rating in ("poor_too_transparent", "poor_too_opaque", "inconsistent"):
        lines.append(f"  [yellow]Alpha:[/yellow] {rating} ({tq.get('mean_opaque_ratio', 0):.0%} opaque)")
    else:
        lines.append(f"  [dim]Alpha:[/dim] {rating} ({tq.get('mean_opaque_ratio', 0):.0%} opaque)")

    # Vision analysis
    va = result.get("vision_analysis")
    if va:
        matches = va.get("matches_declared", True)
        if matches:
            lines.append(f"  [green]Vision:[/green] confirmed as {va.get('detected_type', '?')} ({va.get('confidence', '?')})")
        else:
            lines.append(
                f"  [red]Vision:[/red] detected {va.get('detected_type', '?')} "
                f"(declared: {result.get('declared_type', '?')}) — {va.get('description', '')}"
            )
        if va.get("quality_notes"):
            lines.append(f"  [dim]Notes: {va['quality_notes']}[/dim]")

    console.print(f"\n  [bold cyan]{anim_id}:[/bold cyan]")
    for line in lines:
        console.print(line)


def run_frame_analysis(session: dict) -> dict:
    """Run frame analysis on all segmented animations.

    Args:
        session: Session config with animation_map and segments.

    Returns:
        Updated session with analysis_results populated.
    """
    animation_map = session.get("animation_map", {})
    profile = session.get("game_profile", {})
    anim_types = _load_animation_types()
    anim_base = Path(session["output_dir"]) / "frames" / "animations"

    # Check Vision availability
    from utils.vision import is_vision_available
    has_vision = is_vision_available()

    if has_vision:
        console.print("  [green]Vision API available[/green] — running full analysis")
    else:
        console.print("  [dim]Vision API not available — running basic validation only[/dim]")

    analysis_results: dict[str, dict] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Frame Analysis[/bold cyan]"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("analyze", total=len(animation_map))

        for anim_id, anim_info in animation_map.items():
            anim_dir = anim_base / anim_id
            frames = sorted(anim_dir.glob("frame_*.png")) if anim_dir.exists() else []
            frame_paths = [str(f) for f in frames]

            result: dict = {
                "declared_type": anim_id,
                "frame_count": len(frames),
            }

            # 1. Frame count validation
            anim_def = anim_types.get(anim_id)
            if anim_def and profile:
                target_min, target_max = get_frame_target(profile, anim_def)
                actual = len(frames)
                if actual < target_min:
                    status = "low"
                elif actual > target_max * 2:
                    status = "high"
                else:
                    status = "ok"
                result["frame_count_check"] = {
                    "actual": actual,
                    "target_min": target_min,
                    "target_max": target_max,
                    "status": status,
                }
            elif anim_def:
                typical = anim_def.get("typical_frames", [6, 12])
                actual = len(frames)
                status = "ok"
                if actual < typical[0]:
                    status = "low"
                elif actual > typical[1] * 2:
                    status = "high"
                result["frame_count_check"] = {
                    "actual": actual,
                    "target_min": typical[0],
                    "target_max": typical[1],
                    "status": status,
                }

            # 2. Motion consistency
            if frame_paths:
                result["motion_consistency"] = compute_motion_consistency(frame_paths)

            # 3. Transparency quality
            if frame_paths:
                result["transparency_quality"] = compute_transparency_quality(frame_paths)

            # 4. Vision analysis (if available)
            if has_vision and frame_paths:
                sample_frames = _get_sample_frames(anim_dir)
                if sample_frames:
                    vision_result = _run_vision_analysis(sample_frames, anim_id)
                    if vision_result:
                        result["vision_analysis"] = vision_result

                        # Handle mismatch
                        if not vision_result.get("matches_declared", True):
                            _show_analysis_result(anim_id, result)
                            console.print(
                                f"\n  [bold yellow]Vision suggests this is "
                                f"'{vision_result.get('detected_type', '?')}' "
                                f"not '{anim_id}'[/bold yellow]"
                            )
                            if Confirm.ask("  Reclassify this animation?", default=False):
                                new_type = Prompt.ask(
                                    "  New animation type",
                                    default=vision_result.get("detected_type", anim_id),
                                )
                                result["reclassified_to"] = new_type

            analysis_results[anim_id] = result
            _show_analysis_result(anim_id, result)
            progress.update(task, advance=1)

    # Summary table
    console.print()
    _show_summary_table(analysis_results)

    session["analysis_results"] = analysis_results
    return session


def _show_summary_table(results: dict[str, dict]) -> None:
    """Display summary table of all analysis results."""
    table = Table(title="Analysis Summary", border_style="cyan")
    table.add_column("Animation", style="cyan")
    table.add_column("Frames", justify="right")
    table.add_column("Motion", justify="center")
    table.add_column("Alpha", justify="center")
    table.add_column("Vision", justify="center")

    for anim_id, result in results.items():
        frames = str(result.get("frame_count", "?"))

        mc = result.get("motion_consistency", {})
        score = mc.get("motion_score", 0)
        if score >= 0.9:
            motion = "[green]OK[/green]"
        elif score >= 0.7:
            motion = "[yellow]Fair[/yellow]"
        else:
            motion = "[red]Poor[/red]"

        tq = result.get("transparency_quality", {})
        rating = tq.get("quality_rating", "unknown")
        if rating == "good":
            alpha = "[green]OK[/green]"
        elif rating == "acceptable":
            alpha = "[dim]OK[/dim]"
        elif rating == "unknown":
            alpha = "[dim]—[/dim]"
        else:
            alpha = "[yellow]Issue[/yellow]"

        va = result.get("vision_analysis")
        if va is None:
            vision = "[dim]—[/dim]"
        elif va.get("matches_declared", True):
            vision = "[green]Match[/green]"
        else:
            vision = "[red]Mismatch[/red]"

        table.add_row(anim_id, frames, motion, alpha, vision)

    console.print(table)
