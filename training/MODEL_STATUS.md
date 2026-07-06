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
