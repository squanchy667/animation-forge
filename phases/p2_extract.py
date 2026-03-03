"""Phase 2 — Frame extraction via ffmpeg.

Extracts all frames from video files as PNGs for downstream processing.
"""

import json
import subprocess
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

console = Console()


def _probe_video(video_path: Path) -> dict:
    """Get video metadata via ffprobe (fps, duration, width, height, total_frames)."""
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

    # Find the video stream
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise RuntimeError(f"No video stream found in {video_path}")

    # Parse fps from r_frame_rate (e.g. "24/1" or "30000/1001")
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
        "width": width,
        "height": height,
        "total_frames": total_frames,
    }


def extract_frames(video_path: str, output_dir: str, fps: int | None = None) -> list[str]:
    """Extract frames from a video file using ffmpeg.

    Args:
        video_path: Path to input video file.
        output_dir: Directory for extracted frame PNGs.
        fps: Override extraction frame rate. If None, uses video's native fps.

    Returns:
        Sorted list of extracted frame file paths.
    """
    video_path = Path(video_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    # Probe video metadata
    probe = _probe_video(video_path)
    extract_fps = fps if fps is not None else probe["fps"]
    expected_frames = round(extract_fps * probe["duration"])

    console.print(f"  [dim]Video:[/dim] {video_path.name} ({probe['width']}x{probe['height']}, "
                  f"{probe['fps']}fps, {probe['duration']:.1f}s)")
    console.print(f"  [dim]Extracting at:[/dim] {extract_fps} fps → ~{expected_frames} frames expected")

    # Run ffmpeg
    output_pattern = str(output_dir / "frame_%04d.png")
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-r", str(extract_fps),
        "-y",  # overwrite existing
        output_pattern,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Filter stderr for error-relevant lines
        error_lines = [
            line for line in result.stderr.splitlines()
            if "Error" in line or "Invalid" in line
        ]
        error_msg = "\n".join(error_lines) if error_lines else result.stderr[-500:]
        raise RuntimeError(f"ffmpeg extraction failed:\n{error_msg}")

    # Collect extracted frames (sorted by name)
    frames = sorted(output_dir.glob("frame_*.png"))
    frame_paths = [str(f) for f in frames]
    actual_count = len(frame_paths)

    # Progress display (post-extraction since ffmpeg doesn't stream progress easily)
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan][Phase 3/6][/bold cyan] Frame Extraction"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn(f"[dim]{actual_count} frames[/dim]"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("extract", total=actual_count)
        progress.update(task, completed=actual_count)

    # Validate frame count
    if expected_frames > 0:
        deviation = abs(actual_count - expected_frames) / expected_frames
        if deviation > 0.05:
            console.print(
                f"  [yellow]Warning:[/yellow] Expected ~{expected_frames} frames, "
                f"got {actual_count} ({deviation:.0%} deviation)"
            )
        else:
            console.print(f"  [green]Extracted {actual_count} frames[/green] (within expected range)")
    else:
        console.print(f"  [green]Extracted {actual_count} frames[/green]")

    return frame_paths


def run_extraction(session: dict) -> dict:
    """Extract frames for all videos in the session.

    Updates session with video metadata and frame paths.

    Args:
        session: Session config dict with 'videos' containing video paths.

    Returns:
        Updated session dict.
    """
    output_base = Path(session["output_dir"]) / "frames" / "raw"

    # FPS priority: CLI --fps > game_profile.extract_fps > video native
    cli_fps_override = session.get("extract_fps")
    profile = session.get("game_profile", {})
    profile_fps = profile.get("extract_fps") if profile else None

    for video_name, video_info in session["videos"].items():
        video_path = video_info["path"]
        video_output = output_base / Path(video_name).stem

        console.print(f"\n[bold]Extracting frames from {video_name}...[/bold]")

        # Probe for metadata
        probe = _probe_video(Path(video_path))
        video_info.update({
            "fps": probe["fps"],
            "duration": probe["duration"],
            "total_frames": probe["total_frames"],
            "width": probe["width"],
            "height": probe["height"],
        })

        # FPS priority chain
        if cli_fps_override:
            use_fps = cli_fps_override
            fps_source = "CLI --fps"
        elif profile_fps:
            use_fps = profile_fps
            fps_source = "game profile"
        else:
            use_fps = probe["fps"]
            fps_source = "video native"
        console.print(f"  [dim]FPS source:[/dim] {fps_source} ({use_fps} fps)")

        # Extract
        frame_paths = extract_frames(
            video_path=video_path,
            output_dir=str(video_output),
            fps=use_fps,
        )

        video_info["extracted_frames"] = frame_paths
        video_info["extracted_frame_count"] = len(frame_paths)
        # Update total_frames to match actual extracted count
        video_info["total_frames"] = len(frame_paths)

    return session
