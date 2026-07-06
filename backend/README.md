# Backend Prototype

Flask + SQLite backend for the first smart-home integration test branch.

This version does not require real hardware. It seeds an Orange Pi AIpro 20T hardware profile from official public specifications and provides mock-friendly APIs for frontend, hardware, YOLO, and face-recognition integration.

## Run

```powershell
cd D:\大二下\01_课程\short_term_program\backend
python -m pip install -r requirements.txt
python app.py
```

Optional vision dependencies:

```powershell
python -m pip install -r requirements-vision.txt
```

Default server:

```text
http://127.0.0.1:5000
```

Open the dashboard:

```text
http://127.0.0.1:5000/
```

## Simulate Orange Pi Uploads

Open another terminal:

```powershell
cd D:\大二下\01_课程\short_term_program\backend
python scripts\simulate_orange_pi.py
```

## Vision Models

Model weights are not committed to Git. Put local weights under `../training/models/` or set explicit environment variables:

```powershell
$env:MODEL_PATH="D:\path\to\training\models\object_fire400_drone2800_yolo26s_v1_best.pt"
$env:FACE_MODEL_PACK="buffalo_l"
$env:FACE_GALLERY_DIR="D:\path\to\training\face_gallery"
$env:FACE_SIMILARITY_THRESHOLD="0.40"
$env:FACE_MIN_MARGIN="0.05"
```

If the model files or optional vision dependencies are missing, the backend returns mock results so API/frontend integration can continue.

## Main APIs

```text
GET  /api/health
GET  /api/hardware/profile
GET  /api/status
POST /api/sensor/update
POST /api/device/control
GET  /api/device/commands
POST /api/device/commands/<id>/ack
GET  /api/history
POST /api/yolo/detect
GET  /api/yolo/latest
GET  /api/yolo/history
POST /api/face/access
POST /api/face/verify
GET  /api/face/history
```

## Example YOLO Request

```json
{
  "image_path": "uploads/example.jpg"
}
```

Expected adapter contract:

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

## Example Face Verification Request

```json
{
  "image_path": "uploads/face_a.jpg"
}
```

Expected InsightFace adapter contract:

```python
def verify_face(image_path: str) -> dict:
    return {
        "matched": True,
        "user_id": "user_001",
        "name": "user_001",
        "score": 0.82,
        "threshold": 0.40,
        "min_margin": 0.05,
        "score_margin": 0.12,
        "bbox": [100, 60, 180, 160],
        "landmarks_5": [
            [120, 95],
            [155, 95],
            [138, 115],
            [124, 140],
            [152, 140]
        ],
        "engine": "insightface",
        "model_pack": "buffalo_l"
    }
```

## Example Sensor Update

```json
{
  "temperature": 28.5,
  "door_open": false,
  "window_open": true,
  "light_level": 70,
  "fan_on": false,
  "lock_open": false
}
```
