# /sync-docs

Synchronize documentation with actual project state after tasks have been completed. This is a "finishing move" — run it after one or more `/execute-phase` or `/task-execute` runs to bring all docs up to date.

## Usage

```
/sync-docs full
/sync-docs status
/sync-docs changelog
/sync-docs tasks
```

## Input

Mode: $ARGUMENTS (default: `full`)

| Mode | What It Syncs |
|------|--------------|
| `full` | All of the below in sequence |
| `status` | TASK_BOARD.md statuses + roadmap phase progress |
| `changelog` | Append entries from recent commits to changelog.md |
| `tasks` | Update task spec files with completion notes |

## Process

### Step 1: Scan Current State
Gather ground truth from the code repo:

1. **Git log** — Read all commits since last sync (or all commits if first sync):
   ```bash
   git log --oneline --no-merges
   ```
   Parse commit messages for `[Phase X] TXXX:` patterns to identify completed tasks.

2. **File inventory** — Glob all source files to understand what exists:
   - `main.py`, `phases/*.py`, `utils/*.py`, `config/*`, `templates/*`

3. **Existing docs state** — Read current `TASK_BOARD.md` to know what's already marked DONE.

### Step 2: Sync Task Board (`status` mode)
File: `../animation-forge-docs/TASK_BOARD.md`

For each task identified as completed from git commits:
1. Update status from `PENDING` or `IN_PROGRESS` → `DONE`
2. If a task's code files exist but no commit matches, mark `IN_REVIEW`
3. Update the summary table at the bottom with current counts
4. Update the `Status: X/15 tasks DONE` line

Also update `../animation-forge-docs/product/roadmap.md`:
- For each phase, check if ALL tasks in that phase are DONE
- If yes: mark phase as `DONE`
- If some: mark phase as `IN_PROGRESS`
- If none: leave as `PENDING`

### Step 3: Sync Changelog (`changelog` mode)
File: `../animation-forge-docs/resources/changelog.md`

1. Read existing changelog to find the last recorded entry
2. Parse git log for commits not yet in changelog
3. Group commits by phase: `[Phase 1]`, `[Phase 2]`, etc.
4. For each phase group, generate a changelog section:
   ```markdown
   ## [Phase X] — {Phase Theme}

   ### Added
   - TXXX: Brief description (from commit message)
   - TXXX: Brief description

   ### Files Created
   - `phases/p2_extract.py` — Frame extraction module
   - `utils/session.py` — Session state manager
   ```
5. Prepend new entries above existing content (newest first)
6. Add date stamp: `_Synced: {YYYY-MM-DD}_`

### Step 4: Sync Task Specs (`tasks` mode)
Files: `../animation-forge-docs/tasks/phase-{N}/TXXX-*.md`

For each completed task:
1. Read the task spec file
2. Check acceptance criteria against actual implementation:
   - Read the files that were supposed to be created/modified
   - Mark checkboxes `[x]` for criteria that are verifiably met
   - Leave `[ ]` for criteria that can't be verified from code alone
3. Add a `## Completion Notes` section at the bottom:
   ```markdown
   ## Completion Notes
   - **Status:** DONE
   - **Completed:** {date from git commit}
   - **Branch:** `feat/TXXX-task-name` (or `main` if committed directly)
   - **Files Created:** list of actual files
   - **Deviations:** any differences from the original spec
   ```

### Step 5: Commit Docs
After all syncs complete:
1. Stage all changed docs files
2. Commit with message: `Sync docs: {mode} — {N} tasks updated, {date}`
3. Push to remote

### Step 6: Report
Print a Rich-formatted summary:

```
╔═══════════════════════════════════════════╗
║  DOCS SYNC COMPLETE                       ║
╠═══════════════════════════════════════════╣
║  Mode:      full                          ║
║  Tasks:     6/15 DONE (was 3/15)          ║
║  Changelog: 6 new entries added           ║
║  Specs:     3 task specs updated          ║
║  Roadmap:   Phase 1 DONE, Phase 2 DONE   ║
║                                           ║
║  Docs repo: animation-forge-docs          ║
║  Commit:    abc1234                        ║
╚═══════════════════════════════════════════╝
```

## Important

- This command ONLY modifies docs repo files — never touches code repo
- It reads git history from the CODE repo but writes to the DOCS repo
- Run from the code repo directory: `animation-forge/`
- Safe to run multiple times — idempotent (won't duplicate entries)
- Always commits and pushes docs changes at the end

## Paths

| Repo | Path |
|------|------|
| Code (read) | `/Users/ofek/Projects/Claude/AnimationForge/animation-forge/` |
| Docs (write) | `/Users/ofek/Projects/Claude/AnimationForge/animation-forge-docs/` |
