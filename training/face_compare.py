import argparse
import json
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from insightface.app import FaceAnalysis


DEFAULT_MODEL_PACK = "buffalo_l"
DEFAULT_COSINE_SIMILARITY_THRESHOLD = 0.40
DEFAULT_COSINE_DISTANCE_THRESHOLD = 1.0 - DEFAULT_COSINE_SIMILARITY_THRESHOLD
DEFAULT_MODEL_ROOT = Path(__file__).resolve().parents[1] / "local" / "models" / "insightface"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare faces with InsightFace buffalo_l embeddings.")
    parser.add_argument("--image-a", help="First image path.")
    parser.add_argument("--image-b", help="Second image path.")
    parser.add_argument("--gallery", help="Directory of reference images. Subdirectories are treated as identities.")
    parser.add_argument("--probe", help="Probe image for gallery search.")
    parser.add_argument("--model-pack", default=DEFAULT_MODEL_PACK, help="InsightFace model pack.")
    parser.add_argument("--det-size", type=int, default=640, help="InsightFace detector input size.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_COSINE_SIMILARITY_THRESHOLD)
    parser.add_argument("--out", default="runs/face_compare", help="Output directory.")
    parser.add_argument("--self-test", action="store_true", help="Run a smoke test on prepared face sample images.")
    return parser.parse_args()


def load_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"failed to read image: {path}")
    return image


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


def save_crop(image: np.ndarray, box: list[float], path: Path) -> None:
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    height, width = image.shape[:2]
    x1 = max(0, min(width, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height, y1))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(path.suffix or ".jpg", image[y1:y2, x1:x2])
    if ok:
        encoded.tofile(str(path))


class InsightFaceRecognizer:
    def __init__(self, model_pack: str, det_size: int) -> None:
        self.model_pack = model_pack
        model_root = os.environ.get("INSIGHTFACE_HOME", str(DEFAULT_MODEL_ROOT))
        self.app = FaceAnalysis(name=model_pack, root=model_root, providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=-1, det_size=(det_size, det_size))

    def get_largest_face(self, image_path: Path) -> dict[str, Any]:
        return self.face_from_image(load_image(image_path), str(image_path))

    def face_from_image(self, image: np.ndarray, source: str) -> dict[str, Any]:
        faces = self.app.get(image)
        if not faces:
            # Tight portraits can fill the detector's field of view. Add context
            # for one retry, then map its geometry back to the original image.
            height, width = image.shape[:2]
            top, left = height // 2, width // 2
            padded = cv2.copyMakeBorder(image, top, top, left, left, cv2.BORDER_CONSTANT, value=(127, 127, 127))
            faces = self.app.get(padded)
            for detected in faces:
                detected.bbox -= np.array([left, top, left, top], dtype=np.float32)
                detected.kps -= np.array([left, top], dtype=np.float32)
        if not faces:
            raise ValueError(f"no face detected: {source}")
        face = max(faces, key=lambda item: float((item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1])))
        embedding = np.asarray(face.normed_embedding, dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm == 0:
            raise ValueError(f"zero face embedding: {source}")
        embedding = embedding / norm
        return {
            "image": image,
            "embedding": embedding,
            "box": [float(v) for v in face.bbox.tolist()],
            "kps": [[float(x), float(y)] for x, y in face.kps.tolist()],
            "det_score": float(face.det_score),
        }


def face_meta(face: dict[str, Any]) -> dict[str, Any]:
    return {
        "box": face["box"],
        "landmarks_5": face["kps"],
        "det_score": face["det_score"],
        "aligned_by": "insightface",
    }


def compare_two_images(
    recognizer: InsightFaceRecognizer,
    image_a: Path,
    image_b: Path,
    threshold: float,
    out_dir: Path,
) -> dict[str, Any]:
    face_a = recognizer.get_largest_face(image_a)
    face_b = recognizer.get_largest_face(image_b)
    score = cosine(face_a["embedding"], face_b["embedding"])
    save_crop(face_a["image"], face_a["box"], out_dir / "image_a_face.jpg")
    save_crop(face_b["image"], face_b["box"], out_dir / "image_b_face.jpg")
    return {
        "mode": "pair",
        "engine": "insightface",
        "model_pack": recognizer.model_pack,
        "metric": "cosine_similarity",
        "image_a": str(image_a),
        "image_b": str(image_b),
        "score": score,
        "cosine_distance": 1.0 - score,
        "threshold_similarity": threshold,
        "threshold_distance_equivalent": 1.0 - threshold,
        "same_person": score >= threshold,
        "image_a_face": face_meta(face_a),
        "image_b_face": face_meta(face_b),
    }


def iter_gallery_images(gallery: Path) -> list[tuple[str, Path]]:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    items: list[tuple[str, Path]] = []
    for path in sorted(gallery.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in image_exts:
            continue
        identity = path.parent.name if path.parent != gallery else path.stem
        items.append((identity, path))
    return items


def search_gallery(
    recognizer: InsightFaceRecognizer,
    gallery: Path,
    probe: Path,
    threshold: float,
    out_dir: Path,
) -> dict[str, Any]:
    probe_face = recognizer.get_largest_face(probe)
    save_crop(probe_face["image"], probe_face["box"], out_dir / "probe_face.jpg")

    matches = []
    skipped = []
    for identity, path in iter_gallery_images(gallery):
        try:
            ref_face = recognizer.get_largest_face(path)
        except ValueError as exc:
            skipped.append({"identity": identity, "image": str(path), "reason": str(exc)})
            continue
        score = cosine(probe_face["embedding"], ref_face["embedding"])
        matches.append(
            {
                "identity": identity,
                "image": str(path),
                "score": score,
                "cosine_distance": 1.0 - score,
                "face": face_meta(ref_face),
            }
        )
    matches.sort(key=lambda item: item["score"], reverse=True)
    best = matches[0] if matches else None
    return {
        "mode": "gallery",
        "engine": "insightface",
        "model_pack": recognizer.model_pack,
        "metric": "cosine_similarity",
        "probe": str(probe),
        "gallery": str(gallery),
        "threshold_similarity": threshold,
        "threshold_distance_equivalent": 1.0 - threshold,
        "best": best,
        "accepted": bool(best and best["score"] >= threshold),
        "probe_face": face_meta(probe_face),
        "matches": matches[:20],
        "skipped": skipped,
    }


def pick_self_test_images() -> tuple[Path, Path]:
    root = Path("samples/face_compare")
    images = sorted(root.glob("*.jpg"))
    if len(images) < 2:
        raise FileNotFoundError("not enough prepared face sample images for --self-test")
    return images[0], images[1]


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    recognizer = InsightFaceRecognizer(args.model_pack, args.det_size)

    if args.self_test:
        image_a, image_b = pick_self_test_images()
        report = compare_two_images(recognizer, image_a, image_b, args.threshold, out_dir)
    elif args.gallery and args.probe:
        report = search_gallery(recognizer, Path(args.gallery), Path(args.probe), args.threshold, out_dir)
    elif args.image_a and args.image_b:
        report = compare_two_images(recognizer, Path(args.image_a), Path(args.image_b), args.threshold, out_dir)
    else:
        raise ValueError("use --self-test, or --image-a/--image-b, or --gallery/--probe")

    report_path = out_dir / "face_compare_result.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"wrote: {report_path}")


if __name__ == "__main__":
    main()
