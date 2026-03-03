"""Phase 1 — Interactive questionnaire.

Maps each video to animation type(s) via terminal Q&A with Vision-assisted defaults.
Profile-aware: uses game_profile for default FPS, frame budget guidance, etc.
"""

import json
import re
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from utils.session import save_session

console = Console()


def _load_animation_types() -> list[dict]:
    """Load animation type definitions from config."""
    config_path = Path(__file__).parent.parent / "config" / "animation_types.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _guess_animation_from_vision(description: str | None, anim_types: list[dict]) -> str | None:
    """Try to extract an animation type from a Vision description."""
    if not description:
        return None
    desc_lower = description.lower()
    for anim in anim_types:
        if anim["id"] in desc_lower:
            return anim["id"]
    # Common aliases
    aliases = {
        "walking": "walk", "running": "run", "jumping": "jump",
        "falling": "fall", "landing": "land", "attacking": "attack_1",
        "slashing": "attack_1", "punching": "attack_1", "blocking": "block",
        "dashing": "dash", "dodging": "dash", "standing": "idle",
        "breathing": "idle", "dying": "death", "flinching": "hurt",
    }
    for keyword, anim_id in aliases.items():
        if keyword in desc_lower:
            return anim_id
    return None


def _try_vision_suggest(video_info: dict) -> str | None:
    """Try to get a Vision-based animation type suggestion."""
    frames = video_info.get("sampled_frames", [])
    if not frames:
        return None

    try:
        from utils.vision import get_vision_client, suggest_animation_type
        client = get_vision_client()
        if client:
            return suggest_animation_type(frames, client)
    except Exception:
        pass
    return None


def _show_animation_list(anim_types: list[dict], profile: dict | None = None) -> None:
    """Display numbered list of animation types with frame budget guidance."""
    table = Table(title="Animation Types", border_style="cyan", show_lines=False)
    table.add_column("#", style="bold", width=4)
    table.add_column("ID", style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("Loop", justify="center")
    table.add_column("Frames", justify="right")
    table.add_column("Description")

    for i, anim in enumerate(anim_types, 1):
        loop_str = "[green]✓[/green]" if anim["loop"] else "[dim]—[/dim]"

        # Show frame range, adjusted by profile budget if available
        typical = anim.get("typical_frames", [6, 12])
        if profile:
            from utils.game_profile import get_frame_target
            target_min, target_max = get_frame_target(profile, anim)
            frames_str = f"{target_min}-{target_max}"
        else:
            frames_str = f"{typical[0]}-{typical[1]}"

        table.add_row(str(i), anim["id"], anim["category"], loop_str, frames_str, anim["description"])

    console.print(table)


def _parse_frame_ranges(raw: str) -> dict[str, tuple[int, int]]:
    """Parse frame range input like 'walk=0-24, attack_1=25-60'.

    Returns:
        Dict mapping animation_id → (start, end).
    """
    ranges = {}
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        match = re.match(r"(\w+)\s*=\s*(\d+)\s*-\s*(\d+)", part)
        if match:
            anim_id = match.group(1)
            start = int(match.group(2))
            end = int(match.group(3))
            ranges[anim_id] = (start, end)
        else:
            console.print(f"  [yellow]Could not parse: '{part}' — expected format: name=start-end[/yellow]")
    return ranges


def _show_animation_map(animation_map: dict) -> None:
    """Display current animation_map as a Rich table."""
    if not animation_map:
        return

    table = Table(title="Animation Map", border_style="green")
    table.add_column("Animation", style="cyan")
    table.add_column("Video")
    table.add_column("Frames", justify="right")
    table.add_column("FPS", justify="right")
    table.add_column("Loop", justify="center")
    table.add_column("Trim", justify="center")

    for anim_id, info in animation_map.items():
        loop_str = "[green]✓[/green]" if info.get("loop") else "[dim]—[/dim]"
        trim_str = "[green]✓[/green]" if info.get("auto_trim", True) else "[dim]—[/dim]"
        frames = f"{info['frame_start']}-{info['frame_end']}"
        table.add_row(anim_id, info["video"], frames, str(info.get("fps", "?")), loop_str, trim_str)

    console.print(table)


def _ask_per_animation_config(
    anim_id: str,
    anim_def: dict,
    video_fps: int,
    profile: dict | None,
) -> dict:
    """Ask per-animation configuration: FPS, loop, auto-trim overrides.

    Returns:
        Dict with fps, loop, auto_trim keys.
    """
    # Default FPS from profile or video
    default_fps = profile.get("playback_fps", 12) if profile else video_fps
    default_loop = anim_def.get("loop", False)

    console.print(f"\n  [bold]Per-animation config for [cyan]{anim_id}[/cyan]:[/bold]")

    # FPS override
    fps_str = Prompt.ask(
        f"    Playback FPS",
        default=str(default_fps),
    )
    try:
        fps = int(fps_str)
    except ValueError:
        fps = default_fps

    # Loop override
    loop = Confirm.ask(
        f"    Looping animation?",
        default=default_loop,
    )

    # Auto-trim
    auto_trim = Confirm.ask(
        f"    Enable auto-trim (remove still frames)?",
        default=True,
    )

    return {"fps": fps, "loop": loop, "auto_trim": auto_trim}


def run_questionnaire(session: dict) -> dict:
    """Run interactive questionnaire to map videos to animations.

    Uses game_profile for intelligent defaults when available.

    Args:
        session: Session config with videos already probed.

    Returns:
        Updated session with animation_map populated.
    """
    anim_types = _load_animation_types()
    anim_by_id = {a["id"]: a for a in anim_types}
    profile = session.get("game_profile", {}) or {}

    # Q1: Character name
    default_name = session.get("character_name", "character")
    character_name = Prompt.ask(
        "[bold]Character name[/bold]",
        default=default_name,
    )
    session["character_name"] = character_name

    animation_map = session.get("animation_map", {})
    session_path = Path(session["output_dir"]) / "session_config.json"

    for video_name, video_info in session["videos"].items():
        console.print(f"\n[bold magenta]── {video_name} ──[/bold magenta]")
        console.print(f"  [dim]Resolution:[/dim] {video_info['width']}x{video_info['height']}")
        console.print(f"  [dim]Duration:[/dim] {video_info['duration']:.1f}s  |  "
                      f"[dim]FPS:[/dim] {video_info['fps']}  |  "
                      f"[dim]Frames:[/dim] {video_info['total_frames']}")

        # Show sampled frame paths
        if video_info.get("sampled_frames"):
            console.print("  [dim]Samples:[/dim]")
            for fp in video_info["sampled_frames"]:
                console.print(f"    [dim]{fp}[/dim]")

        # Vision description — show prominently in a panel
        vision_desc = video_info.get("vision_description")
        if vision_desc:
            console.print(Panel(
                f"[italic]{vision_desc}[/italic]",
                title="[bold blue]Vision Analysis[/bold blue]",
                border_style="blue",
                padding=(0, 2),
            ))

        # Try Vision suggestion for animation type
        vision_guess = _guess_animation_from_vision(vision_desc, anim_types)
        if not vision_guess:
            vision_guess = _try_vision_suggest(video_info)

        # Q2: Single or multiple animations?
        multi = Prompt.ask(
            "  Does this video contain [bold]one[/bold] or [bold]multiple[/bold] animations?",
            choices=["one", "multiple"],
            default="one",
        )

        if multi == "multiple":
            # Multiple animations — user provides frame ranges
            _show_animation_list(anim_types, profile)
            console.print(f"\n  Total frames: {video_info['total_frames']} (0-indexed: 0-{video_info['total_frames'] - 1})")

            # Show frame budget guidance if profile is set
            if profile and profile.get("frame_budget"):
                budget = profile["frame_budget"]
                console.print(f"  [dim]Frame budget: {budget} — frame targets adjusted accordingly[/dim]")

            raw = Prompt.ask(
                "  Enter frame ranges (e.g. [cyan]walk=0-24, attack_1=25-60[/cyan])"
            )
            ranges = _parse_frame_ranges(raw)

            for anim_id, (start, end) in ranges.items():
                anim_def = anim_by_id.get(anim_id, {})

                # Per-animation config
                config = _ask_per_animation_config(
                    anim_id, anim_def, video_info["fps"], profile,
                )

                animation_map[anim_id] = {
                    "video": video_name,
                    "frame_start": start,
                    "frame_end": end,
                    "fps": config["fps"],
                    "loop": config["loop"],
                    "auto_trim": config["auto_trim"],
                    "confirmed": True,
                }
        else:
            # Single animation — pick from list
            _show_animation_list(anim_types, profile)

            default_choice = None
            if vision_guess:
                for i, a in enumerate(anim_types, 1):
                    if a["id"] == vision_guess:
                        default_choice = str(i)
                        console.print(f"  [dim]Vision suggests: {vision_guess}[/dim]")
                        break

            choice = Prompt.ask(
                "  Animation type (number)",
                default=default_choice,
            )

            try:
                idx = int(choice) - 1
                anim = anim_types[idx]
            except (ValueError, IndexError):
                console.print(f"  [yellow]Invalid choice '{choice}' — defaulting to idle[/yellow]")
                anim = anim_types[0]

            anim_id = anim["id"]
            anim_def = anim_by_id.get(anim_id, anim)

            # Per-animation config
            config = _ask_per_animation_config(
                anim_id, anim_def, video_info["fps"], profile,
            )

            animation_map[anim_id] = {
                "video": video_name,
                "frame_start": 0,
                "frame_end": video_info["total_frames"] - 1,
                "fps": config["fps"],
                "loop": config["loop"],
                "auto_trim": config["auto_trim"],
                "confirmed": True,
            }

        # Show current map and save
        session["animation_map"] = animation_map
        _show_animation_map(animation_map)

        # Q5: Confirm
        if not Confirm.ask("  [bold]Confirm and continue?[/bold]", default=True):
            console.print("  [dim]Removing last entries — re-ask on next run[/dim]")
            # Remove entries for this video
            animation_map = {
                k: v for k, v in animation_map.items()
                if v["video"] != video_name
            }
            session["animation_map"] = animation_map

        # Save after each confirmed answer
        save_session(session, session_path)

    console.print("\n[bold green]Questionnaire complete.[/bold green]")
    _show_animation_map(animation_map)

    return session
