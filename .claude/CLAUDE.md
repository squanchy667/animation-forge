# Animation Forge — Project Conventions

## What This Is
CLI pipeline that converts AI-generated video files (.mp4/.mov) into Unity-ready 2D animation packages: transparent PNG spritesheets, AnimatorController scaffold, metadata, and import guide.

## Stack
- **Language**: Python 3.10+ (type hints, pathlib)
- **CLI**: Click 8.1+
- **Terminal UI**: Rich 13+ (progress bars, tables, panels)
- **Video**: ffmpeg/ffprobe (system dependency)
- **BG Removal**: rembg 2.0+ (isnet-anime model) with numpy/scipy fallback
- **Pose Detection**: MediaPipe 0.10+ (optional)
- **Vision AI**: Anthropic Claude API (optional)
- **Image Processing**: Pillow 10+

## Structure
```
animation-forge/
├── main.py                    # CLI entry point (Click)
├── requirements.txt           # Python dependencies
├── config/
│   └── animation_types.json   # 14 animation type definitions
├── phases/
│   ├── p0_bootstrap.py        # Video analysis + env check
│   ├── p1_questionnaire.py    # Interactive video→animation mapping
│   ├── p2_extract.py          # ffmpeg frame extraction
│   ├── p3_bg_removal.py       # rembg + numpy background removal
│   ├── p4_segmentation.py     # Frame range slicing per animation
│   └── p5_export.py           # Spritesheet packing + Unity package
├── utils/
│   ├── vision.py              # Claude API helpers
│   ├── spritesheet.py         # PIL packing utilities
│   ├── unity_export.py        # AnimatorController + C# params
│   └── session.py             # session_config.json read/write
└── templates/
    ├── animator_controller.json.tmpl
    └── import_guide.md.tmpl
```

## Key Patterns

### Paths
- Use `pathlib.Path` everywhere — never string concatenation
- All output paths must be absolute
- Create dirs with `Path.mkdir(parents=True, exist_ok=True)`

### Error Handling
- Never crash silently — use `rich.console.Console().print_exception()`
- Phase failures are recoverable — save state, show error, offer retry
- ffmpeg errors: capture stderr, show "Error" and "Invalid" lines only
- Optional deps (`rembg`, `mediapipe`, `anthropic`): always try/except import

### Progress
- Every phase uses `rich.progress.Progress` with task name, counter, elapsed, ETA

### Frame Numbering
- Raw + segment frames: `frame_0001.png` (1-indexed, 4-digit zero-padded)
- Spritesheet cells: 0-indexed in metadata
- animation_map ranges: 0-indexed

### Session Persistence
- `session_config.json` tracks everything
- Saved after each phase completes
- Pipeline can resume from any phase

## Commands
```bash
# Full pipeline
python main.py run --video walk.mp4 --video attack.mp4 --character "mage"

# Resume
python main.py resume --session ./output/session_abc/session_config.json

# Preview only
python main.py preview --video input.mp4
```

## Docs Repo
Task board and specs: `../animation-forge-docs/`
- `TASK_BOARD.md` — 15 tasks, 5 phases
- `tasks/phase-{1..5}/` — Individual task specs

## Commit Convention
- Format: `[Phase X] TXXX: Brief description`
- Branch: `feat/TXXX-task-name`
