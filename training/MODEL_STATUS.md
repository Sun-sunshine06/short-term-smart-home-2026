# Model status

## Current decision

- YOLO is used for object detection only.
- InsightFace is used for face recognition/access control.
- YOLO does not include a `face` class.

## Current YOLO dataset

```text
data/object_fire400_drone2800
```

Classes:

```yaml
0: fire_extinguisher
1: drone
```

## Current YOLO model

Use this model for backend/demo object detection:

```text
models/object_fire400_drone2800_yolo26s_v1_best.pt
```

The model names have been checked and match the dataset:

```python
{0: "fire_extinguisher", 1: "drone"}
```

Backend object detection adapter:

```text
object_service.py
```

Default object detection confidence:

```text
conf = 0.60
```

## YOLO weight update: v2 face-cleaned retraining

- Added weight: `models/object_fire400_drone2630_yolo26s_v2_face_removed_pretrained_best.pt`.
- SHA-256: `1E1F4F45A5D2C63DEA4E201B05CDEF577BFE14CD6709EAE84A4D40A6CFC3BB1F`.
- Training: official `yolo26s.pt` pretrained initialization, 30 epochs, 640 image size, batch 16, seed 42, CUDA device 0.
- Training data: 3,030 images: 400 `fire_extinguisher` and 2,630 `drone`. Face-containing drone images were removed before this retraining run.
- Validation: precision 0.9062, recall 0.8722, mAP50 0.9300, mAP50-95 0.6352 on 606 validation images.
- This branch adds the weight file only. Existing code defaults remain unchanged; callers that want v2 must pass this path as `model_path`.

## Face access

Face recognition/access control is handled by InsightFace `buffalo_l` through:

```text
face_service.py
face_compare.py
face_access_demo.py
```

Default access threshold:

```text
threshold = 0.40
min_margin = 0.05
```
