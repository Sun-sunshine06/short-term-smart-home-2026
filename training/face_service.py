from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from face_compare import (
    DEFAULT_COSINE_SIMILARITY_THRESHOLD,
    DEFAULT_MODEL_PACK,
    InsightFaceRecognizer,
    cosine,
    face_meta,
    iter_gallery_images,
)


DEFAULT_GALLERY_DIR = "face_gallery"


@lru_cache(maxsize=4)
def get_recognizer(model_pack: str = DEFAULT_MODEL_PACK, det_size: int = 640) -> InsightFaceRecognizer:
    return InsightFaceRecognizer(model_pack=model_pack, det_size=det_size)


def verify_face(
    image_path: str,
    gallery_dir: str = DEFAULT_GALLERY_DIR,
    threshold: float = DEFAULT_COSINE_SIMILARITY_THRESHOLD,
    min_margin: float = 0.0,
    model_pack: str = DEFAULT_MODEL_PACK,
    det_size: int = 640,
) -> dict[str, Any]:
    recognizer = get_recognizer(model_pack, det_size)
    probe_path = Path(image_path)
    gallery_path = Path(gallery_dir)
    probe_face = recognizer.get_largest_face(probe_path)

    candidates: list[dict[str, Any]] = []
    skipped = []
    for identity, ref_path in iter_gallery_images(gallery_path):
        try:
            ref_face = recognizer.get_largest_face(ref_path)
        except ValueError as exc:
            skipped.append({"identity": identity, "image": str(ref_path), "reason": str(exc)})
            continue
        score = cosine(probe_face["embedding"], ref_face["embedding"])
        candidate = {
            "user_id": identity,
            "name": identity,
            "reference_image": str(ref_path),
            "score": score,
            "cosine_distance": 1.0 - score,
        }
        candidates.append(candidate)

    candidates.sort(key=lambda item: item["score"], reverse=True)
    best = candidates[0] if candidates else None
    identity_best: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        identity = candidate["user_id"]
        if identity not in identity_best or candidate["score"] > identity_best[identity]["score"]:
            identity_best[identity] = candidate
    identity_rank = sorted(identity_best.values(), key=lambda item: item["score"], reverse=True)
    second_best_identity = identity_rank[1] if len(identity_rank) > 1 else None
    score_margin = (best["score"] - second_best_identity["score"]) if best and second_best_identity else None
    margin_ok = True if score_margin is None else score_margin >= min_margin
    matched = bool(best and best["score"] >= threshold and margin_ok)
    return {
        "matched": matched,
        "user_id": best["user_id"] if matched and best else None,
        "name": best["name"] if matched and best else None,
        "score": best["score"] if best else None,
        "threshold": threshold,
        "min_margin": min_margin,
        "score_margin": score_margin,
        "threshold_distance_equivalent": 1.0 - threshold,
        "bbox": probe_face["box"],
        "landmarks_5": probe_face["kps"],
        "det_score": probe_face["det_score"],
        "engine": "insightface",
        "model_pack": model_pack,
        "metric": "cosine_similarity",
        "best_match": best,
        "second_best_identity_match": second_best_identity,
        "top_matches": candidates[:10],
        "skipped": skipped,
    }


def extract_face_embedding(
    image_path: str,
    model_pack: str = DEFAULT_MODEL_PACK,
    det_size: int = 640,
) -> dict[str, Any]:
    recognizer = get_recognizer(model_pack, det_size)
    face = recognizer.get_largest_face(Path(image_path))
    embedding = np.asarray(face["embedding"], dtype=np.float32)
    return {
        "embedding": embedding.tolist(),
        "embedding_dim": int(embedding.shape[0]),
        "face": face_meta(face),
        "engine": "insightface",
        "model_pack": model_pack,
    }
