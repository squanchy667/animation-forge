"""Animation Forge — CLI entry point.

Converts AI-generated video files into Unity-ready 2D animation packages.
"""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.text import Text

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


def show_phase_progress(phase_index: int, total: int = 6) -> Progress:
    """Create a Rich Progress bar for phase tracking."""
    return Progress(
        SpinnerColumn(),
        TextColumn(f"[bold cyan][Phase {phase_index}/{total}][/bold cyan] {PHASE_NAMES[phase_index - 1]}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )


def show_completion_summary(session: dict) -> None:
    """Display final completion summary box."""
    lines = [
        f"[bold green]Character:[/bold green] {session.get('character_name', 'unknown')}",
        f"[bold green]Animations:[/bold green] {len(session.get('animation_map', {}))}",
        f"[bold green]Output:[/bold green] {session.get('output_dir', 'N/A')}",
        f"[bold green]Phases:[/bold green] {', '.join(session.get('phases_completed', []))}",
    ]
    panel = Panel(
        "\n".join(lines),
        title="[bold green]Pipeline Complete[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
    console.print(panel)


# ── Pipeline Stubs ──────────────────────────────────────────────────────────


def run_pipeline(videos: tuple[str, ...], character: str, phases: str | None, skip_questionnaire: bool) -> None:
    """Stub: orchestrate the full pipeline. Wired in T014."""
    show_banner()
    console.print(f"[dim]Videos:[/dim] {', '.join(videos)}")
    console.print(f"[dim]Character:[/dim] {character}")

    for i, name in enumerate(PHASE_NAMES, 1):
        with show_phase_progress(i) as progress:
            task = progress.add_task(name, total=100)
            progress.update(task, completed=100)
        console.print(f"  [dim]Phase {i} — {name}: [yellow]stub (not yet wired)[/yellow][/dim]")

    console.print("\n[bold green]All phases complete (stubs).[/bold green]")


def resume_pipeline(session_path: Path) -> None:
    """Stub: resume pipeline from session file. Wired in T014."""
    show_banner()
    console.print(f"[dim]Resuming from:[/dim] {session_path}")
    console.print("[yellow]Resume not yet wired — will be implemented in T014.[/yellow]")


def preview_video(video_path: Path) -> None:
    """Stub: preview video frame samples. Wired in T014."""
    show_banner()
    console.print(f"[dim]Preview:[/dim] {video_path}")
    console.print("[yellow]Preview not yet wired — will be implemented in T014.[/yellow]")


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
def run(video: tuple[str, ...], character: str, phases: str | None, skip_questionnaire: bool) -> None:
    """Run the full animation extraction pipeline."""
    try:
        run_pipeline(video, character, phases, skip_questionnaire)
    except Exception as e:
        show_error(str(e), exception=e)
        if click.confirm("Retry this phase?", default=True):
            run_pipeline(video, character, phases, skip_questionnaire)


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
