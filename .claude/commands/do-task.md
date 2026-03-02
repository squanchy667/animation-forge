# /do-task

Execute a single task through the Animation Forge pipeline.

## Usage

```
/do-task "Implement the spritesheet packing utility"
/do-task T007
```

## Input

Task description or Task ID: $ARGUMENTS

## Process

If input is a task ID (TXXX format):
1. Redirect to `/task-execute TXXX`

If input is a free-form task:
1. **Analyze** — Determine which module/phase the task affects
2. **Context** — Read relevant existing code and the original plan
3. **Implement** — Write code following project conventions
4. **Verify** — Syntax check, import check
5. **Report** — Summary of what was done

## Conventions
- Python 3.10+, pathlib, rich, type hints
- Refer to `/Users/ofek/Downloads/ANIMATION_FORGE_PLAN.md` for detailed implementation specs
- Refer to `../animation-forge-docs/` for task specs and architecture
