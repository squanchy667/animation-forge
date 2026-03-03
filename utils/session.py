"""Session state manager for Animation Forge pipeline.

Persists pipeline state as session_config.json, enabling resume from any phase.
"""

import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def new_session(output_dir: str, character_name: str) -> dict[str, Any]:
    """Create a new session dict with UUID and timestamp."""
    return {
        "schema_version": 2,
        "session_id": str(uuid.uuid4()),
        "character_name": character_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phases_completed": [],
        "videos": {},
        "animation_map": {},
        "output_dir": str(Path(output_dir).resolve()),
        "bg_removal_method": None,
        "game_profile": {},
        "analysis_results": {},
    }


def save_session(data: dict[str, Any], path: Path) -> None:
    """Atomic JSON write — write to temp file, then rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory, then atomic rename
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, suffix=".tmp", prefix=".session_"
    )
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        Path(tmp_path).replace(path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def load_session(path: Path) -> dict[str, Any]:
    """Read and return a session dict from JSON file."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def mark_phase_complete(session: dict[str, Any], phase: str) -> dict[str, Any]:
    """Append phase ID to phases_completed without duplicates."""
    if phase not in session["phases_completed"]:
        session["phases_completed"].append(phase)
    return session
