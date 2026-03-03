"""Phase 3 — Background removal.

Three-stage background removal pipeline:
1. Green screen detection — auto-detects chroma-key green and removes via HSV chroma key
2. rembg (primary) — neural network background removal for non-green-screen videos
3. numpy fallback — color-distance removal when rembg is unavailable

For green screen videos, stage 1 runs first, then rembg cleans up remaining artifacts.
A final green cleanup pass catches any residual green fringing on edges.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

console = Console()

# ── Green Screen Detection & Removal ─────────────────────────────────────────


def _detect_green_screen(frames_dir: Path, sample_count: int = 3) -> bool:
    """Auto-detect whether frames have a green screen background.

    Samples a few frames and checks if corners/edges contain
    predominantly green pixels (high green channel, low red/blue).

    Returns:
        True if green screen is detected.
    """
    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        return False

    # Sample frames from start, middle, end
    indices = [0, len(frames) // 2, -1]
    green_corner_count = 0
    total_checks = 0

    for idx in indices:
        if abs(idx) >= len(frames):
            continue
        img = np.array(Image.open(frames[idx]).convert("RGB"), dtype=np.float32)
        h, w = img.shape[:2]

        # Check 4 corner regions (16x16 each)
        corners = [
            img[:16, :16],          # top-left
            img[:16, w - 16:],      # top-right
            img[h - 16:, :16],      # bottom-left
            img[h - 16:, w - 16:],  # bottom-right
        ]

        for corner in corners:
            r, g, b = corner[:, :, 0], corner[:, :, 1], corner[:, :, 2]
            green_dominant = (g > 80) & ((g - r) > 20) & ((g - b) > 20)
            ratio = np.count_nonzero(green_dominant) / green_dominant.size
            if ratio > 0.5:
                green_corner_count += 1
            total_checks += 1

    # If majority of corners are green, it's a green screen
    return total_checks > 0 and (green_corner_count / total_checks) > 0.3


def _remove_green_from_frame(img: Image.Image) -> Image.Image:
    """Remove green screen from a single frame using chroma-key detection.

    Uses color channel analysis to identify green-dominant pixels and
    sets them transparent. Also desaturates green fringing on edge pixels.

    Args:
        img: Input image (RGB or RGBA).

    Returns:
        RGBA image with green pixels made transparent.
    """
    rgba = np.array(img.convert("RGBA"), dtype=np.float32)
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]

    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

    # Green excess: how much greener than other channels
    green_excess = g - np.maximum(r, b)
    green_ratio = g / (r + g + b + 1e-6)

    # Strong green: clearly green screen
    strong_green = (green_excess > 30) & (green_ratio > 0.38)

    # Medium green: greenish tint
    medium_green = (green_excess > 15) & (green_ratio > 0.36) & (g > 60)

    # Bright green: classic chroma key color
    bright_green = (g > 100) & (green_excess > 20) & (green_ratio > 0.35)

    # Combined green mask
    green_mask = strong_green | medium_green | bright_green

    # Set green pixels fully transparent
    alpha[green_mask] = 0

    # Desaturate green fringe on edge pixels near green areas
    edge_green = (green_excess > 5) & (green_ratio > 0.34) & (~green_mask) & (alpha > 0)
    if np.any(edge_green):
        max_rb = np.maximum(r, b)
        blend = np.clip(green_excess[edge_green] / 30.0, 0, 1)
        rgba[edge_green, 1] = g[edge_green] - (g[edge_green] - max_rb[edge_green]) * blend * 0.7

    # Clean up very low alpha
    alpha[alpha < 10] = 0
    rgba[:, :, 3] = alpha

    return Image.fromarray(rgba.astype(np.uint8), "RGBA")


def remove_bg_greenscreen(frames_dir: str, output_dir: str) -> dict:
    """Remove green screen backgrounds using chroma-key detection.

    Args:
        frames_dir: Directory containing input PNG frames.
        output_dir: Directory for output RGBA PNGs.

    Returns:
        Dict with method, frame_count, output_dir.
    """
    frames_dir = Path(frames_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError(f"No frames found in {frames_dir}")

    console.print(f"  [dim]Config:[/dim] chroma-key green removal")
    console.print(f"  [dim]Frames:[/dim] {len(frames)}")

    processed = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan][Phase 4/6][/bold cyan] Green Screen Removal"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("greenscreen", total=len(frames))

        for frame_path in frames:
            img = Image.open(frame_path)
            result = _remove_green_from_frame(img)
            out_path = output_dir / frame_path.name
            result.save(out_path, "PNG")
            processed.append(str(out_path))
            progress.update(task, advance=1)

    console.print(f"  [green]Processed {len(processed)} frames[/green] (chroma-key green removal)")

    return {
        "success": True,
        "method": "greenscreen",
        "frame_count": len(processed),
        "output_dir": str(output_dir),
        "frames": processed,
    }


def _cleanup_green_residue(output_dir: Path) -> None:
    """Final pass: remove any residual green fringing from RGBA frames.

    Runs after rembg to catch green artifacts the neural network missed.
    Modifies frames in-place.
    """
    frames = sorted(output_dir.glob("frame_*.png"))
    if not frames:
        return

    cleaned = 0
    for frame_path in frames:
        img = Image.open(frame_path).convert("RGBA")
        result = _remove_green_from_frame(img)
        result.save(frame_path, "PNG")
        cleaned += 1

    if cleaned:
        console.print(f"  [dim]Green cleanup pass: {cleaned} frames[/dim]")


# ── rembg Method (T005) ──────────────────────────────────────────────────────


def _refine_alpha(img: Image.Image, feather_radius: int = 1) -> Image.Image:
    """Post-process RGBA image: smooth alpha edges to reduce jagged cutouts.

    Applies a slight Gaussian blur to the alpha channel only, preserving
    the RGB pixel data. This softens hard edges from the neural network mask.
    """
    if img.mode != "RGBA":
        return img

    r, g, b, a = img.split()

    # Light gaussian blur on alpha to feather edges
    if feather_radius > 0:
        a = a.filter(ImageFilter.GaussianBlur(radius=feather_radius))

    # Re-threshold: keep fully transparent areas transparent, boost near-opaque
    a_arr = np.array(a, dtype=np.float64)
    # Sigmoid-style contrast boost — sharpens the soft edge band
    a_arr = np.clip((a_arr - 30) * (255 / 195), 0, 255).astype(np.uint8)

    return Image.merge("RGBA", (r, g, b, Image.fromarray(a_arr)))


def remove_bg_rembg(
    frames_dir: str,
    output_dir: str,
    model: str = "isnet-anime",
    alpha_matting: bool = False,
    post_process: bool = True,
) -> dict:
    """Remove backgrounds using rembg with session reuse and edge refinement.

    Args:
        frames_dir: Directory containing input PNG frames.
        output_dir: Directory for output RGBA PNGs.
        model: rembg model name (isnet-anime, u2net_human_seg, u2net).
        alpha_matting: Enable alpha matting (off by default — too aggressive on AI video).
        post_process: Apply edge feathering post-processing.

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

    features = [f"model={model}"]
    if alpha_matting:
        features.append("alpha-matting")
    if post_process:
        features.append("edge-refine")
    console.print(f"  [dim]Config:[/dim] {', '.join(features)}")
    console.print(f"  [dim]Frames:[/dim] {len(frames)}")

    processed = []
    warnings = []
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

            # rembg remove with optional alpha matting
            try:
                result = remove(
                    img,
                    session=rembg_session,
                    alpha_matting=alpha_matting,
                    alpha_matting_foreground_threshold=240,
                    alpha_matting_background_threshold=10,
                    alpha_matting_erode_size=10,
                )
            except Exception:
                # Alpha matting can fail on some frames — fall back to plain remove
                result = remove(img, session=rembg_session)

            # Post-processing: edge refinement
            if post_process:
                result = _refine_alpha(result, feather_radius=1)

            out_path = output_dir / frame_path.name
            result.save(out_path, "PNG")
            processed.append(str(out_path))
            progress.update(task, advance=1)

            # Quality spot-check at frame 5 (non-blocking — just warn)
            if i == 4:
                warnings = _quality_check(output_dir, frames[:5])

    if warnings:
        for w in warnings:
            console.print(f"  [yellow]Warning:[/yellow] {w}")
    console.print(f"  [green]Processed {len(processed)} frames[/green] (rembg + {model})")

    return {
        "success": True,
        "method": "rembg",
        "model": model,
        "frame_count": len(processed),
        "output_dir": str(output_dir),
        "frames": processed,
    }


def _quality_check(output_dir: Path, sample_frames: list[Path]) -> list[str]:
    """Check bg removal quality on sample frames — return warnings if alpha looks wrong.

    Non-blocking: returns a list of warning strings instead of prompting.
    """
    warnings = []
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
            warnings.append(f"{sample_path.name} — {opaque_ratio:.0%} opaque "
                            f"(background may not be fully removed)")
        elif transparent_ratio > 0.95:
            warnings.append(f"{sample_path.name} — {transparent_ratio:.0%} transparent "
                            f"(character may be over-removed)")

    return warnings




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


# ── Model Auto-Selection ─────────────────────────────────────────────────────


_REMBG_MODELS = ["isnet-anime", "u2net_human_seg", "u2net"]


def _pick_best_model(frames_dir: Path) -> str:
    """Test each rembg model on a sample frame and pick the one with the best alpha quality.

    Scores based on: character should be opaque (alpha > 128) in roughly 15-65% of pixels.
    Too low = character removed. Too high = background kept.
    """
    try:
        from rembg import new_session, remove
    except ImportError:
        return _REMBG_MODELS[0]

    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        return _REMBG_MODELS[0]

    # Pick a frame from the middle (more representative than first/last)
    sample = frames[len(frames) // 2]
    img = Image.open(sample)

    best_model = _REMBG_MODELS[0]
    best_score = -1.0
    ideal_opaque = 0.35  # target: ~35% opaque for a character on transparent bg

    console.print(f"  [dim]Auto-selecting model (testing on {sample.name})...[/dim]")

    for model_name in _REMBG_MODELS:
        try:
            session = new_session(model_name)
            result = remove(img, session=session)
            alpha = np.array(result)[:, :, 3]
            opaque_ratio = np.count_nonzero(alpha > 128) / alpha.size

            # Score: how close to ideal opaque ratio (lower distance = better)
            distance = abs(opaque_ratio - ideal_opaque)
            score = 1.0 - distance

            console.print(f"    {model_name}: {opaque_ratio:.0%} opaque (score: {score:.2f})")

            if score > best_score:
                best_score = score
                best_model = model_name
        except Exception as e:
            console.print(f"    {model_name}: failed ({e})")
            continue

    console.print(f"  [green]Selected: {best_model}[/green]")
    return best_model


def remove_backgrounds(session: dict) -> dict:
    """Run background removal with green screen detection, model selection, and fallback.

    Pipeline per video:
    1. Detect green screen — if found, use chroma-key removal first
    2. Run rembg with auto-selected model (or on chroma-key output for green screen)
    3. Fall back to numpy if rembg unavailable
    4. Final green cleanup pass to catch residual green fringing

    Args:
        session: Session config dict.

    Returns:
        Updated session dict.
    """
    output_base = Path(session["output_dir"]) / "frames" / "nobg"

    for video_name, video_info in session["videos"].items():
        raw_dir = Path(session["output_dir"]) / "frames" / "raw" / Path(video_name).stem
        video_output = output_base / Path(video_name).stem

        console.print(f"\n[bold]Removing backgrounds from {video_name}...[/bold]")

        result = None
        is_greenscreen = _detect_green_screen(raw_dir)

        if is_greenscreen:
            console.print("  [green]Green screen detected[/green] — using chroma-key removal")

            # Stage 1: Chroma-key green removal
            result = remove_bg_greenscreen(str(raw_dir), str(video_output))

            # Stage 2: Run rembg on the chroma-key output to clean up remaining bg
            # (rembg works better when most of the green is already gone)
            best_model = _pick_best_model(raw_dir)
            try:
                # Use the chroma-key output as input for rembg
                rembg_result = remove_bg_rembg(
                    str(video_output), str(video_output), model=best_model,
                )
                if rembg_result.get("success"):
                    result = rembg_result
                    result["method"] = f"greenscreen+rembg_{best_model}"
            except Exception as e:
                console.print(f"  [dim]rembg refinement skipped: {e}[/dim]")
                result["method"] = "greenscreen"

            # Stage 3: Final green cleanup pass
            _cleanup_green_residue(video_output)
        else:
            # Non-green-screen: standard rembg pipeline
            best_model = _pick_best_model(raw_dir)

            try:
                result = remove_bg_rembg(str(raw_dir), str(video_output), model=best_model)
            except Exception as e:
                console.print(f"  [yellow]rembg ({best_model}) failed: {e}[/yellow]")

            # Fallback to numpy
            if not result or not result.get("success"):
                console.print("  [dim]Falling back to numpy method...[/dim]")
                result = remove_bg_numpy(str(raw_dir), str(video_output))

        # Update session
        video_info["nobg_frames"] = result.get("frames", [])
        video_info["nobg_frame_count"] = result.get("frame_count", 0)
        method = result.get("method", "unknown")
        if not method.startswith("greenscreen") and result.get("model"):
            method = f"rembg_{result['model']}"
        session["bg_removal_method"] = method

    return session
