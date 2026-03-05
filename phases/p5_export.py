"""Phase 5 — Export: spritesheet packing, metadata, import guide, and output assembly.

T007: Spritesheet packing loop
T009: Metadata JSON, import guide rendering, output package assembly
T021: Profile-aware export (resolution resize, PPU override, Godot/generic)
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.table import Table

from utils.spritesheet import get_pivot_bottom_center, pack_spritesheet, recommended_ppu, resize_frames
from utils.unity_export import generate_animator_controller, generate_animator_params_cs

console = Console()


# ── Spritesheet Packing (T007/T021) ─────────────────────────────────────────


def pack_all_spritesheets(session: dict) -> dict[str, dict]:
    """Pack spritesheets for all animations in the session.

    Checks for refined frames first (from Phase 8 Game Refinement).
    Falls back to segmented frames, then nobg frames.

    Respects game_profile for:
    - target_resolution: resize frames before packing (skipped if refined)
    - ppu_override: use instead of auto-calculated PPU
    - filter_mode/art_style: determines resample method

    Args:
        session: Session config with animation_map and nobg frame paths.

    Returns:
        Dict mapping animation_id → spritesheet metadata.
    """
    output_base = Path(session["output_dir"]) / "export" / "Sprites"
    character = session["character_name"]
    animation_map = session.get("animation_map", {})
    refined_frames = session.get("refined_frames", {})
    profile = session.get("game_profile", {}) or {}

    if not animation_map:
        console.print("  [yellow]No animations mapped — skipping spritesheet packing[/yellow]")
        return {}

    use_refined = bool(refined_frames)
    if use_refined:
        console.print(f"  [dim]Using refined frames ({len(refined_frames)} animations)[/dim]")

    # Check if resize is needed (skip for refined frames — already sized)
    target_res = profile.get("target_resolution", {})
    target_w = target_res.get("width")
    target_h = target_res.get("height")
    needs_resize = (not use_refined) and target_w and target_h and target_res.get("preset") != "original"

    if needs_resize:
        resample = None
        if profile.get("filter_mode") == "point" or profile.get("art_style") == "pixel_art":
            from PIL import Image
            resample = Image.Resampling.NEAREST
            console.print(f"  [dim]Resizing to {target_w}x{target_h} (NEAREST for pixel art)[/dim]")
        else:
            from PIL import Image
            resample = Image.Resampling.LANCZOS
            console.print(f"  [dim]Resizing to {target_w}x{target_h} (LANCZOS)[/dim]")

    # Determine which animation IDs to pack
    anim_ids = list(refined_frames.keys()) if use_refined else list(animation_map.keys())

    spritesheets: dict[str, dict] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan][Phase 9][/bold cyan] Spritesheet Packing"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("pack", total=len(anim_ids))

        for anim_id in anim_ids:
            anim_info = animation_map.get(anim_id, {})

            if use_refined and anim_id in refined_frames:
                # Use refined frames directory
                refined_dir = Path(refined_frames[anim_id]["frames_dir"])
                anim_frames = [str(f) for f in sorted(refined_dir.glob("frame_*.png"))]
            else:
                # Fallback: segmented frames, then nobg frames
                anim_dir = Path(session["output_dir"]) / "frames" / "animations" / anim_id
                if anim_dir.exists():
                    anim_frames = [str(f) for f in sorted(anim_dir.glob("frame_*.png"))]
                else:
                    video_name = anim_info.get("video", "")
                    video_stem = Path(video_name).stem
                    nobg_dir = Path(session["output_dir"]) / "frames" / "nobg" / video_stem
                    start = anim_info.get("frame_start", 0)
                    end = anim_info.get("frame_end", 0)
                    all_frames = sorted(nobg_dir.glob("frame_*.png"))
                    anim_frames = [str(f) for f in all_frames[start:end + 1]]

            if not anim_frames:
                console.print(f"  [yellow]Warning:[/yellow] No frames for '{anim_id}' — skipping")
                progress.update(task, advance=1)
                continue

            # Resize if profile specifies target resolution (skip for refined)
            if needs_resize:
                resize_frames(anim_frames, target_w, target_h, resample)

            out_path = output_base / f"{character}_{anim_id}.png"
            meta = pack_spritesheet(anim_frames, str(out_path))

            # Enrich metadata
            meta["animation_id"] = anim_id

            if use_refined and anim_id in refined_frames:
                # Use refinement metadata (more accurate than animation_map)
                ref = refined_frames[anim_id]
                meta["fps"] = session.get("game_profile", {}).get("playback_fps", 12)
                meta["loop"] = ref.get("loop", False)
            else:
                meta["fps"] = anim_info.get("fps", 12)
                meta["loop"] = anim_info.get("loop", False)

            meta["pivot"] = get_pivot_bottom_center(meta["frame_w"], meta["frame_h"])

            # PPU: use profile override or auto-calculate
            ppu_override = profile.get("ppu_override")
            if ppu_override:
                meta["ppu"] = ppu_override
            else:
                meta["ppu"] = recommended_ppu(meta["frame_h"])

            spritesheets[anim_id] = meta
            progress.update(task, advance=1)

    console.print(f"  [green]Packed {len(spritesheets)} spritesheets[/green]")
    return spritesheets


# ── Metadata + Import Guide (T009/T021) ──────────────────────────────────────


def write_metadata(session: dict, spritesheets: dict[str, dict], output_path: str) -> None:
    """Write metadata.json with all export details.

    Args:
        session: Session config.
        spritesheets: Dict of animation_id → spritesheet metadata.
        output_path: Path for metadata.json.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    profile = session.get("game_profile", {}) or {}

    metadata = {
        "character_name": session["character_name"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "Animation Forge v0.2.0",
        "bg_removal_method": session.get("bg_removal_method", "unknown"),
        "game_profile": {
            "game_type": profile.get("game_type"),
            "art_style": profile.get("art_style"),
            "export_target": profile.get("export_target"),
            "filter_mode": profile.get("filter_mode"),
        } if profile else None,
        "animations": {},
    }

    for anim_id, sheet in spritesheets.items():
        anim_meta = {
            "spritesheet": sheet["path"],
            "frame_w": sheet["frame_w"],
            "frame_h": sheet["frame_h"],
            "cols": sheet["cols"],
            "rows": sheet["rows"],
            "n_frames": sheet["n_frames"],
            "fps": sheet["fps"],
            "loop": sheet["loop"],
            "pivot": list(sheet["pivot"]),
            "ppu": sheet["ppu"],
        }
        metadata["animations"][anim_id] = anim_meta

    # Include analysis results if available
    analysis = session.get("analysis_results", {})
    if analysis:
        metadata["analysis_results"] = analysis

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        f.write("\n")


def render_import_guide(session: dict, spritesheets: dict[str, dict], output_path: str) -> None:
    """Render IMPORT_GUIDE.md from template with actual values.

    Args:
        session: Session config.
        spritesheets: Dict of animation_id → spritesheet metadata.
        output_path: Path for rendered IMPORT_GUIDE.md.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    character = session["character_name"]
    profile = session.get("game_profile", {}) or {}
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Get representative dimensions from first spritesheet
    first_sheet = next(iter(spritesheets.values()), {})
    frame_w = first_sheet.get("frame_w", 64)
    frame_h = first_sheet.get("frame_h", 64)
    ppu = first_sheet.get("ppu", 64)
    default_fps = first_sheet.get("fps", 12)

    # Profile-aware values
    game_type = profile.get("game_type", "generic")
    art_style = profile.get("art_style", "hd_sprites")
    filter_mode = profile.get("filter_mode", "bilinear")
    export_target = profile.get("export_target", "unity")

    # Build file table
    file_rows = []
    for anim_id, sheet in spritesheets.items():
        rel_path = f"Sprites/{character}_{anim_id}.png"
        file_rows.append(f"| `{rel_path}` | {anim_id} spritesheet ({sheet['n_frames']} frames) |")

    if export_target == "unity":
        file_rows.append(f"| `Animator/{character}_controller.json` | AnimatorController scaffold |")
        file_rows.append(f"| `Animator/{character}AnimatorParams.cs` | C# parameter constants |")
    elif export_target == "godot":
        file_rows.append(f"| `{character}_sprite_frames.json` | Godot SpriteFrames metadata |")
    file_rows.append("| `metadata.json` | Machine-readable export metadata |")
    file_table = "\n".join(file_rows)

    # Build animation clips section
    clip_lines = []
    for anim_id, sheet in spritesheets.items():
        loop_str = "Loop Time: ON" if sheet["loop"] else "Loop Time: OFF"
        clip_lines.append(f"- **{anim_id}**: {sheet['n_frames']} frames at {sheet['fps']} fps ({loop_str})")
    animation_clips = "\n".join(clip_lines)

    # Build parameters table
    params_lines = [
        "| Parameter | Type | Default |",
        "|-----------|------|---------|",
        "| Speed | Float | 0.0 |",
        "| IsGrounded | Bool | true |",
        "| AttackTrigger | Trigger | — |",
        "| HurtTrigger | Trigger | — |",
        "| DeathTrigger | Trigger | — |",
    ]
    parameters_table = "\n".join(params_lines)

    # Build animation reference
    looping = [f"- **{a}** ({s['n_frames']} frames)" for a, s in spritesheets.items() if s["loop"]]
    non_looping = [f"- **{a}** ({s['n_frames']} frames)" for a, s in spritesheets.items() if not s["loop"]]

    ref_lines = []
    if looping:
        ref_lines.append("### Looping Animations")
        ref_lines.extend(looping)
    if non_looping:
        ref_lines.append("\n### One-Shot Animations")
        ref_lines.extend(non_looping)
    animation_reference = "\n".join(ref_lines)

    # Build quality analysis section
    analysis = session.get("analysis_results", {})
    quality_lines = []
    if analysis:
        quality_lines.append("### Quality Analysis")
        for anim_id, result in analysis.items():
            mc = result.get("motion_consistency", {})
            tq = result.get("transparency_quality", {})
            score = mc.get("motion_score", 0)
            alpha = tq.get("quality_rating", "unknown")
            quality_lines.append(f"- **{anim_id}**: motion {score:.0%}, alpha quality: {alpha}")
    quality_analysis = "\n".join(quality_lines)

    # Read template
    template_path = Path(__file__).parent.parent / "templates" / "import_guide.md.tmpl"
    template = template_path.read_text(encoding="utf-8")

    # Fill placeholders
    guide = template.format(
        character_name=character,
        version="0.2.0",
        timestamp=timestamp,
        file_table=file_table,
        output_folder=f"{character}_animations",
        pixels_per_unit=ppu,
        cell_width=frame_w,
        cell_height=frame_h,
        animation_clips=animation_clips,
        parameters_table=parameters_table,
        animation_reference=animation_reference,
        default_fps=default_fps,
        game_type=game_type,
        art_style=art_style,
        filter_mode=filter_mode,
        quality_analysis=quality_analysis,
    )

    output_path.write_text(guide, encoding="utf-8")


def _generate_godot_metadata(
    character: str,
    spritesheets: dict[str, dict],
    output_path: str,
) -> None:
    """Generate Godot-compatible SpriteFrames metadata JSON.

    Args:
        character: Character name.
        spritesheets: Dict of animation_id → spritesheet metadata.
        output_path: Path for output JSON file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sprite_frames = {
        "character_name": character,
        "type": "SpriteFrames",
        "animations": [],
    }

    for anim_id, sheet in spritesheets.items():
        anim = {
            "name": anim_id,
            "speed": float(sheet.get("fps", 12)),
            "loop": sheet.get("loop", False),
            "frames": [],
        }
        # Reference spritesheet with atlas coordinates
        for i in range(sheet["n_frames"]):
            col = i % sheet["cols"]
            row = i // sheet["cols"]
            anim["frames"].append({
                "texture": f"Sprites/{character}_{anim_id}.png",
                "region": {
                    "x": col * sheet["frame_w"],
                    "y": row * sheet["frame_h"],
                    "w": sheet["frame_w"],
                    "h": sheet["frame_h"],
                },
            })
        sprite_frames["animations"].append(anim)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sprite_frames, f, indent=2, ensure_ascii=False)
        f.write("\n")


def assemble_output_package(session: dict, spritesheets: dict[str, dict]) -> str:
    """Assemble the final output directory and ZIP package.

    Respects game_profile.export_target:
    - "unity": AnimatorController + C# params + spritesheets (default)
    - "godot": SpriteFrames metadata + spritesheets
    - "generic": spritesheets + JSON metadata only

    Args:
        session: Session config.
        spritesheets: Dict of animation_id → spritesheet metadata.

    Returns:
        Path to the created ZIP file.
    """
    character = session["character_name"]
    base = Path(session["output_dir"])
    package_dir = base / f"{character}_animations"
    profile = session.get("game_profile", {}) or {}
    export_target = profile.get("export_target", "unity")

    # Create directory structure
    sprites_dir = package_dir / "Sprites"
    sprites_dir.mkdir(parents=True, exist_ok=True)

    # Copy spritesheets to package
    for anim_id, sheet in spritesheets.items():
        src = Path(sheet["path"])
        dst = sprites_dir / src.name
        if src != dst:
            shutil.copy2(str(src), str(dst))

    # Engine-specific exports
    if export_target == "unity":
        animator_dir = package_dir / "Animator"
        animator_dir.mkdir(parents=True, exist_ok=True)

        animations = list(spritesheets.keys())
        generate_animator_controller(
            character, animations, str(animator_dir / f"{character}_controller.json")
        )
        generate_animator_params_cs(
            character, animations, str(animator_dir / f"{character}AnimatorParams.cs")
        )
        console.print("  [dim]Generated Unity AnimatorController + C# params[/dim]")

    elif export_target == "godot":
        _generate_godot_metadata(
            character, spritesheets,
            str(package_dir / f"{character}_sprite_frames.json"),
        )
        console.print("  [dim]Generated Godot SpriteFrames metadata[/dim]")

    else:
        console.print("  [dim]Generic export — spritesheets + metadata only[/dim]")

    # Write metadata
    write_metadata(session, spritesheets, str(package_dir / "metadata.json"))

    # Render import guide
    render_import_guide(session, spritesheets, str(package_dir / "IMPORT_GUIDE.md"))

    # Create ZIP
    zip_path = shutil.make_archive(str(package_dir), "zip", str(base), f"{character}_animations")

    # Print summary table
    _print_summary(package_dir, zip_path, spritesheets)

    return zip_path


def _print_summary(package_dir: Path, zip_path: str, spritesheets: dict[str, dict]) -> None:
    """Print final summary table with file paths and sizes."""
    table = Table(title="Output Package", border_style="green")
    table.add_column("File", style="cyan")
    table.add_column("Size", justify="right")

    for path in sorted(package_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(package_dir)
            size_kb = path.stat().st_size / 1024
            table.add_row(str(rel), f"{size_kb:.1f} KB")

    zip_size_mb = Path(zip_path).stat().st_size / (1024 * 1024)
    table.add_row(f"[bold]{Path(zip_path).name}[/bold]", f"[bold]{zip_size_mb:.2f} MB[/bold]")

    console.print(table)
    console.print(f"\n  [green]Package ready:[/green] {zip_path}")
