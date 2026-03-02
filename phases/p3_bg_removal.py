"""Phase 3 — Background removal.

Dual-method background removal: rembg (primary) with numpy fallback.
"""

from pathlib import Path

import click
import numpy as np
from PIL import Image
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

console = Console()

# ── rembg Method (T005) ──────────────────────────────────────────────────────


def remove_bg_rembg(frames_dir: str, output_dir: str, model: str = "isnet-anime") -> dict:
    """Remove backgrounds using rembg with session reuse.

    Args:
        frames_dir: Directory containing input PNG frames.
        output_dir: Directory for output RGBA PNGs.
        model: rembg model name (isnet-anime, u2net_human_seg, u2net).

    Returns:
        Dict with method, model, frame_count, output_dir.
    """
    try:
        from rembg import new_session, remove
    except ImportError:
        console.print("  [yellow]rembg not available — skipping[/yellow]")
        return {"success": False, "reason": "rembg not installed"}

    frames_dir = Path(frames_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError(f"No frames found in {frames_dir}")

    # Create rembg session for model reuse across frames
    try:
        rembg_session = new_session(model)
    except Exception as e:
        console.print(f"  [yellow]Failed to load model '{model}': {e}[/yellow]")
        return {"success": False, "reason": f"model load failed: {e}"}

    console.print(f"  [dim]Model:[/dim] {model}")
    console.print(f"  [dim]Frames:[/dim] {len(frames)}")

    processed = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan][Phase 4/6][/bold cyan] Background Removal (rembg)"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("rembg", total=len(frames))

        for i, frame_path in enumerate(frames):
            img = Image.open(frame_path)
            result = remove(img, session=rembg_session)
            out_path = output_dir / frame_path.name
            result.save(out_path, "PNG")
            processed.append(str(out_path))
            progress.update(task, advance=1)

            # Quality check after first 5 frames
            if i == 4:
                _quality_check(output_dir, frames[:5])

    return {
        "success": True,
        "method": "rembg",
        "model": model,
        "frame_count": len(processed),
        "output_dir": str(output_dir),
        "frames": processed,
    }


def _quality_check(output_dir: Path, sample_frames: list[Path]) -> None:
    """Check bg removal quality on sample frames — warn if alpha looks wrong."""
    samples = [output_dir / f.name for f in sample_frames[::2]][:3]  # 3 evenly spaced

    for sample_path in samples:
        if not sample_path.exists():
            continue
        img = Image.open(sample_path).convert("RGBA")
        alpha = np.array(img)[:, :, 3]
        total_pixels = alpha.size
        opaque_ratio = np.count_nonzero(alpha > 128) / total_pixels
        transparent_ratio = np.count_nonzero(alpha < 128) / total_pixels

        if opaque_ratio > 0.80:
            console.print(f"  [yellow]Warning:[/yellow] {sample_path.name} — "
                          f"{opaque_ratio:.0%} opaque (background may not be removed)")
        elif transparent_ratio > 0.80:
            console.print(f"  [yellow]Warning:[/yellow] {sample_path.name} — "
                          f"{transparent_ratio:.0%} transparent (character may be removed)")

    if not click.confirm("  Background removal quality OK?", default=True):
        console.print("  [dim]User rejected quality — will retry with different model[/dim]")
        raise _QualityRejected()


class _QualityRejected(Exception):
    """Raised when user rejects bg removal quality."""


# ── numpy Fallback Method (T006) ─────────────────────────────────────────────


def remove_bg_numpy(frames_dir: str, output_dir: str) -> dict:
    """Remove backgrounds using numpy color-distance with scipy edge smoothing.

    Less accurate than rembg but works without internet, GPU, or rembg install.

    Args:
        frames_dir: Directory containing input PNG frames.
        output_dir: Directory for output RGBA PNGs.

    Returns:
        Dict with method, frame_count, output_dir.
    """
    try:
        from scipy.ndimage import binary_dilation
    except ImportError:
        binary_dilation = None

    frames_dir = Path(frames_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError(f"No frames found in {frames_dir}")

    console.print("  [yellow]Using numpy fallback — lower quality than rembg[/yellow]")
    console.print(f"  [dim]Frames:[/dim] {len(frames)}")

    # Sample background color from 4 corners of first frame
    first_img = np.array(Image.open(frames[0]).convert("RGB"))
    h, w = first_img.shape[:2]
    corners = [
        first_img[:8, :8],          # top-left
        first_img[:8, w - 8:],      # top-right
        first_img[h - 8:, :8],      # bottom-left
        first_img[h - 8:, w - 8:],  # bottom-right
    ]
    bg_mean = np.mean(np.concatenate([c.reshape(-1, 3) for c in corners], axis=0), axis=0)
    console.print(f"  [dim]Background color:[/dim] RGB({bg_mean[0]:.0f}, {bg_mean[1]:.0f}, {bg_mean[2]:.0f})")

    threshold = 55
    brightness_floor = 20
    kernel = np.ones((3, 3), dtype=bool)

    processed = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan][Phase 4/6][/bold cyan] Background Removal (numpy)"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("numpy", total=len(frames))

        for frame_path in frames:
            img = Image.open(frame_path).convert("RGB")
            pixels = np.array(img, dtype=np.float64)

            # Euclidean distance from background mean
            distance = np.sqrt(np.sum((pixels - bg_mean) ** 2, axis=2))

            # Brightness check
            brightness = np.mean(pixels, axis=2)

            # Foreground mask: far from bg color AND not too dark
            fg_mask = (distance >= threshold) & (brightness >= brightness_floor)

            # Edge smoothing via scipy dilation
            if binary_dilation is not None:
                fg_mask = binary_dilation(fg_mask, structure=kernel, iterations=2)

            # Build RGBA output
            rgba = np.zeros((pixels.shape[0], pixels.shape[1], 4), dtype=np.uint8)
            rgba[:, :, :3] = np.array(img)
            rgba[:, :, 3] = (fg_mask * 255).astype(np.uint8)

            out_path = output_dir / frame_path.name
            Image.fromarray(rgba, "RGBA").save(out_path, "PNG")
            processed.append(str(out_path))
            progress.update(task, advance=1)

    console.print(f"  [green]Processed {len(processed)} frames[/green] (numpy fallback)")

    return {
        "success": True,
        "method": "numpy_fallback",
        "frame_count": len(processed),
        "output_dir": str(output_dir),
        "frames": processed,
    }


# ── Method Selector ──────────────────────────────────────────────────────────


_REMBG_MODELS = ["isnet-anime", "u2net_human_seg", "u2net"]


def remove_backgrounds(session: dict, preview: bool = True) -> dict:
    """Run background removal with automatic method selection and fallback.

    Tries rembg models in order, falls back to numpy if all fail.
    Updates session config with method used.

    Args:
        session: Session config dict.
        preview: If True, show quality check after first 5 frames.

    Returns:
        Updated session dict.
    """
    output_base = Path(session["output_dir"]) / "frames" / "nobg"

    for video_name, video_info in session["videos"].items():
        raw_dir = Path(session["output_dir"]) / "frames" / "raw" / Path(video_name).stem
        video_output = output_base / Path(video_name).stem

        console.print(f"\n[bold]Removing backgrounds from {video_name}...[/bold]")

        result = None

        # Try rembg models in order
        for model in _REMBG_MODELS:
            try:
                result = remove_bg_rembg(str(raw_dir), str(video_output), model=model)
                if result.get("success"):
                    break
            except _QualityRejected:
                console.print(f"  [dim]Retrying with next model...[/dim]")
                continue
            except Exception as e:
                console.print(f"  [yellow]rembg ({model}) failed: {e}[/yellow]")
                continue

        # Fallback to numpy
        if not result or not result.get("success"):
            console.print("  [dim]Falling back to numpy method...[/dim]")
            result = remove_bg_numpy(str(raw_dir), str(video_output))

        # Update session
        video_info["nobg_frames"] = result.get("frames", [])
        video_info["nobg_frame_count"] = result.get("frame_count", 0)
        session["bg_removal_method"] = result.get("method", "unknown")
        if result.get("model"):
            session["bg_removal_method"] = f"rembg_{result['model']}"

    return session
