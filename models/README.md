# Model Files

Large model weights are not committed to Git.

Recommended local layout:

```text
models/
  yolo_object_best.pt
  joint_noapi_yolo26s_best.pt
  insightface/
    buffalo_l/
```

## Environment Variables

```powershell
$env:MODEL_PATH="D:\path\to\models\yolo_object_best.pt"
$env:FACE_MODEL_PACK="buffalo_l"
```

## YOLO

The backend expects the YOLO adapter to expose:

```python
def detect_image(image_path: str) -> dict:
    return {
        "result_image_path": "static/results/example.jpg",
        "detections": [
            {
                "label": "person",
                "class_id": 0,
                "confidence": 0.92,
                "bbox": [120, 80, 260, 360]
            }
        ],
        "model": {
            "name": "YOLO26s",
            "weights": "models/yolo_object_best.pt"
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
        "user_id": 1,
        "name": "Alice",
        "score": 0.82,
        "threshold": 0.65,
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
