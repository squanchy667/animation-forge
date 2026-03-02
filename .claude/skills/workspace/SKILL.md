# Animation Forge Workspace Skill

This skill provides context about Animation Forge's project structure and navigation.

## Project Layout
```
/Users/ofek/Projects/Claude/AnimationForge/
├── animation-forge/                 # Code repository
│   ├── main.py                      # CLI entry point (Click)
│   ├── requirements.txt             # Python dependencies
│   ├── config/
│   │   └── animation_types.json     # 14 animation type definitions
│   ├── phases/
│   │   ├── p0_bootstrap.py          # Video analysis + env check
│   │   ├── p1_questionnaire.py      # Interactive video→animation mapping
│   │   ├── p2_extract.py            # ffmpeg frame extraction
│   │   ├── p3_bg_removal.py         # rembg + numpy bg removal
│   │   ├── p4_segmentation.py       # Frame range slicing
│   │   └── p5_export.py             # Spritesheet + Unity package
│   ├── utils/
│   │   ├── session.py               # Session state persistence
│   │   ├── vision.py                # Claude Vision API helpers
│   │   ├── spritesheet.py           # PIL grid packing
│   │   └── unity_export.py          # AnimatorController + C# params
│   └── templates/
│       ├── animator_controller.json.tmpl
│       └── import_guide.md.tmpl
├── animation-forge-docs/            # Documentation repository
│   ├── PLAN.md                      # Architecture + phase overview
│   ├── TASK_BOARD.md                # 15 tasks, 5 phases
│   ├── development-agents.md        # 6 agent types + batch plan
│   ├── tasks/phase-{1..5}/          # Individual task specs
│   ├── architecture/                # System overview + data flow
│   └── ...                          # Developer, product, resources, testing
```

## Key Commands
```bash
cd /Users/ofek/Projects/Claude/AnimationForge/animation-forge
pip install -r requirements.txt       # Install dependencies
python main.py run --video X --character Y  # Full pipeline
python main.py resume --session path  # Resume interrupted session
python main.py preview --video X      # Preview only (bootstrap)
```

## Pipeline Flow
```
P0 Bootstrap → P1 Questionnaire → P2 Extract → P3 BG Removal → P4 Segmentation → P5 Export
```

## Adding New Code
- **New phase**: Create `phases/p{N}_{name}.py`, add to pipeline in `main.py`
- **New utility**: Create in `utils/`, import where needed
- **New animation type**: Add to `config/animation_types.json`
- **New export format**: Extend `phases/p5_export.py` and `utils/unity_export.py`

## Original Plan
The detailed implementation spec is at: `/Users/ofek/Downloads/ANIMATION_FORGE_PLAN.md`
