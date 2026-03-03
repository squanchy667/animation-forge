"""Game Profile Setup — interactive questionnaire for project-level configuration.

Asks the user about game type, resolution, art style, FPS, export target, and
background method. Saves the profile to game_profile.json in the session directory
and stores it in session["game_profile"].
"""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from utils.game_profile import (
    ART_STYLES,
    BG_METHODS,
    EXPORT_TARGETS,
    FRAME_BUDGETS,
    GAME_TYPES,
    PERSPECTIVES,
    RESOLUTION_PRESETS,
    list_presets,
    load_preset,
    new_profile,
    save_profile,
    validate_profile,
)

console = Console()

# Descriptions for display
_GAME_TYPE_DESC = {
    "2d_platformer": "Side-scrolling platformer (Mario, Hollow Knight)",
    "card_game": "Card battler with character portraits (Slay the Spire)",
    "top_down_rpg": "Overhead view RPG (Stardew Valley, Zelda)",
    "isometric": "Isometric perspective (Diablo, Hades)",
    "generic": "No specific game type — use general defaults",
}

_ART_STYLE_DESC = {
    "pixel_art": "Pixel art — sharp edges, point filtering, small resolution",
    "hd_sprites": "HD sprites — smooth edges, bilinear filtering",
    "painted": "Painted/illustrated — high detail, LANCZOS scaling",
}

_PERSPECTIVE_DESC = {
    "side_view": "Side-on camera (platformers, fighters)",
    "top_down": "Overhead camera (RPGs, strategy)",
    "isometric": "Isometric/diagonal camera",
    "three_quarter": "3/4 view (action RPGs)",
}

_BUDGET_DESC = {
    "minimal": "Snappy — fewer frames, tight animations (0.6x typical)",
    "standard": "Balanced — standard frame counts (1.0x typical)",
    "smooth": "Cinematic — extra frames for smooth motion (1.5x typical)",
}

_EXPORT_DESC = {
    "unity": "Unity — AnimatorController + C# params + spritesheets",
    "godot": "Godot — SpriteFrames metadata + spritesheets",
    "generic": "Generic — spritesheets + JSON metadata only",
}

_BG_METHOD_DESC = {
    "auto": "Auto-detect — try green screen first, then rembg/numpy",
    "green_screen": "Green screen — always use chroma-key removal",
    "solid_color": "Solid color background — specify RGB color",
    "natural": "Natural — rembg neural network only, skip green screen detection",
}


def _ask_choice(label: str, options: dict[str, str], default: str) -> str:
    """Display a numbered list and ask user to pick one."""
    keys = list(options.keys())

    table = Table(show_header=False, border_style="cyan", padding=(0, 2))
    table.add_column("#", style="bold", width=4)
    table.add_column("Option", style="cyan")
    table.add_column("Description")

    for i, key in enumerate(keys, 1):
        marker = " *" if key == default else ""
        table.add_row(str(i), key + marker, options[key])

    console.print(table)

    default_num = str(keys.index(default) + 1) if default in keys else "1"
    choice = Prompt.ask(f"  {label} (number)", default=default_num)

    try:
        idx = int(choice) - 1
        return keys[idx]
    except (ValueError, IndexError):
        console.print(f"  [yellow]Invalid choice — using default: {default}[/yellow]")
        return default


def run_profile_setup(session: dict) -> dict:
    """Run the interactive game profile questionnaire.

    Args:
        session: Session config dict.

    Returns:
        Updated session with game_profile populated.
    """
    console.print(Panel(
        "[bold]Configure your game's animation profile.[/bold]\n"
        "These settings influence resolution, frame counts, export format,\n"
        "and background removal across the entire pipeline.",
        title="[bold magenta]Game Profile Setup[/bold magenta]",
        border_style="magenta",
        padding=(1, 2),
    ))

    # Check for available presets
    presets = list_presets()
    profile = new_profile()

    if presets:
        console.print("\n  [bold]Available presets:[/bold]")
        for i, name in enumerate(presets, 1):
            console.print(f"    {i}. {name}")
        console.print(f"    {len(presets) + 1}. Custom (configure manually)")

        preset_choice = Prompt.ask(
            "  Start from a preset? (number)",
            default=str(len(presets) + 1),
        )
        try:
            idx = int(preset_choice) - 1
            if 0 <= idx < len(presets):
                profile = load_preset(presets[idx])
                console.print(f"  [green]Loaded preset: {presets[idx]}[/green]")
        except (ValueError, IndexError):
            pass

    # Q1: Game type
    console.print("\n[bold]1. Game Type[/bold]")
    profile["game_type"] = _ask_choice("Game type", _GAME_TYPE_DESC, profile["game_type"])

    # Auto-adjust defaults based on game type
    if profile["game_type"] == "2d_platformer":
        profile.setdefault("perspective", "side_view")
    elif profile["game_type"] == "top_down_rpg":
        profile["perspective"] = "top_down"
        if profile["art_style"] == "hd_sprites":
            profile["art_style"] = "pixel_art"
            profile["filter_mode"] = "point"
    elif profile["game_type"] == "isometric":
        profile["perspective"] = "isometric"

    # Q2: Target resolution
    console.print("\n[bold]2. Target Resolution[/bold]")
    res_options = {k: f"{v['width']}x{v['height']}px" if v else "Keep video native resolution"
                   for k, v in RESOLUTION_PRESETS.items()}
    current_preset = profile.get("target_resolution", {}).get("preset", "original")
    preset_choice = _ask_choice("Resolution", res_options, current_preset)

    if preset_choice == "original":
        profile["target_resolution"] = {"width": None, "height": None, "preset": "original"}
    elif preset_choice in RESOLUTION_PRESETS:
        dims = RESOLUTION_PRESETS[preset_choice]
        profile["target_resolution"] = {"width": dims["width"], "height": dims["height"], "preset": preset_choice}
    else:
        # Custom
        w = int(Prompt.ask("  Width (px)", default="128"))
        h = int(Prompt.ask("  Height (px)", default="128"))
        profile["target_resolution"] = {"width": w, "height": h, "preset": "custom"}

    # Q3: Art style
    console.print("\n[bold]3. Art Style[/bold]")
    profile["art_style"] = _ask_choice("Art style", _ART_STYLE_DESC, profile["art_style"])

    # Auto-set filter mode based on art style
    if profile["art_style"] == "pixel_art":
        profile["filter_mode"] = "point"
    else:
        profile["filter_mode"] = "bilinear"

    # Q4: Camera perspective
    console.print("\n[bold]4. Camera Perspective[/bold]")
    profile["perspective"] = _ask_choice("Perspective", _PERSPECTIVE_DESC, profile["perspective"])

    # Q5: Frame budget
    console.print("\n[bold]5. Frame Budget[/bold]")
    profile["frame_budget"] = _ask_choice("Frame budget", _BUDGET_DESC, profile["frame_budget"])

    # Q6: Export target
    console.print("\n[bold]6. Export Target[/bold]")
    profile["export_target"] = _ask_choice("Export target", _EXPORT_DESC, profile["export_target"])

    # Q7: Background method
    console.print("\n[bold]7. Background Removal Method[/bold]")
    profile["bg_method"] = _ask_choice("BG method", _BG_METHOD_DESC, profile["bg_method"])

    if profile["bg_method"] == "solid_color":
        r = int(Prompt.ask("  Background R (0-255)", default="0"))
        g = int(Prompt.ask("  Background G (0-255)", default="255"))
        b = int(Prompt.ask("  Background B (0-255)", default="0"))
        profile["bg_color"] = [r, g, b]

    # Q8: Default playback FPS
    console.print("\n[bold]8. Default Playback FPS[/bold]")
    fps_default = str(profile.get("playback_fps", 12))
    fps = Prompt.ask("  Playback FPS for animations", default=fps_default)
    try:
        profile["playback_fps"] = int(fps)
    except ValueError:
        profile["playback_fps"] = 12

    # Q9: Summary and confirm
    console.print()
    _show_profile_summary(profile)

    warnings = validate_profile(profile)
    if warnings:
        for w in warnings:
            console.print(f"  [yellow]Warning:[/yellow] {w}")

    if not Confirm.ask("\n  [bold]Confirm profile?[/bold]", default=True):
        console.print("  [dim]Profile not saved — using defaults[/dim]")
        profile = new_profile()

    # Save to session
    session["game_profile"] = profile

    # Save as file in session dir
    profile_path = Path(session["output_dir"]) / "game_profile.json"
    save_profile(profile, profile_path)
    console.print(f"  [green]Profile saved:[/green] {profile_path}")

    return session


def _show_profile_summary(profile: dict) -> None:
    """Display profile as a Rich summary table."""
    table = Table(title="Game Profile Summary", border_style="green")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    res = profile.get("target_resolution", {})
    res_str = res.get("preset", "original")
    if res.get("width") and res.get("height"):
        res_str = f"{res['width']}x{res['height']} ({res.get('preset', 'custom')})"

    table.add_row("Game Type", profile.get("game_type", "?"))
    table.add_row("Resolution", res_str)
    table.add_row("Art Style", profile.get("art_style", "?"))
    table.add_row("Perspective", profile.get("perspective", "?"))
    table.add_row("Frame Budget", profile.get("frame_budget", "?"))
    table.add_row("Export Target", profile.get("export_target", "?"))
    table.add_row("BG Method", profile.get("bg_method", "?"))
    if profile.get("bg_color"):
        table.add_row("BG Color", str(profile["bg_color"]))
    table.add_row("Playback FPS", str(profile.get("playback_fps", 12)))
    table.add_row("Filter Mode", profile.get("filter_mode", "?"))

    console.print(table)
