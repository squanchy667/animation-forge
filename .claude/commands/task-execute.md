# Task Execute

Execute a task from the Animation Forge task board autonomously.

## Input

Task ID: $ARGUMENTS (e.g., T001, T007, T014)

## Process

### 1. Load Task Spec
Read the task specification from `../animation-forge-docs/tasks/`:
- Phase 1: `tasks/phase-1/T001-*.md` through `T003-*.md`
- Phase 2: `tasks/phase-2/T004-*.md` through `T006-*.md`
- Phase 3: `tasks/phase-3/T007-*.md` through `T009-*.md`
- Phase 4: `tasks/phase-4/T010-*.md` through `T012-*.md`
- Phase 5: `tasks/phase-5/T013-*.md` through `T015-*.md`

### 2. Check Dependencies
Read `../animation-forge-docs/TASK_BOARD.md` and verify all "Depends On" tasks are marked DONE. If any are not, report which dependencies are missing and stop.

### 3. Understand Context
- Read the task spec fully (objective, subtasks, acceptance criteria)
- Read existing code files that will be modified or extended
- Read related modules to understand established patterns
- Check `../animation-forge-docs/PLAN.md` for architectural context
- Reference the original plan: `/Users/ofek/Downloads/ANIMATION_FORGE_PLAN.md` for detailed implementation specs

### 4. Plan Implementation
Before writing any code:
- List all files to create/modify
- Identify the implementation sequence
- Note any decisions that need user input

### 5. Execute
Implement the task following Animation Forge conventions:
- Python 3.10+ with type hints (`list[str]`, `X | None`)
- `pathlib.Path` for all file paths
- `rich` for all terminal output (progress, tables, panels)
- Optional deps (`rembg`, `mediapipe`, `anthropic`) in try/except
- Never crash silently — catch and display with Rich
- Frame numbering: `frame_0001.png` (1-indexed, 4-digit)

### 6. Verify
- Check Python syntax: `python -c "import py_compile; py_compile.compile('{file}', doraise=True)"`
- Check imports resolve correctly
- Verify acceptance criteria from the task spec

### 7. Report
Output a summary:
- What was implemented
- Files created/modified
- Any decisions made
- Acceptance criteria status (checked/unchecked)
- Suggested next steps

## Important
- Always read the full task spec AND the original plan file before starting
- Follow the acceptance criteria exactly
- Don't modify files outside the task's scope
- Commit with format: `[Phase X] TXXX: Brief description`
- Branch: `feat/TXXX-task-name`
