"""Spritesheet packing utilities.

Packs frame PNGs into fixed-cell grid spritesheets for Unity import.
"""

import math
from pathlib import Path

from PIL import Image


def pack_spritesheet(frames: list[str], output_path: str) -> dict:
    """Pack frames into a grid spritesheet PNG.

    Layout: fixed-cell grid, frames ordered left→right, top→bottom.
    Background is fully transparent (RGBA).

    Args:
        frames: Sorted list of frame PNG paths.
        output_path: Output spritesheet PNG path.

    Returns:
        Metadata dict with path, frame_w, frame_h, cols, rows, n_frames,
        sheet_w, sheet_h.
    """
    if not frames:
        raise ValueError("No frames to pack")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Use first frame dimensions as cell size
    first = Image.open(frames[0])
    frame_w, frame_h = first.size
    first.close()

    n_frames = len(frames)
    cols = math.ceil(math.sqrt(n_frames))
    rows = math.ceil(n_frames / cols)

    sheet_w = cols * frame_w
    sheet_h = rows * frame_h

    # Warn on very large sheets
    if n_frames > 100:
        from rich.console import Console
        Console().print(
            f"  [yellow]Warning:[/yellow] Large spritesheet — {n_frames} frames, "
            f"{sheet_w}x{sheet_h}px"
        )

    # Create transparent RGBA canvas
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

    for i, frame_path in enumerate(frames):
        col = i % cols
        row = i // cols
        x = col * frame_w
        y = row * frame_h
        frame = Image.open(frame_path).convert("RGBA")
        sheet.paste(frame, (x, y))
        frame.close()

    sheet.save(str(output_path), "PNG")
    sheet.close()

    return {
        "path": str(output_path),
        "frame_w": frame_w,
        "frame_h": frame_h,
        "cols": cols,
        "rows": rows,
        "n_frames": n_frames,
        "sheet_w": sheet_w,
        "sheet_h": sheet_h,
    }


def resize_frames(
    frames: list[str],
    target_w: int,
    target_h: int,
    resample=None,
) -> list[str]:
    """Resize frames in-place to target dimensions.

    Args:
        frames: List of frame PNG paths.
        target_w: Target width in pixels.
        target_h: Target height in pixels.
        resample: PIL resample filter (default: LANCZOS).

    Returns:
        Same list of frame paths (modified in-place).
    """
    if resample is None:
        resample = Image.Resampling.LANCZOS

    for frame_path in frames:
        path = Path(frame_path)
        if not path.exists():
            continue
        img = Image.open(path)
        if img.size == (target_w, target_h):
            img.close()
            continue
        resized = img.resize((target_w, target_h), resample)
        if img.mode == "RGBA":
            resized = resized.convert("RGBA")
        resized.save(str(path), "PNG")
        img.close()
        resized.close()

    return frames


def get_pivot_bottom_center(frame_w: int, frame_h: int) -> tuple[float, float]:
    """Return Unity bottom-center pivot for ground-based characters.

    Returns:
        (0.5, 0.0) — centered horizontally, anchored at bottom.
    """
    return (0.5, 0.0)


def recommended_ppu(frame_h: int, target_unity_height: float = 2.0) -> int:
    """Calculate recommended Pixels Per Unit, rounded to nearest power of 2.

    Args:
        frame_h: Frame height in pixels.
        target_unity_height: Desired height in Unity world units.

    Returns:
        PPU rounded to nearest power of 2.
    """
    raw_ppu = frame_h / target_unity_height
    # Round to nearest power of 2
    if raw_ppu <= 0:
        return 16
    log2 = math.log2(raw_ppu)
    return int(2 ** round(log2))
