# Animation Forge Conventions Skill

## Python Conventions
- Python 3.10+ with native type hints: `list[str]`, `dict[str, Any]`, `X | None`
- `pathlib.Path` for all file operations
- `from __future__ import annotations` not needed (3.10+)

## Error Handling
- Wrap all phase calls in try/except
- Show errors via `rich.console.Console().print_exception()`
- Never show raw tracebacks to user
- Offer retry on phase failure: `"Retry this phase? [Y/n]"`
- Optional deps (rembg, mediapipe, anthropic) always in try/except import

## Progress Reporting
```python
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    TimeElapsedColumn(),
    TimeRemainingColumn(),
) as progress:
    task = progress.add_task("Processing frames", total=frame_count)
    for frame in frames:
        # process
        progress.advance(task)
```

## Session Pattern
```python
from utils.session import load_session, save_session, new_session

# Create new session
session = new_session(output_dir, character_name)

# Modify and save
session["animation_map"]["walk"] = {...}
save_session(session, session_path)

# Resume
session = load_session(session_path)
```

## Frame Naming
- Always 1-indexed, 4-digit zero-padded: `frame_0001.png`
- Never `frame_0000.png`
- Spritesheet metadata uses 0-indexed cells

## BG Removal Priority
1. rembg `isnet-anime` (default, best for AI art)
2. rembg `u2net_human_seg` (realistic humans)
3. rembg `u2net` (general)
4. numpy fallback (always available)

## Key Design Decisions (Do Not Change)
- Separate spritesheet per animation (not combined atlas)
- Fixed-cell grid layout (not packed)
- Bottom-center pivot (0.5, 0.0)
- session_config.json for persistence
- numpy fallback always available
- Per-phase error recovery
