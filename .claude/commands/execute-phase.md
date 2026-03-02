# /execute-phase

Run all tasks in a phase with batched execution and artifact handoff.

## Usage

```
/execute-phase 1
/execute-phase 2
```

## Input

Phase number: $ARGUMENTS (1–5)

## Process

### 1. Load Phase Tasks
Read `../animation-forge-docs/TASK_BOARD.md` and load all tasks for the specified phase.
For each task, read the full spec from `../animation-forge-docs/tasks/phase-{N}/TXXX-*.md`.

### 2. Check Dependencies
For each task in the phase, verify all "Depends On" tasks are marked DONE in TASK_BOARD.md.
If any dependencies are not satisfied, report which are missing and ask user how to proceed.

### 3. Plan Execution Batches
Group tasks into batches based on dependencies:
- Tasks with no unresolved dependencies within the phase go in the same batch
- Batches execute sequentially; tasks within a batch can run in parallel
- Refer to `../animation-forge-docs/development-agents.md` for the batch plan

### 4. Execute Each Task
For each task in batch order, run the `/task-execute` pipeline:
1. Read task spec fully (objective, subtasks, acceptance criteria)
2. Read existing code that will be modified/extended
3. Plan implementation (list files to create/modify)
4. Implement following Animation Forge conventions
5. Verify (Python syntax check, import validation)
6. Report results

### 5. Update Task Board
After each task completes:
- Update status in `../animation-forge-docs/TASK_BOARD.md` (PENDING → DONE)
- Commit code with format: `[Phase {N}] TXXX: Brief description`

### 6. Phase Report
After all tasks in the phase complete, output:
- Per-task results (what was created/modified)
- Files created in this phase
- Any issues or warnings
- What the next phase needs

## Phase Reference

| Phase | Tasks | Theme |
|-------|-------|-------|
| 1 | T001, T002, T003 | Foundation (scaffold, session, CLI skeleton) |
| 2 | T004, T005, T006 | Core Pipeline (extract, bg removal) |
| 3 | T007, T008, T009 | Export (spritesheet, Unity export, metadata) |
| 4 | T010, T011, T012 | Interactive (bootstrap, Vision, questionnaire) |
| 5 | T013, T014, T015 | Integration (segmentation, CLI wiring, E2E) |

## Important
- Always read task specs before implementing
- Follow acceptance criteria exactly
- Don't modify files outside task scope
- Commit after each task, not at the end of the phase
- If a task fails, continue with remaining tasks unless --stop-on-failure
