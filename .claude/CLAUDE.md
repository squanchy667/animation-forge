# Animation Forge — Project Conventions

## What This Is
CLI pipeline that converts AI-generated video files (.mp4/.mov) into Unity-ready 2D animation packages: transparent PNG spritesheets, AnimatorController scaffold, metadata, and import guide.

**9-phase pipeline**: profile → bootstrap → questionnaire → extract → bg removal → segmentation → analysis → **game refinement** → export

## Project Layout
```
/Users/ofek/Projects/Claude/AnimationForge/
├── animation-forge/               ← Code repo (this repo)
│   ├── .claude/CLAUDE.md          ← This file
│   ├── main.py                    # CLI entry point (v0.2.0, 9-phase pipeline)
│   ├── refine_v4.py               # Legacy standalone refinement (superseded by Phase 8)
│   ├── config/
│   │   ├── animation_types.json   # 14 animation type definitions (locomotion/combat/utility)
│   │   ├── game_profiles/         # 5 game type presets (platformer, roguelite, rpg, iso, card)
│   │   │   ├── platformer_2d.json # 128x128, hd_sprites, refinement: platformer_2d
│   │   │   ├── roguelite_2d.json  # 128x256, painted, refinement: platformer_2d
│   │   │   ├── top_down_rpg.json  # 64x64, pixel_art, refinement: null (skipped)
│   │   │   ├── isometric.json     # 128x128, hd_sprites, refinement: null (skipped)
│   │   │   └── card_game.json     # 256x256, painted, refinement: null (skipped)
│   │   └── refinement_profiles/   # Per-game-type refinement configs
│   │       └── platformer_2d.json # 14 animation configs (frame counts, action ranges, thresholds)
│   ├── phases/
│   │   ├── p_profile.py           # Phase 1: Game profile setup (interactive or --profile)
│   │   ├── p0_bootstrap.py        # Phase 2: Video analysis + env check (ffprobe, deps)
│   │   ├── p1_questionnaire.py    # Phase 3: Interactive video→animation mapping (Rich UI + Vision)
│   │   ├── p2_extract.py          # Phase 4: ffmpeg frame extraction (all videos → frames/)
│   │   ├── p3_bg_removal.py       # Phase 5: rembg + numpy background removal → frames/nobg/
│   │   ├── p4_segmentation.py     # Phase 6: Frame range slicing per animation
│   │   ├── p_analyzer.py          # Phase 7: Vision-assisted frame validation (optional)
│   │   ├── p6_refine.py           # Phase 8: Game refinement — auto for 2d_platformer/roguelite
│   │   └── p5_export.py           # Phase 9: Spritesheet packing + ZIP package
│   ├── utils/
│   │   ├── game_profile.py        # Profile schema, validation, presets, budget multipliers
│   │   ├── motion.py              # Pose signatures, motion/transparency analysis
│   │   ├── vision.py              # Claude Vision API helpers (claude-sonnet-4-6)
│   │   ├── spritesheet.py         # PIL grid packing, resize, PPU calculation
│   │   ├── unity_export.py        # AnimatorController JSON + C# params generation
│   │   └── session.py             # session_config.json read/write (schema v2, atomic)
│   └── templates/
│       ├── animator_controller.json.tmpl
│       └── import_guide.md.tmpl
│
└── animation-forge-docs/          ← Docs repo (GitBook-style)
    ├── README.md, SUMMARY.md, PLAN.md, TASK_BOARD.md
    ├── architecture/              # System overview, data flow
    ├── developer/                 # Setup guide, coding standards
    ├── product/                   # Features, usage guide
    ├── resources/                 # Tech stack, changelog, known issues
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
- **Image Processing**: Pillow 10+, numpy, scipy

## Pipeline Phases

| # | Phase | ID | Key Function | Skippable |
|---|-------|----|----|------------|
| 1 | Game Profile Setup | `p_profile` | `run_profile_setup()` | `--profile` flag |
| 2 | Bootstrap & Analysis | `p0` | `run_bootstrap()` | No |
| 3 | Questionnaire | `p1` | `run_questionnaire()` | `--skip-questionnaire` |
| 4 | Frame Extraction | `p2` | `run_extraction()` | No |
| 5 | Background Removal | `p3` | `remove_backgrounds()` | No |
| 6 | Segmentation | `p4` | `segment_animations()` | No |
| 7 | Frame Analysis | `p_analyze` | `run_frame_analysis()` | `--skip-analysis` |
| 8 | Game Refinement | `p6_refine` | `run_refinement()` | `--skip-refinement` / auto |
| 9 | Export & Package | `p5` | `pack_all_spritesheets()` | No |

## Phase 8: Game Refinement

### What It Does
Transforms raw pipeline frames into game-ready sprites. Solves three problems the raw pipeline can't:
1. **Too many frames** — AI videos have 60-145 frames per animation; games need 4-8
2. **Inconsistent character sizes** — different videos produce different scales/positions
3. **Wind-up frames** — AI videos often start with idle poses before action begins

### How It Works
1. **Global bounding box** — scans ALL nobg frames across ALL animations to find the character's maximum extent, ensuring consistent scale
2. **Motion-aware keypose selection** — computes cumulative motion between frames, picks frames at evenly-spaced motion milestones (not evenly-spaced time). High-motion segments get more frames, still segments get fewer
3. **Per-frame cleanup** — white smoke kill (saturation+value thresholds) → binary alpha → crop to global bbox → resize+sharpen to target canvas → final alpha clean
4. **Consistent output** — all frames are exactly `canvas.width` x `canvas.height` (e.g., 128x256), bottom-aligned, with UnsharpMask applied after downscale

### Auto-Activation
Phase 8 runs automatically when the game profile has `"refinement_profile"` set:
- `roguelite_2d.json` → `"refinement_profile": "platformer_2d"` → auto-activates
- `platformer_2d.json` → `"refinement_profile": "platformer_2d"` → auto-activates
- `top_down_rpg.json` → `"refinement_profile": null` → skipped
- `isometric.json` → `"refinement_profile": null` → skipped
- `card_game.json` → `"refinement_profile": null` → skipped
- `--skip-refinement` flag overrides auto-activation

### Refinement Profiles
Stored in `config/refinement_profiles/{name}.json`. Each profile defines:
- `canvas` — output frame size (e.g., 128x256)
- `normalize_resolution` — common resolution for processing (e.g., 784x1168)
- `fps` — playback FPS
- `animations` — per-animation config:
  - `target_frames` — final frame count (e.g., idle=6, walk=8, jump=5)
  - `action_start` / `action_end` — frame range with actual motion (1-indexed)
  - `loop` — whether animation loops
  - `white_kill` — `[saturation_thresh, value_thresh]` for smoke removal
  - `alpha_thresh` — binary alpha cutoff (alpha > thresh → 255, else → 0)
  - `trim_pct` — extra horizontal trim percentage

### Adding New Refinement Profiles
To support a new game type:
1. Create `config/refinement_profiles/{game_type}.json` with per-animation configs
2. Add `"refinement_profile": "{game_type}"` to the corresponding game profile
3. Phase 8 auto-loads the profile and applies it

### Session Keys Added by Phase 8
- `session["refined_frames"]` — `{anim_id: {frame_count, loop, category, frames_dir}}`
- `session["global_bbox"]` — `[x0, y0, x1, y1]` cached for re-runs
- `session["refinement_canvas"]` — `{width, height}` of the output canvas

### Phase 9 Awareness
When `session["refined_frames"]` exists, the export phase (Phase 9):
- Uses `frames/refined/{anim_id}/` instead of segmented/nobg frames
- Skips resize (refined frames are already at target canvas size)
- Gets loop flags and FPS from refinement output instead of animation_map

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
- Raw + segment + refined frames: `frame_0001.png` (1-indexed, 4-digit zero-padded)
- Spritesheet cells: 0-indexed in metadata
- animation_map ranges: 0-indexed
- Refinement `action_start`/`action_end`: 1-indexed in profile, converted to 0-indexed in code

### Session Persistence
- `session_config.json` tracks everything (schema v2, atomic JSON write)
- Saved after each phase completes
- Pipeline can resume from any phase via `python main.py resume`
- Phase IDs in `phases_completed`: `p_profile, p0, p1, p2, p3, p4, p_analyze, p6_refine, p5`

### Output Directory Structure
```
output/session_{character}/
├── session_config.json          # Pipeline state (resumable)
├── game_profile.json            # Copy of loaded profile
├── frames/
│   ├── samples/                 # Phase 2: ffprobe sample frames
│   ├── raw/{video_stem}/        # Phase 4: extracted frames
│   ├── nobg/{video_stem}/       # Phase 5: background-removed frames
│   ├── animations/{anim_id}/    # Phase 6: segmented frame ranges
│   └── refined/{anim_id}/       # Phase 8: game-ready refined frames
├── export/Sprites/              # Phase 9: packed spritesheets (working dir)
├── {character}_animations/      # Phase 9: final package
│   ├── Sprites/*.png            # Spritesheets (e.g., yellow_idle.png)
│   ├── Animator/                # Unity AnimatorController + C# params
│   ├── metadata.json            # Machine-readable export metadata
│   └── IMPORT_GUIDE.md          # Human-readable import steps
└── {character}_animations.zip   # Phase 9: final deliverable
```

## Commands
```bash
# Full pipeline (all 9 phases)
python main.py run --video walk.mp4 --video attack.mp4 --character "mage"

# With profile preset (skips Phase 1 questionnaire)
python main.py run --video walk.mp4 --character "mage" --profile config/game_profiles/roguelite_2d.json

# Skip optional phases
python main.py run --video walk.mp4 --character "mage" --skip-questionnaire --skip-analysis --skip-refinement

# Run specific phases only (1-indexed)
python main.py run --video walk.mp4 --character "mage" --phases "8,9"

# Resume from last completed phase
python main.py resume --session ./output/session_abc/session_config.json

# Preview only (bootstrap, no export)
python main.py preview --video input.mp4
```

### Typical Production Run (AI-generated character videos)
```bash
python main.py run \
  --video idle.mp4 --video walk.mp4 --video run.mp4 \
  --video jump.mp4 --video fall.mp4 --video land.mp4 \
  --video attack1.mp4 --video attack2.mp4 \
  --video hurt.mp4 --video death.mp4 \
  --character "character_name" \
  --profile config/game_profiles/roguelite_2d.json \
  --skip-questionnaire --skip-analysis
```

## Processed Characters

### yellow (Tomato Fighters roguelite)
- **14 animations**: idle(6), walk(8), run(8), jump(5), fall(4), land(4), dash(5), attack_1(6), attack_2(8), block(4), guard(6), hurt(4), death(8), kneel(6)
- **82 total frames**, 128x256 canvas, 12 fps, 2.01 MB ZIP
- Profile: `roguelite_2d.json` → refinement: `platformer_2d`
- Source videos: `/Users/ofek/Downloads/yellow/`
- Output: `output/session_yellow/yellow_animations.zip`

## Lessons Learned
- **rembg > chroma key** for AI-generated green screen video — scene elements aren't pure green
- **Skip first 4 frames** of AI video (green screen fade-in artifact)
- **3-layer cleanup** for AI sprites: green kill → low-saturation smoke kill → outer edge band (3px erosion)
- **Aggressive trim** — pipeline's default threshold is too loose, cut 15-20% extra per edge
- **Sharpen after downscale** — `UnsharpMask(radius=1, percent=40, threshold=2)` recovers LANCZOS blur
- **Binary alpha threshold** for crisp edges: `alpha > threshold → 255, else → 0`
- **Motion-aware frame selection** beats even subsampling — high-motion gets more frames, stills get fewer
- **Global bounding box** across all animations ensures consistent character size in spritesheets
- **One video → one animation** is the sweet spot; splitting videos into sub-animations adds complexity
- **Consistent canvas** (128x256) across all characters — height differences via character size, not canvas
- **Bottom-align** all frames on canvas — feet anchored for ground-based characters
- **nobg frames are the refinement source** — segmented frames can lose quality from extra processing

## Commit Convention
- Format: `[Phase X] TXXX: Brief description`
- Branch: `feat/TXXX-task-name`
