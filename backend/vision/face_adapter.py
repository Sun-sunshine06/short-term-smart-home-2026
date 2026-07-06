from __future__ import annotations

import os
from typing import Any


DEFAULT_FACE_THRESHOLD = 0.65


def _threshold() -> float:
    try:
        return float(os.environ.get("FACE_SIMILARITY_THRESHOLD", DEFAULT_FACE_THRESHOLD))
    except ValueError:
        return DEFAULT_FACE_THRESHOLD


def verify_face(image_path: str) -> dict[str, Any]:
    """Verify a face image using the planned InsightFace contract.

    This placeholder returns deterministic mock output until the InsightFace
    registration database and buffalo_l model package are wired in.
    """

    if not image_path:
        raise ValueError("image_path is required")

    threshold = _threshold()
    score = float(os.environ.get("FACE_MOCK_SCORE", "0.82"))
    matched = score >= threshold

    return {
        "matched": matched,
        "user_id": 1 if matched else None,
        "name": "authorized_user_a" if matched else None,
        "score": score,
        "threshold": threshold,
        "bbox": [100, 60, 180, 160],
        "landmarks_5": [
            [120, 95],
            [155, 95],
            [138, 115],
            [124, 140],
            [152, 140],
        ],
        "model": {
            "name": "InsightFace buffalo_l",
            "mode": "mock",
        },
    }
