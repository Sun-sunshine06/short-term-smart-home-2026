# Model Files

Large model weights are not committed to Git.

Recommended local layout:

```text
models/
  insightface/
    buffalo_l/
training/
  models/
    object_fire400_drone2800_yolo26s_v1_best.pt
```

## Environment Variables

```powershell
$env:MODEL_PATH="D:\path\to\training\models\object_fire400_drone2800_yolo26s_v1_best.pt"
$env:FACE_MODEL_PACK="buffalo_l"
$env:FACE_GALLERY_DIR="D:\path\to\training\face_gallery"
$env:FACE_SIMILARITY_THRESHOLD="0.40"
$env:FACE_MIN_MARGIN="0.05"
```

## YOLO

The backend expects the YOLO adapter to expose:

```python
def detect_image(image_path: str) -> dict:
    return {
        "result_image_path": "static/results/example.jpg",
        "detections": [
            {
                "label": "fire_extinguisher",
                "class_id": 0,
                "confidence": 0.92,
                "bbox": [120, 80, 260, 360]
            }
        ],
        "model": {
            "name": "YOLO26s",
            "weights": "training/models/object_fire400_drone2800_yolo26s_v1_best.pt"
        }
    }
```

## InsightFace

Face access control is expected to use InsightFace `buffalo_l`.

The backend expects the face adapter to expose:

```python
def verify_face(image_path: str) -> dict:
    return {
        "matched": True,
        "user_id": "user_001",
        "name": "user_001",
        "score": 0.82,
        "threshold": 0.40,
        "min_margin": 0.05,
        "bbox": [100, 60, 180, 160],
        "landmarks_5": [
            [120, 95],
            [155, 95],
            [138, 115],
            [124, 140],
            [152, 140]
        ]
    }
```
