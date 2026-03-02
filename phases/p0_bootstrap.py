"""Phase 0 — Bootstrap & environment check.

Validates system dependencies, probes input videos, and samples representative frames.
"""

import base64
import json
import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


# ── Environment Checks ───────────────────────────────────────────────────────


def check_ffmpeg() -> str | None:
    """Check ffmpeg/ffprobe availability. Returns version string or None."""
    try:
        result = subprocess.run(
            ["ffprobe", "-version"], capture_output=True, text=True
        )
        if result.returncode == 0:
            version_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
            return version_line
    except FileNotFoundError:
        pass
    return None


def check_rembg() -> bool:
    """Check if rembg is importable."""
    try:
        from rembg import remove  # noqa: F401
        return True
    except ImportError:
        return False


def check_mediapipe() -> bool:
    """Check if mediapipe is importable."""
    try:
        import mediapipe  # noqa: F401
        return True
    except ImportError:
        return False


def check_anthropic() -> bool:
    """Check if anthropic SDK is importable and API key is set."""
    try:
        import anthropic  # noqa: F401
        import os
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    except ImportError:
        return False


def _print_env_status() -> dict[str, bool]:
    """Print Rich-formatted environment status. Returns availability dict."""
    ffmpeg_version = check_ffmpeg()
    has_rembg = check_rembg()
    has_mediapipe = check_mediapipe()
    has_anthropic = check_anthropic()

    console.print("\n[bold]Environment Check[/bold]")

    checks = [
        ("ffmpeg/ffprobe", ffmpeg_version is not None, ffmpeg_version or "not found"),
        ("rembg", has_rembg, "available" if has_rembg else "not installed (numpy fallback will be used)"),
        ("mediapipe", has_mediapipe, "available" if has_mediapipe else "not installed (optional)"),
        ("anthropic SDK", has_anthropic, "available + API key set" if has_anthropic else "not configured (optional)"),
    ]

    from rich.text import Text

    for name, ok, detail in checks:
        icon = "[green]✓[/green]" if ok else "[yellow]○[/yellow]"
        # Build line safely — detail may contain brackets that break Rich markup
        line = Text("  ")
        line.append_text(Text.from_markup(icon))
        line.append(" ")
        label = f"{name}: {detail}"
        line.append(label, style="dim" if not ok else "")
        console.print(line)

    if ffmpeg_version is None:
        console.print("\n  [bold red]Error:[/bold red] ffmpeg is required. Install it:")
        console.print("    macOS:  [cyan]brew install ffmpeg[/cyan]")
        console.print("    Ubuntu: [cyan]sudo apt install ffmpeg[/cyan]")
        raise RuntimeError("ffmpeg not found — cannot continue")

    return {
        "ffmpeg": ffmpeg_version is not None,
        "rembg": has_rembg,
        "mediapipe": has_mediapipe,
        "anthropic": has_anthropic,
    }


# ── Video Probing ────────────────────────────────────────────────────────────


def probe_video(video_path: str) -> dict:
    """Probe a video file for metadata via ffprobe.

    Args:
        video_path: Path to video file.

    Returns:
        Dict with fps, duration, total_frames, width, height.
    """
    video_path = Path(video_path).resolve()
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {video_path}: {result.stderr.strip()}")

    data = json.loads(result.stdout)

    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise RuntimeError(f"No video stream found in {video_path}")

    # Parse fps from r_frame_rate fraction (e.g. "24/1", "30000/1001")
    r_frame_rate = video_stream.get("r_frame_rate", "24/1")
    num, den = r_frame_rate.split("/")
    fps = round(int(num) / int(den))

    duration = float(data.get("format", {}).get("duration", 0))
    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    total_frames = int(video_stream.get("nb_frames", 0)) or round(fps * duration)

    return {
        "fps": fps,
        "duration": duration,
        "total_frames": total_frames,
        "width": width,
        "height": height,
    }


# ── Frame Sampling ───────────────────────────────────────────────────────────


def sample_frames(video_path: str, output_dir: str, count: int = 5) -> list[str]:
    """Extract N evenly-spaced frames from a video using ffmpeg -ss seeking.

    Args:
        video_path: Path to video file.
        output_dir: Directory for sampled frame PNGs.
        count: Number of frames to sample.

    Returns:
        List of sampled frame paths.
    """
    video_path = Path(video_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    probe = probe_video(str(video_path))
    duration = probe["duration"]

    if duration <= 0:
        return []

    sampled = []
    for i in range(count):
        # Evenly space across duration
        timestamp = (i / max(count - 1, 1)) * duration if count > 1 else duration / 2
        out_path = output_dir / f"sample_{i:04d}.png"

        cmd = [
            "ffmpeg",
            "-ss", f"{timestamp:.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-y",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and out_path.exists():
            sampled.append(str(out_path))

    return sampled


# ── Orchestrator ─────────────────────────────────────────────────────────────


def run_bootstrap(session: dict, video_paths: list[str]) -> dict:
    """Run bootstrap phase: env check → probe videos → sample frames → update session.

    Args:
        session: Session config dict.
        video_paths: List of input video file paths.

    Returns:
        Updated session dict.
    """
    # 1. Environment check
    env = _print_env_status()

    # 2. Probe all videos and display info table
    table = Table(title="Input Videos", border_style="cyan")
    table.add_column("Video", style="cyan")
    table.add_column("Resolution")
    table.add_column("FPS", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Frames", justify="right")

    sample_base = Path(session["output_dir"]) / "frames" / "samples"

    for video_path in video_paths:
        vpath = Path(video_path).resolve()
        video_name = vpath.name

        console.print(f"\n[bold]Analyzing {video_name}...[/bold]")
        probe = probe_video(str(vpath))

        table.add_row(
            video_name,
            f"{probe['width']}x{probe['height']}",
            str(probe["fps"]),
            f"{probe['duration']:.1f}s",
            str(probe["total_frames"]),
        )

        # 3. Sample frames
        sample_dir = sample_base / vpath.stem
        sampled = sample_frames(str(vpath), str(sample_dir))

        # 4. Update session
        session["videos"][video_name] = {
            "path": str(vpath),
            "fps": probe["fps"],
            "duration": probe["duration"],
            "total_frames": probe["total_frames"],
            "width": probe["width"],
            "height": probe["height"],
            "sampled_frames": sampled,
            "vision_description": None,
        }

    console.print()
    console.print(table)

    # 5. Vision analysis (optional)
    if env.get("anthropic"):
        try:
            from utils.vision import describe_character_from_frames, get_vision_client

            client = get_vision_client()
            if client:
                for video_name, video_info in session["videos"].items():
                    if video_info.get("sampled_frames"):
                        console.print(f"\n[dim]Analyzing {video_name} with Claude Vision...[/dim]")
                        desc = describe_character_from_frames(
                            video_info["sampled_frames"], client
                        )
                        if desc:
                            video_info["vision_description"] = desc
                            console.print(f"  [dim]{desc}[/dim]")
        except Exception as e:
            console.print(f"  [yellow]Vision analysis skipped: {e}[/yellow]")

    return session
