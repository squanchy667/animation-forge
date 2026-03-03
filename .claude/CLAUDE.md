# Animation Forge — Project Conventions

## What This Is
CLI pipeline that converts AI-generated video files (.mp4/.mov) into Unity-ready 2D animation packages: transparent PNG spritesheets, AnimatorController scaffold, metadata, and import guide.

## Project Layout
```
/Users/ofek/Projects/Claude/AnimationForge/
├── animation-forge/               ← Code repo (this repo)
│   ├── .claude/CLAUDE.md          ← This file
│   ├── main.py                    # CLI entry point (v0.2.0, 8-phase pipeline)
│   ├── config/
│   │   ├── animation_types.json   # 14 animation type definitions
│   │   └── game_profiles/         # 4 game type presets
│   ├── phases/
│   │   ├── p_profile.py           # Phase 1: Game profile setup
│   │   ├── p0_bootstrap.py        # Phase 2: Video analysis + env check
│   │   ├── p1_questionnaire.py    # Phase 3: Interactive video→animation mapping
│   │   ├── p2_extract.py          # Phase 4: ffmpeg frame extraction
│   │   ├── p3_bg_removal.py       # Phase 5: rembg + numpy background removal
│   │   ├── p4_segmentation.py     # Phase 6: Frame range slicing per animation
│   │   ├── p_analyzer.py          # Phase 7: Vision-assisted frame validation
│   │   └── p5_export.py           # Phase 8: Spritesheet packing + package
│   ├── utils/
│   │   ├── game_profile.py        # Profile schema, validation, presets
│   │   ├── motion.py              # Pose signatures, motion/transparency analysis
│   │   ├── vision.py              # Claude Vision API helpers
│   │   ├── spritesheet.py         # PIL packing + resize utilities
│   │   ├── unity_export.py        # AnimatorController + C# params
│   │   └── session.py             # session_config.json read/write (schema v2)
│   └── templates/
│       ├── animator_controller.json.tmpl
│       └── import_guide.md.tmpl
│
└── animation-forge-docs/          ← Docs repo (GitBook-style)
    ├── README.md                  # Project overview
    ├── SUMMARY.md                 # Table of contents
    ├── PLAN.md                    # Architecture + phase outline
    ├── TASK_BOARD.md              # 21 tasks, 6 phases — all DONE
    ├── architecture/              # System overview, data flow
    ├── developer/                 # Setup guide, coding standards
    ├── product/                   # Features, usage guide
    ├── resources/
    │   ├── changelog.md           # Per-phase changelog
    │   ├── tech-stack.md
    │   └── known-issues.md
    ├── testing/                   # Test plans
    └── tasks/phase-{1..5}/        # Individual task specs (T001-T015)
```

## Stack
- **Language**: Python 3.10+ (type hints, pathlib)
- **CLI**: Click 8.1+
- **Terminal UI**: Rich 13+ (progress bars, tables, panels)
- **Video**: ffmpeg/ffprobe (system dependency)
- **BG Removal**: rembg 2.0+ (isnet-anime model) with numpy/scipy fallback
- **Pose Detection**: MediaPipe 0.10+ (optional)
- **Vision AI**: Anthropic Claude API (optional)
- **Image Processing**: Pillow 10+

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

# With profile preset (skips profile questionnaire)
python main.py run --video walk.mp4 --character "mage" --profile config/game_profiles/platformer_2d.json

# Skip optional phases
python main.py run --video walk.mp4 --character "mage" --skip-questionnaire --skip-analysis

# Resume
python main.py resume --session ./output/session_abc/session_config.json

# Preview only
python main.py preview --video input.mp4
```

## Commit Convention
- Format: `[Phase X] TXXX: Brief description`
- Branch: `feat/TXXX-task-name`
