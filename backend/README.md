# Backend Prototype

Flask + SQLite backend for the first smart-home integration test branch.

This version does not require real hardware. It seeds a generic Ascend-based Orange Pi AIpro hardware profile and provides mock-friendly APIs for frontend, hardware, YOLO, and face-recognition integration.

## Run

```powershell
cd <PROJECT_ROOT>\backend
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
cd <PROJECT_ROOT>\backend
python scripts\simulate_orange_pi.py
```

## Vision Models

YOLO inference weights are committed under `../training/models/`. InsightFace `buffalo_l` weights are distributed as a GitHub Release asset because several ONNX files are larger than GitHub's normal Git file limit.

Release asset:

```text
https://github.com/Sun-sunshine06/short-term-smart-home-2026/releases/download/vision-models-v1/buffalo_l.zip
```

For offline InsightFace runs, unzip `buffalo_l.zip` to:

```text
<USER_HOME>/.insightface/models/buffalo_l/
```

Then set explicit environment variables if needed:

```powershell
$env:MODEL_PATH="<PROJECT_ROOT>\training\models\object_fire400_drone2800_yolo26s_v1_best.pt"
$env:FACE_MODEL_PACK="buffalo_l"
$env:FACE_GALLERY_DIR="<PROJECT_ROOT>\training\face_gallery"
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
POST /api/camera/upload
POST /api/yolo/detect
GET  /api/yolo/latest
GET  /api/yolo/history
POST /api/face/access
POST /api/face/verify
GET  /api/face/history
GET  /api/face/users
POST /api/face/users
GET  /api/face/users/<id>
POST /api/face/users/<id>/images
GET  /api/face/gallery
```

## Example Face User Registration

The first version registers existing image paths instead of handling browser file uploads. If the source file exists, it is copied to `FACE_GALLERY_DIR/<identity>/` so `training/face_service.py` can read the standard InsightFace gallery layout.

```json
{
  "name": "Alice",
  "identity": "user_001",
  "image_path": "uploads/alice_001.jpg",
  "copy_to_gallery": true
}
```

Add another enrollment image:

```json
{
  "image_path": "uploads/alice_002.jpg",
  "copy_to_gallery": true
}
```

Gallery status:

```text
GET /api/face/gallery
```

## Example YOLO Request

Orange Pi camera or snapshot uploads should use:

```text
POST /api/camera/upload
```

For acceptance, put the test image on Orange Pi first and let `edge/orange_pi_client.py --upload-image <path>` call this endpoint. The curl command below is only the raw protocol equivalent.

Multipart example:

```bash
curl -X POST http://<BACKEND_IP>:5000/api/camera/upload \
  -F "image=@/tmp/smart_home_snapshot.jpg" \
  -F "source=orange_pi_camera" \
  -F "node_id=orange-pi-aipro-20t"
```

JSON/base64 example:

```json
{
  "filename": "smart_home_snapshot.jpg",
  "source": "orange_pi_camera",
  "node_id": "orange-pi-aipro-20t",
  "image_base64": "<base64 encoded image>"
}
```

The upload endpoint saves the image and immediately passes the saved `image_path` to the YOLO adapter. The response includes both `image_path` and `yolo_record`.

If the image already exists on the backend computer, call YOLO directly:

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
