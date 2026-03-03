"""Claude Vision API helpers for character animation analysis.

Completely optional — skips gracefully if API key not set or SDK missing.
"""

import base64
import os
from pathlib import Path

from rich.console import Console

console = Console()

_VISION_PROMPT = """You are analyzing frames from a game character animation video.
Describe: 1) The character's visual style and appearance
2) What movement/action appears to be happening
3) What Unity animation type this most likely corresponds to \
(idle/walk/run/jump/attack/dash/hurt/death)
Be concise. 2-3 sentences max."""

_MODEL = "claude-sonnet-4-6"


def is_vision_available() -> bool:
    """Check if Vision API is usable (SDK installed + API key set)."""
    try:
        import anthropic  # noqa: F401
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    except ImportError:
        return False


def get_vision_client():
    """Create an Anthropic client or return None if unavailable.

    Returns:
        anthropic.Anthropic instance or None.
    """
    if not is_vision_available():
        return None
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception as e:
        console.print(f"  [yellow]Could not create Vision client: {e}[/yellow]")
        return None


def describe_character_from_frames(frame_paths: list[str], client) -> str | None:
    """Send frames to Claude Vision for character description.

    Args:
        frame_paths: List of frame PNG paths (up to 5 used).
        client: anthropic.Anthropic instance.

    Returns:
        Description string or None on failure.
    """
    if not frame_paths or client is None:
        return None

    # Use up to 5 frames
    paths = [Path(p) for p in frame_paths[:5]]

    # Build content blocks: alternating images and text
    content = []
    for path in paths:
        if not path.exists():
            continue
        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": data,
            },
        })

    if not content:
        return None

    content.append({"type": "text", "text": _VISION_PROMPT})

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": content}],
        )
        if response.content:
            return response.content[0].text
    except Exception as e:
        console.print(f"  [yellow]Vision API error: {e}[/yellow]")

    return None


# ── Questionnaire Helper ────────────────────────────────────────────────────


_SUGGEST_PROMPT = """You are analyzing frames from a game character animation video.
Based on these frames, what animation type does this most likely represent?
Respond with ONLY one of these IDs: idle, walk, run, jump, apex, fall, land, \
attack_1, attack_2, attack_3, dash, block, hurt, death.
One word only, no explanation."""


def suggest_animation_type(frame_paths: list[str], client) -> str | None:
    """Lightweight Vision call to suggest animation type for questionnaire defaults.

    Args:
        frame_paths: List of frame PNG paths (up to 3 used).
        client: anthropic.Anthropic instance.

    Returns:
        Animation type ID string or None on failure.
    """
    if not frame_paths or client is None:
        return None

    # Use up to 3 frames for a lightweight call
    paths = [Path(p) for p in frame_paths[:3]]

    content = []
    for path in paths:
        if not path.exists():
            continue
        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": data,
            },
        })

    if not content:
        return None

    content.append({"type": "text", "text": _SUGGEST_PROMPT})

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=32,
            messages=[{"role": "user", "content": content}],
        )
        if response.content:
            result = response.content[0].text.strip().lower()
            valid_types = {
                "idle", "walk", "run", "jump", "apex", "fall", "land",
                "attack_1", "attack_2", "attack_3", "dash", "block", "hurt", "death",
            }
            if result in valid_types:
                return result
    except Exception as e:
        console.print(f"  [yellow]Vision suggest error: {e}[/yellow]")

    return None


# ── Frame Analyzer ──────────────────────────────────────────────────────────


_ANALYZER_PROMPT = """You are analyzing frames from a game character animation.
The animation is declared as: {declared_type}

Analyze these frames and respond with ONLY valid JSON (no markdown):
{{
    "detected_type": "<one of: idle/walk/run/jump/apex/fall/land/attack_1/attack_2/attack_3/dash/block/hurt/death>",
    "confidence": "<high/medium/low>",
    "matches_declared": <true/false>,
    "description": "<1 sentence describing what the character is doing>",
    "quality_notes": "<1 sentence about animation quality, or null>"
}}"""


def analyze_animation_frames(
    frame_paths: list[str],
    declared_type: str,
    client,
) -> dict | None:
    """Send sample frames to Claude Vision for animation type verification.

    Args:
        frame_paths: List of sample frame PNG paths (3-5 frames).
        declared_type: The animation type declared by the user.
        client: anthropic.Anthropic instance.

    Returns:
        Analysis dict with detected_type, confidence, matches_declared,
        description, quality_notes. None on failure.
    """
    if not frame_paths or client is None:
        return None

    paths = [Path(p) for p in frame_paths[:5]]

    content = []
    for path in paths:
        if not path.exists():
            continue
        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": data,
            },
        })

    if not content:
        return None

    prompt = _ANALYZER_PROMPT.format(declared_type=declared_type)
    content.append({"type": "text", "text": prompt})

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": content}],
        )
        if response.content:
            text = response.content[0].text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            import json
            return json.loads(text)
    except Exception as e:
        console.print(f"  [yellow]Vision analyzer error: {e}[/yellow]")

    return None
