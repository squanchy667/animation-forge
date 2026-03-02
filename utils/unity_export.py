"""Unity export utilities.

Generates AnimatorController JSON scaffold and C# AnimatorParams helper.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


# Animation categories for state machine logic
_LOCOMOTION = {"idle", "walk", "run", "jump", "apex", "fall", "land"}
_COMBAT = {"attack_1", "attack_2", "attack_3", "dash", "block"}
_REACTION = {"hurt", "death"}

# All possible transitions — only created if both states exist
_TRANSITIONS = [
    {"from": "idle", "to": "walk", "condition": "Speed", "mode": "Greater", "threshold": 0.1},
    {"from": "walk", "to": "run", "condition": "Speed", "mode": "Greater", "threshold": 0.8},
    {"from": "walk", "to": "idle", "condition": "Speed", "mode": "Less", "threshold": 0.1},
    {"from": "run", "to": "walk", "condition": "Speed", "mode": "Less", "threshold": 0.8},
    {"from": "jump", "to": "apex", "condition": None, "has_exit_time": True, "exit_time": 0.8},
    {"from": "apex", "to": "fall", "condition": "IsGrounded", "mode": "Equals", "threshold": False},
    {"from": "fall", "to": "land", "condition": "IsGrounded", "mode": "Equals", "threshold": True},
    {"from": "land", "to": "idle", "condition": None, "has_exit_time": True, "exit_time": 1.0},
    {"from": "hurt", "to": "idle", "condition": None, "has_exit_time": True, "exit_time": 1.0},
    # Any-state transitions
    {"from": "Any", "to": "hurt", "condition": "HurtTrigger", "mode": "Trigger"},
    {"from": "Any", "to": "death", "condition": "DeathTrigger", "mode": "Trigger"},
    {"from": "Any", "to": "attack_1", "condition": "AttackTrigger", "mode": "Trigger"},
]

_PARAMETERS = [
    {"name": "Speed", "type": "Float", "default": 0.0},
    {"name": "IsGrounded", "type": "Bool", "default": True},
    {"name": "AttackTrigger", "type": "Trigger", "default": None},
    {"name": "HurtTrigger", "type": "Trigger", "default": None},
    {"name": "DeathTrigger", "type": "Trigger", "default": None},
]


def _to_pascal_case(name: str) -> str:
    """Convert snake_case or space-separated name to PascalCase."""
    return "".join(word.capitalize() for word in name.replace("_", " ").replace("-", " ").split())


def generate_animator_controller(
    character_name: str,
    animations: list[str],
    output_path: str,
) -> None:
    """Generate a Unity AnimatorController JSON scaffold.

    Only includes states and transitions for animations that actually exist.

    Args:
        character_name: Character name for naming.
        animations: List of animation IDs present (e.g. ["idle", "walk", "attack_1"]).
        output_path: Path for output JSON file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    anim_set = set(animations)

    # Build states for existing animations only
    states = []
    for anim_id in animations:
        state = {
            "name": anim_id,
            "motion": f"{character_name}_{anim_id}",
            "speed": 1.0,
        }
        if anim_id == "death":
            state["no_exit"] = True
        states.append(state)

    # Filter transitions — only include if both from/to states exist
    transitions = []
    for t in _TRANSITIONS:
        from_state = t["from"]
        to_state = t["to"]

        # "Any" state is always valid
        from_valid = from_state == "Any" or from_state in anim_set
        to_valid = to_state in anim_set

        if from_valid and to_valid:
            transition = {
                "from": from_state,
                "to": to_state,
            }
            if t.get("condition"):
                transition["condition"] = {
                    "parameter": t["condition"],
                    "mode": t["mode"],
                }
                if "threshold" in t and t["mode"] != "Trigger":
                    transition["condition"]["threshold"] = t["threshold"]
            if t.get("has_exit_time"):
                transition["has_exit_time"] = True
                transition["exit_time"] = t["exit_time"]
            transitions.append(transition)

    controller = {
        "character_name": character_name,
        "animator_controller": f"{character_name}_AnimatorController",
        "parameters": _PARAMETERS,
        "layers": [
            {
                "name": "Base Layer",
                "states": states,
                "transitions": transitions,
                "default_state": "idle" if "idle" in anim_set else animations[0] if animations else "idle",
            }
        ],
        "generated_by": "Animation Forge v0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(controller, f, indent=2, ensure_ascii=False)
        f.write("\n")


def generate_animator_params_cs(
    character_name: str,
    animations: list[str],
    output_path: str,
) -> None:
    """Generate a C# static class with const strings for Animator parameters.

    Args:
        character_name: Character name (converted to PascalCase for class).
        animations: List of animation IDs present.
        output_path: Path for output .cs file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    class_name = f"{_to_pascal_case(character_name)}AnimatorParams"

    lines = [
        "// Auto-generated by Animation Forge",
        f"// Character: {character_name}",
        "",
        "using UnityEngine;",
        "",
        f"public static class {class_name}",
        "{",
        "    // Parameters",
    ]

    for param in _PARAMETERS:
        const_name = param["name"].upper()
        lines.append(f'    public const string {const_name} = "{param["name"]}";')

    lines.append("")
    lines.append("    // State Names")

    for anim_id in animations:
        const_name = f"STATE_{anim_id.upper()}"
        lines.append(f'    public const string {const_name} = "{anim_id}";')

    lines.append("}")
    lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
