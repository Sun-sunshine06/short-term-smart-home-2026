from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


DEFAULT_FACE_THRESHOLD = 0.40
DEFAULT_FACE_MIN_MARGIN = 0.05


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_image_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return _project_root() / candidate


def _threshold() -> float:
    try:
        return float(os.environ.get("FACE_SIMILARITY_THRESHOLD", DEFAULT_FACE_THRESHOLD))
    except ValueError:
        return DEFAULT_FACE_THRESHOLD


def _min_margin() -> float:
    try:
        return float(os.environ.get("FACE_MIN_MARGIN", DEFAULT_FACE_MIN_MARGIN))
    except ValueError:
        return DEFAULT_FACE_MIN_MARGIN


def _try_training_face_service(image_path: str, threshold: float, min_margin: float) -> dict[str, Any] | None:
    training_dir = _project_root() / "training"
    if str(training_dir) not in sys.path:
        sys.path.insert(0, str(training_dir))
    try:
        from face_service import verify_face as training_verify_face
    except Exception:
        return None

    gallery_dir = os.environ.get("FACE_GALLERY_DIR", str(_project_root() / "training" / "face_gallery"))
    model_pack = os.environ.get("FACE_MODEL_PACK", "buffalo_l")
    try:
        det_size = int(os.environ.get("FACE_DET_SIZE", "640"))
    except ValueError:
        det_size = 640

    try:
        return training_verify_face(
            image_path=image_path,
            gallery_dir=gallery_dir,
            threshold=threshold,
            min_margin=min_margin,
            model_pack=model_pack,
            det_size=det_size,
        )
    except ValueError as exc:
        return {
            "matched": False,
            "user_id": None,
            "name": None,
            "score": None,
            "threshold": threshold,
            "min_margin": min_margin,
            "score_margin": None,
            "bbox": None,
            "landmarks_5": None,
            "det_score": None,
            "engine": "insightface",
            "model_pack": model_pack,
            "metric": "cosine_similarity",
            "best_match": None,
            "second_best_identity_match": None,
            "top_matches": [],
            "skipped": [{"image": image_path, "reason": str(exc)}],
            "mode": "no-face",
        }
    except Exception:
        return None


def verify_face(image_path: str) -> dict[str, Any]:
    """Verify a face image using the planned InsightFace contract.

    This placeholder returns deterministic mock output until the InsightFace
    registration database and buffalo_l model package are wired in.
    """

    if not image_path:
        raise ValueError("image_path is required")

    threshold = _threshold()
    min_margin = _min_margin()
    resolved_image_path = str(_resolve_image_path(image_path))
    training_result = _try_training_face_service(resolved_image_path, threshold, min_margin)
    if training_result is not None:
        return training_result

    score = float(os.environ.get("FACE_MOCK_SCORE", "0.0"))
    matched = score >= threshold

    return {
        "matched": matched,
        "user_id": "mock_user_001" if matched else None,
        "name": "authorized_user_a" if matched else None,
        "score": score,
        "threshold": threshold,
        "min_margin": min_margin,
        "score_margin": None,
        "bbox": [100, 60, 180, 160],
        "landmarks_5": [
            [120, 95],
            [155, 95],
            [138, 115],
            [124, 140],
            [152, 140],
        ],
        "det_score": 0.99,
        "engine": "insightface",
        "model_pack": os.environ.get("FACE_MODEL_PACK", "buffalo_l"),
        "metric": "cosine_similarity",
        "best_match": None,
        "top_matches": [],
        "skipped": [],
        "mode": "mock",
    }
