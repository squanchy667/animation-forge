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
