"""Game profile schema, validation, and helpers.

Defines the project-level configuration that influences all downstream phases:
resolution, art style, FPS, export target, background method, etc.
"""

import json
from pathlib import Path
from typing import Any


# Frame budget multipliers
_BUDGET_MULTIPLIERS = {
    "minimal": 0.6,
    "standard": 1.0,
    "smooth": 1.5,
}

# Valid enum values
GAME_TYPES = ("2d_platformer", "card_game", "top_down_rpg", "isometric", "generic")
ART_STYLES = ("pixel_art", "hd_sprites", "painted")
PERSPECTIVES = ("side_view", "top_down", "isometric", "three_quarter")
FRAME_BUDGETS = ("minimal", "standard", "smooth")
EXPORT_TARGETS = ("unity", "godot", "generic")
BG_METHODS = ("auto", "green_screen", "solid_color", "natural")
FILTER_MODES = ("point", "bilinear")

# Resolution presets
RESOLUTION_PRESETS = {
    "32x32": {"width": 32, "height": 32},
    "48x48": {"width": 48, "height": 48},
    "64x64": {"width": 64, "height": 64},
    "96x96": {"width": 96, "height": 96},
    "128x128": {"width": 128, "height": 128},
    "256x256": {"width": 256, "height": 256},
    "original": None,  # keep video resolution
}

# Preset config directory
_PRESETS_DIR = Path(__file__).parent.parent / "config" / "game_profiles"


def new_profile() -> dict[str, Any]:
    """Create a new profile with sensible defaults."""
    return {
        "game_type": "generic",
        "target_resolution": {"width": None, "height": None, "preset": "original"},
        "art_style": "hd_sprites",
        "perspective": "side_view",
        "frame_budget": "standard",
        "export_target": "unity",
        "bg_method": "auto",
        "bg_color": None,
        "extract_fps": None,
        "playback_fps": 12,
        "filter_mode": "bilinear",
        "ppu_override": None,
    }


def validate_profile(profile: dict[str, Any]) -> list[str]:
    """Validate a profile dict and return warnings (empty list = valid)."""
    warnings = []

    if profile.get("game_type") not in GAME_TYPES:
        warnings.append(f"Unknown game_type: {profile.get('game_type')}")

    if profile.get("art_style") not in ART_STYLES:
        warnings.append(f"Unknown art_style: {profile.get('art_style')}")

    if profile.get("perspective") not in PERSPECTIVES:
        warnings.append(f"Unknown perspective: {profile.get('perspective')}")

    if profile.get("frame_budget") not in FRAME_BUDGETS:
        warnings.append(f"Unknown frame_budget: {profile.get('frame_budget')}")

    if profile.get("export_target") not in EXPORT_TARGETS:
        warnings.append(f"Unknown export_target: {profile.get('export_target')}")

    if profile.get("bg_method") not in BG_METHODS:
        warnings.append(f"Unknown bg_method: {profile.get('bg_method')}")

    if profile.get("filter_mode") not in FILTER_MODES:
        warnings.append(f"Unknown filter_mode: {profile.get('filter_mode')}")

    if profile.get("bg_method") == "solid_color" and not profile.get("bg_color"):
        warnings.append("bg_method is solid_color but bg_color is not set")

    res = profile.get("target_resolution", {})
    if res.get("preset") not in RESOLUTION_PRESETS and res.get("preset") != "custom":
        if res.get("width") and res.get("height"):
            pass  # custom dimensions are fine
        else:
            warnings.append(f"Unknown resolution preset: {res.get('preset')}")

    fps = profile.get("playback_fps")
    if fps is not None and (not isinstance(fps, int) or fps < 1 or fps > 120):
        warnings.append(f"playback_fps should be 1-120, got: {fps}")

    ppu = profile.get("ppu_override")
    if ppu is not None and (not isinstance(ppu, int) or ppu < 1):
        warnings.append(f"ppu_override should be positive int, got: {ppu}")

    return warnings


def get_frame_target(profile: dict[str, Any], anim_type_def: dict) -> tuple[int, int]:
    """Get target frame count range for an animation type, adjusted by budget.

    Args:
        profile: Game profile dict.
        anim_type_def: Animation type definition from animation_types.json.

    Returns:
        (min_frames, max_frames) adjusted by budget multiplier.
    """
    typical = anim_type_def.get("typical_frames", [6, 12])
    multiplier = _BUDGET_MULTIPLIERS.get(profile.get("frame_budget", "standard"), 1.0)

    min_frames = max(2, round(typical[0] * multiplier))
    max_frames = max(min_frames, round(typical[1] * multiplier))

    return min_frames, max_frames


def get_bg_method(profile: dict[str, Any]) -> str:
    """Resolve the background removal method from profile.

    'auto' means detect automatically; other values are explicit overrides.
    """
    return profile.get("bg_method", "auto")


def get_ppu(profile: dict[str, Any], frame_h: int) -> int:
    """Get pixels-per-unit: use override if set, otherwise auto-calculate.

    Args:
        profile: Game profile dict.
        frame_h: Frame height in pixels.

    Returns:
        PPU value.
    """
    override = profile.get("ppu_override")
    if override is not None:
        return override

    from utils.spritesheet import recommended_ppu
    return recommended_ppu(frame_h)


def get_resample_filter(profile: dict[str, Any]):
    """Get PIL resample filter based on profile art style.

    Returns:
        PIL.Image.Resampling enum value.
    """
    from PIL import Image
    if profile.get("filter_mode") == "point" or profile.get("art_style") == "pixel_art":
        return Image.Resampling.NEAREST
    return Image.Resampling.LANCZOS


def load_preset(name: str) -> dict[str, Any]:
    """Load a preset profile from config/game_profiles/.

    Args:
        name: Preset filename without extension (e.g. 'platformer_2d').

    Returns:
        Profile dict.
    """
    path = _PRESETS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Preset not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        preset = json.load(f)

    # Merge with defaults so all keys exist
    profile = new_profile()
    profile.update(preset)
    return profile


def load_profile_from_path(path: str | Path) -> dict[str, Any]:
    """Load a profile from an arbitrary JSON file path.

    Args:
        path: Path to profile JSON file.

    Returns:
        Profile dict merged with defaults.
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile = new_profile()
    profile.update(data)
    return profile


def save_profile(profile: dict[str, Any], path: str | Path) -> None:
    """Save a profile dict to JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
        f.write("\n")


def list_presets() -> list[str]:
    """Return available preset names."""
    if not _PRESETS_DIR.exists():
        return []
    return sorted(p.stem for p in _PRESETS_DIR.glob("*.json"))
