"""Motion analysis utilities shared between segmentation and frame analysis.

Extracts pose signatures from RGBA frames using alpha channel center-of-mass
and bounding box metrics. Used for auto-trim and motion consistency validation.
"""

from pathlib import Path

import numpy as np
from PIL import Image


def frame_pose_signature(frame_path: Path) -> tuple[float, float, float]:
    """Extract pose signature from an RGBA frame: center-of-mass X/Y and bbox height.

    AI-generated video has high per-pixel variation even in standing frames,
    so raw pixel diffs don't work. Instead we track the character's overall
    position and shape via the alpha channel.

    Args:
        frame_path: Path to RGBA PNG frame.

    Returns:
        (center_x, center_y, bbox_height) normalized to 0.0-1.0 range.
    """
    img = np.array(Image.open(frame_path).convert("RGBA"), dtype=np.float32)
    alpha = img[:, :, 3] / 255.0
    h, w = alpha.shape
    total = alpha.sum()

    if total < 1:
        return 0.5, 0.5, 0.0

    ys = np.arange(h, dtype=np.float32).reshape(-1, 1)
    xs = np.arange(w, dtype=np.float32).reshape(1, -1)
    cy = float((alpha * ys).sum() / total) / h
    cx = float((alpha * xs).sum() / total) / w

    # Bounding box height
    rows = alpha.max(axis=1)
    visible_rows = np.where(rows > 0.1)[0]
    if len(visible_rows) == 0:
        return cx, cy, 0.0
    bbox_h = float(visible_rows[-1] - visible_rows[0]) / h

    return cx, cy, bbox_h


def compute_motion_consistency(frame_paths: list[str | Path]) -> dict:
    """Analyze motion consistency across a sequence of frames.

    Computes pose signatures for all frames and returns statistics about
    the motion: mean/std of pose changes, flagging frames with anomalous jumps.

    Args:
        frame_paths: Sorted list of frame paths.

    Returns:
        Dict with motion_score (0-1), mean_diff, std_diff, anomaly_count.
    """
    if len(frame_paths) < 3:
        return {
            "motion_score": 1.0,
            "mean_diff": 0.0,
            "std_diff": 0.0,
            "anomaly_count": 0,
            "frame_count": len(frame_paths),
        }

    signatures = [frame_pose_signature(Path(p)) for p in frame_paths]

    diffs = []
    for i in range(len(signatures) - 1):
        cx1, cy1, bh1 = signatures[i]
        cx2, cy2, bh2 = signatures[i + 1]
        diff = abs(cx2 - cx1) * 2.0 + abs(cy2 - cy1) * 1.5 + abs(bh2 - bh1) * 1.0
        diffs.append(diff)

    mean_diff = float(np.mean(diffs))
    std_diff = float(np.std(diffs))

    # Count anomalous frames: > 3 std deviations from mean
    threshold = mean_diff + 3.0 * std_diff if std_diff > 0 else mean_diff * 3.0
    anomaly_count = sum(1 for d in diffs if d > threshold)

    # Motion score: 1.0 = perfectly smooth, lower = more anomalies
    if len(diffs) > 0:
        motion_score = max(0.0, 1.0 - (anomaly_count / len(diffs)))
    else:
        motion_score = 1.0

    return {
        "motion_score": round(motion_score, 3),
        "mean_diff": round(mean_diff, 5),
        "std_diff": round(std_diff, 5),
        "anomaly_count": anomaly_count,
        "frame_count": len(frame_paths),
    }


def compute_transparency_quality(frame_paths: list[str | Path]) -> dict:
    """Check alpha channel quality across frames.

    Analyzes the transparency of frames to detect issues like:
    - Background not fully removed (too much opaque area)
    - Character over-removed (too little opaque area)
    - Inconsistent alpha between frames

    Args:
        frame_paths: List of RGBA frame paths.

    Returns:
        Dict with mean_opaque_ratio, std_opaque_ratio, quality_rating.
    """
    if not frame_paths:
        return {"mean_opaque_ratio": 0.0, "std_opaque_ratio": 0.0, "quality_rating": "unknown"}

    # Sample up to 5 evenly spaced frames
    n = len(frame_paths)
    indices = [int(i * (n - 1) / min(4, n - 1)) for i in range(min(5, n))]
    indices = sorted(set(indices))

    opaque_ratios = []
    for idx in indices:
        path = Path(frame_paths[idx])
        if not path.exists():
            continue
        img = np.array(Image.open(path).convert("RGBA"))
        alpha = img[:, :, 3]
        opaque_ratio = float(np.count_nonzero(alpha > 128) / alpha.size)
        opaque_ratios.append(opaque_ratio)

    if not opaque_ratios:
        return {"mean_opaque_ratio": 0.0, "std_opaque_ratio": 0.0, "quality_rating": "unknown"}

    mean_opaque = float(np.mean(opaque_ratios))
    std_opaque = float(np.std(opaque_ratios))

    # Rating based on expected character-to-canvas ratio
    if mean_opaque < 0.05:
        quality_rating = "poor_too_transparent"
    elif mean_opaque > 0.85:
        quality_rating = "poor_too_opaque"
    elif std_opaque > 0.15:
        quality_rating = "inconsistent"
    elif 0.10 <= mean_opaque <= 0.70:
        quality_rating = "good"
    else:
        quality_rating = "acceptable"

    return {
        "mean_opaque_ratio": round(mean_opaque, 3),
        "std_opaque_ratio": round(std_opaque, 3),
        "quality_rating": quality_rating,
    }
