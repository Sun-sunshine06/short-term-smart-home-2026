from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_MODEL_PATH = "models/yolo_object_best.pt"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_path(path: str | None) -> Path:
    if not path:
        path = DEFAULT_MODEL_PATH
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return _project_root() / candidate


def _relative_for_response(path: Path) -> str:
    try:
        return path.relative_to(_project_root()).as_posix()
    except ValueError:
        return str(path)


@lru_cache(maxsize=1)
def _load_yolo_model():
    model_path = _resolve_path(os.environ.get("MODEL_PATH"))
    if not model_path.exists():
        return None, model_path, "mock"

    try:
        from ultralytics import YOLO
    except Exception:
        return None, model_path, "missing-ultralytics"

    try:
        return YOLO(str(model_path)), model_path, "loaded"
    except Exception:
        return None, model_path, "load-failed"


def _mock_detection(image_path: str) -> dict[str, Any]:
    model_path = _resolve_path(os.environ.get("MODEL_PATH"))
    return {
        "result_image_path": image_path,
        "detections": [
            {
                "label": "person",
                "class_id": 0,
                "confidence": 0.88,
                "bbox": [120, 80, 260, 360],
            }
        ],
        "model": {
            "name": "YOLO26s-mock",
            "weights": _relative_for_response(model_path),
            "mode": "mock",
        },
    }


def detect_image(image_path: str) -> dict[str, Any]:
    """Detect objects from an image path.

    The function intentionally falls back to mock output when model weights or
    ultralytics are unavailable, so backend/frontend integration can continue
    before the visual team delivers final assets.
    """

    if not image_path:
        raise ValueError("image_path is required")

    model, model_path, status = _load_yolo_model()
    if model is None:
        result = _mock_detection(image_path)
        result["model"]["status"] = status
        return result

    results = model(image_path)
    first = results[0]
    detections: list[dict[str, Any]] = []
    names = getattr(first, "names", {}) or {}

    for box in getattr(first, "boxes", []) or []:
        class_id = int(box.cls[0].item())
        confidence = float(box.conf[0].item())
        bbox = [float(value) for value in box.xyxy[0].tolist()]
        detections.append(
            {
                "label": names.get(class_id, str(class_id)),
                "class_id": class_id,
                "confidence": confidence,
                "bbox": bbox,
            }
        )

    result_image_path = image_path
    if os.environ.get("YOLO_SAVE_RESULTS", "0") == "1":
        result_dir = _project_root() / "backend" / "static" / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        try:
            first.save(filename=str(result_dir / Path(image_path).name))
            result_image_path = _relative_for_response(result_dir / Path(image_path).name)
        except Exception:
            result_image_path = image_path

    return {
        "result_image_path": result_image_path,
        "detections": detections,
        "model": {
            "name": "YOLO26s",
            "weights": _relative_for_response(model_path),
            "status": status,
        },
    }
