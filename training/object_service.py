from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_MODEL_PATH = "models/object_fire400_drone2800_yolo26s_v1_best.pt"
DEFAULT_CONFIDENCE_THRESHOLD = 0.60
DEFAULT_IMAGE_SIZE = 640
MODULE_DIR = Path(__file__).resolve().parent


def _resolve_local_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path.resolve()
    return (MODULE_DIR / path).resolve()


@lru_cache(maxsize=2)
def get_detector(model_path: str = DEFAULT_MODEL_PATH):
    path = _resolve_local_path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"YOLO model not found: {path}")

    from ultralytics import YOLO

    return YOLO(str(path))


def detect_image(
    image_path: str,
    model_path: str = DEFAULT_MODEL_PATH,
    out_dir: str = "runs/inference/backend",
    conf: float = DEFAULT_CONFIDENCE_THRESHOLD,
    imgsz: int = DEFAULT_IMAGE_SIZE,
    device: str | int | None = None,
    save: bool = True,
) -> dict[str, Any]:
    image = Path(image_path)
    if not image.exists():
        raise FileNotFoundError(f"image not found: {image}")

    model = get_detector(model_path)
    out_path = Path(out_dir)
    if not out_path.is_absolute():
        out_path = (MODULE_DIR / out_path).resolve()
    project = out_path.parent if out_path.parent != Path("") else Path(".")
    name = out_path.name

    predict_kwargs: dict[str, Any] = {
        "source": str(image),
        "imgsz": imgsz,
        "conf": conf,
        "save": save,
        "project": str(project),
        "name": name,
        "exist_ok": True,
        "verbose": False,
    }
    if device is not None:
        predict_kwargs["device"] = device

    result = model.predict(**predict_kwargs)[0]
    detections = []
    for box in result.boxes:
        class_id = int(box.cls[0])
        detections.append(
            {
                "class_id": class_id,
                "label": model.names[class_id],
                "confidence": float(box.conf[0]),
                "bbox": [float(x) for x in box.xyxy[0].tolist()],
            }
        )

    result_image_path = str(Path(result.save_dir) / Path(result.path).name) if save else None
    return {
        "result_image_path": result_image_path,
        "detections": detections,
        "model": str(Path(model_path)),
        "conf": conf,
        "imgsz": imgsz,
    }
