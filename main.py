"""Animation Forge — CLI entry point.

Converts AI-generated video files into Unity-ready 2D animation packages.
"""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from utils.session import load_session, mark_phase_complete, new_session, save_session

console = Console()

VERSION = "0.1.0"

PHASE_NAMES = [
    "Bootstrap & Analysis",
    "Questionnaire",
    "Frame Extraction",
    "Background Removal",
    "Segmentation",
    "Export & Package",
]

PHASE_IDS = ["p0", "p1", "p2", "p3", "p4", "p5"]


# ── UI Helpers ──────────────────────────────────────────────────────────────


def show_banner() -> None:
    """Display ASCII banner with Rich styling."""
    banner = Text()
    banner.append("Animation Forge", style="bold magenta")
    banner.append(f"  v{VERSION}", style="dim")
    panel = Panel(
        banner,
        title="[bold white]⚒ Animation Forge[/bold white]",
        subtitle=f"[dim]v{VERSION}[/dim]",
        border_style="magenta",
        padding=(1, 4),
    )
    console.print(panel)


def show_error(message: str, exception: BaseException | None = None) -> None:
    """Display error in red-bordered panel. Never shows raw tracebacks."""
    error_text = Text(message, style="bold red")
    panel = Panel(
        error_text,
        title="[bold red]Error[/bold red]",
        border_style="red",
        padding=(1, 2),
    )
    console.print(panel)
    if exception:
        console.print_exception(max_frames=5)


def show_completion_summary(session: dict, zip_path: str | None = None) -> None:
    """Display final completion summary box with output file paths and sizes."""
    lines = [
        f"[bold green]Character:[/bold green] {session.get('character_name', 'unknown')}",
        f"[bold green]Animations:[/bold green] {len(session.get('animation_map', {}))}",
        f"[bold green]BG Method:[/bold green] {session.get('bg_removal_method', 'N/A')}",
        f"[bold green]Output:[/bold green] {session.get('output_dir', 'N/A')}",
        f"[bold green]Phases:[/bold green] {', '.join(session.get('phases_completed', []))}",
    ]
    if zip_path:
        zip_size = Path(zip_path).stat().st_size / (1024 * 1024)
        lines.append(f"[bold green]Package:[/bold green] {zip_path} ({zip_size:.2f} MB)")

    panel = Panel(
        "\n".join(lines),
        title="[bold green]Pipeline Complete[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
    console.print(panel)


def _parse_phases(phases_str: str | None) -> set[int] | None:
    """Parse --phases option like '1-3' or '2,4,6' into a set of 1-indexed phase numbers."""
    if not phases_str:
        return None

    selected = set()
    for part in phases_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            selected.update(range(int(start), int(end) + 1))
        else:
            selected.add(int(part))
    return selected


# ── Phase Runners ────────────────────────────────────────────────────────────


def _run_phase(phase_num: int, session: dict, session_path: Path, **kwargs) -> dict:
    """Run a single phase with error handling and retry.

    Args:
        phase_num: 1-indexed phase number.
        session: Session config dict.
        session_path: Path to session_config.json for saving.
        **kwargs: Extra args (video_paths, skip_questionnaire).

    Returns:
        Updated session dict.
    """
    phase_id = PHASE_IDS[phase_num - 1]
    phase_name = PHASE_NAMES[phase_num - 1]

    if phase_id in session.get("phases_completed", []):
        console.print(f"\n[dim]Phase {phase_num} ({phase_name}) — already complete, skipping[/dim]")
        return session

    console.print(f"\n[bold cyan]── Phase {phase_num}/6: {phase_name} ──[/bold cyan]")

    while True:
        try:
            if phase_num == 1:
                from phases.p0_bootstrap import run_bootstrap
                session = run_bootstrap(session, kwargs.get("video_paths", []))

            elif phase_num == 2:
                if kwargs.get("skip_questionnaire"):
                    console.print("  [dim]Skipping questionnaire (--skip-questionnaire)[/dim]")
                else:
                    from phases.p1_questionnaire import run_questionnaire
                    session = run_questionnaire(session)

            elif phase_num == 3:
                from phases.p2_extract import run_extraction
                session = run_extraction(session)

            elif phase_num == 4:
                from phases.p3_bg_removal import remove_backgrounds
                session = remove_backgrounds(session)

            elif phase_num == 5:
                from phases.p4_segmentation import segment_animations
                segments = segment_animations(session)
                session["segments"] = {k: v for k, v in segments.items()}

            elif phase_num == 6:
                from phases.p5_export import assemble_output_package, pack_all_spritesheets
                spritesheets = pack_all_spritesheets(session)
                session["spritesheets"] = {
                    k: {sk: sv for sk, sv in v.items() if sk != "frames"}
                    for k, v in spritesheets.items()
                }
                zip_path = assemble_output_package(session, spritesheets)
                session["zip_path"] = zip_path

            # Mark complete and save
            session = mark_phase_complete(session, phase_id)
            save_session(session, session_path)
            console.print(f"  [green]Phase {phase_num} complete.[/green]")
            break

        except Exception as e:
            show_error(f"Phase {phase_num} ({phase_name}) failed: {e}", exception=e)
            if not click.confirm("  Retry this phase?", default=True):
                raise

    return session


# ── Pipeline Orchestration ─────────────────────────────────────────────────


def run_pipeline(
    videos: tuple[str, ...],
    character: str,
    phases: str | None,
    skip_questionnaire: bool,
    fps: int | None = None,
) -> None:
    """Orchestrate the full pipeline: P0 → P1 → P2 → P3 → P4 → P5."""
    show_banner()

    # Create output directory and session
    output_dir = Path.cwd() / "output" / f"session_{character}"
    output_dir.mkdir(parents=True, exist_ok=True)

    session = new_session(str(output_dir), character)

    # Set extraction FPS override if provided
    if fps:
        session["extract_fps"] = fps

    # Pre-populate videos in session
    for v in videos:
        vpath = Path(v).resolve()
        session["videos"][vpath.name] = {"path": str(vpath)}

    session_path = output_dir / "session_config.json"
    save_session(session, session_path)

    console.print(f"[dim]Session:[/dim] {session_path}")
    console.print(f"[dim]Videos:[/dim] {', '.join(str(v) for v in videos)}")
    console.print(f"[dim]Character:[/dim] {character}")

    selected_phases = _parse_phases(phases)

    for phase_num in range(1, 7):
        if selected_phases and phase_num not in selected_phases:
            console.print(f"\n[dim]Phase {phase_num} ({PHASE_NAMES[phase_num - 1]}) — skipped (--phases)[/dim]")
            continue

        session = _run_phase(
            phase_num,
            session,
            session_path,
            video_paths=[str(Path(v).resolve()) for v in videos],
            skip_questionnaire=skip_questionnaire,
        )

    show_completion_summary(session, session.get("zip_path"))


def resume_pipeline(session_path: Path) -> None:
    """Resume pipeline from a saved session file."""
    show_banner()

    session = load_session(session_path)
    session_path = Path(session_path).resolve()

    completed = set(session.get("phases_completed", []))
    console.print(f"[dim]Resuming session:[/dim] {session.get('session_id', '?')}")
    console.print(f"[dim]Character:[/dim] {session.get('character_name', '?')}")
    console.print(f"[dim]Completed:[/dim] {', '.join(sorted(completed)) or 'none'}")

    video_paths = [info["path"] for info in session.get("videos", {}).values()]

    for phase_num in range(1, 7):
        phase_id = PHASE_IDS[phase_num - 1]
        if phase_id in completed:
            continue

        session = _run_phase(
            phase_num,
            session,
            session_path,
            video_paths=video_paths,
        )

    show_completion_summary(session, session.get("zip_path"))


def preview_video(video_path: Path) -> None:
    """Preview video: run bootstrap only (frame sampling, no export)."""
    show_banner()

    output_dir = Path.cwd() / "output" / f"preview_{video_path.stem}"
    output_dir.mkdir(parents=True, exist_ok=True)

    session = new_session(str(output_dir), video_path.stem)
    vpath = video_path.resolve()
    session["videos"][vpath.name] = {"path": str(vpath)}

    from phases.p0_bootstrap import run_bootstrap
    session = run_bootstrap(session, [str(vpath)])

    console.print("\n[bold green]Preview complete.[/bold green]")
    console.print(f"[dim]Sampled frames in:[/dim] {output_dir / 'frames' / 'samples'}")


# ── CLI Commands ────────────────────────────────────────────────────────────


@click.group()
@click.version_option(VERSION, prog_name="animation-forge")
def cli() -> None:
    """Animation Forge — Convert AI-generated videos into Unity-ready 2D sprite packages."""


@cli.command()
@click.option("--video", "-v", multiple=True, required=True, type=click.Path(exists=True), help="Input video file(s) (.mp4/.mov)")
@click.option("--character", "-c", required=True, help="Character name (used in output naming)")
@click.option("--phases", "-p", default=None, help="Run specific phases (e.g. '1-3' or '2,4')")
@click.option("--skip-questionnaire", is_flag=True, default=False, help="Skip interactive questionnaire")
@click.option("--fps", type=int, default=None, help="Override extraction FPS (lower = fewer frames, snappier animations)")
def run(video: tuple[str, ...], character: str, phases: str | None, skip_questionnaire: bool, fps: int | None) -> None:
    """Run the full animation extraction pipeline."""
    try:
        run_pipeline(video, character, phases, skip_questionnaire, fps)
    except Exception as e:
        show_error(str(e), exception=e)


@cli.command()
@click.option("--session", "-s", required=True, type=click.Path(exists=True), help="Path to session_config.json")
def resume(session: str) -> None:
    """Resume an interrupted pipeline session."""
    try:
        resume_pipeline(Path(session))
    except Exception as e:
        show_error(str(e), exception=e)


@cli.command()
@click.option("--video", "-v", required=True, type=click.Path(exists=True), help="Video file to preview")
def preview(video: str) -> None:
    """Preview video frame samples without exporting."""
    try:
        preview_video(Path(video))
    except Exception as e:
        show_error(str(e), exception=e)


if __name__ == "__main__":
    cli()
