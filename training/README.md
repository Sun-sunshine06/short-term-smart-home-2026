# 视觉模块说明：YOLO26 物体检测 + InsightFace 人脸门禁

本目录是当前视觉侧交付内容，包含两部分：

```text
物体检测：YOLO26s 物体检测模型
人脸门禁：InsightFace buffalo_l
```

当前状态：

- 已训练好的 YOLO 模型：`models/object_fire400_drone2800_yolo26s_v1_best.pt`
- YOLO 只负责物体检测，不做人脸检测或人脸识别。
- 人脸识别和门禁判断使用 InsightFace。
- 后端、数据库、硬件拍照和设备控制不在本目录实现范围内，本目录只提供视觉接口和测试样例。

当前 YOLO 模型不包含 `face` 类。当前类别只有：

```yaml
0: fire_extinguisher
1: drone
```

## 1. 文件说明

- `models/object_fire400_drone2800_yolo26s_v1_best.pt`：当前交付的 YOLO 权重。
- `data/object_fire400_drone2800/data.yaml`：当前物体检测数据集配置。
- `train_joint.py`：后续需要复训时使用的 YOLO 训练脚本。
- `val_joint.py`：验证当前或后续训练权重的脚本。
- `face_compare.py`：InsightFace 人脸比对基础逻辑。
- `face_service.py`：后端可直接调用的人脸门禁适配层。
- `object_service.py`：后端可直接调用的 YOLO 物体检测适配层。
- `face_access_demo.py`：“2 真 1 假”门禁演示脚本。
- `requirements.txt`：Python 依赖。
- `.gitignore`：忽略数据集、运行输出和模型权重，避免误提交大文件。

## 2. Git 提交说明

本目录上传到 GitHub 时只提交代码、说明文档和小样例图片。下面内容不会提交：

```text
data/
runs/
models/*.pt
models/*.onnx
```

原因：

- `data/` 是训练数据集，体积较大。
- `runs/` 是本地运行输出，可以重新生成。
- `.pt/.onnx` 模型权重体积较大，建议通过共享盘、Release 或 Git LFS 单独分发。

后端或演示运行前，需要把当前 YOLO 权重放回：

```text
training/models/object_fire400_drone2800_yolo26s_v1_best.pt
```

## 3. 环境安装

建议在虚拟环境中安装：

```powershell
cd C:\Users\23378\Downloads\code\小学期\training
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
```

## 4. 复训说明

当前已交付模型可以直接用于推理，不需要重新训练。若后续要重新训练，可以使用：

```powershell
python train_joint.py --data data\object_fire400_drone2800\data.yaml --model yolo26s.pt --epochs 30 --imgsz 640 --batch 16 --device 0 --project runs\object_yolo26 --name object_fire400_drone2800_yolo26s
```

说明：

- 复训时需要准备 `yolo26s.pt` 基模；当前清理后的目录不再保留基模副本。
- 当前数据集位于 `data/object_fire400_drone2800`。
- 当前类别固定为 `fire_extinguisher/drone`。
- 显存不够时减小 `--batch` 或 `--imgsz`。

验证当前模型：

```powershell
python val_joint.py --data data\object_fire400_drone2800\data.yaml --model models\object_fire400_drone2800_yolo26s_v1_best.pt --imgsz 640 --device 0
```

## 5. 后端接口说明

本目录只负责视觉侧能力。后端需要负责：

- 从硬件或上传接口获得图片。
- 保存图片并把图片路径传给视觉接口。
- 读取视觉接口返回结果。
- 根据结果写数据库、更新状态或下发开门命令。

### 5.1 物体检测接口

当前模型：

```text
models/object_fire400_drone2800_yolo26s_v1_best.pt
```

当前类别：

```yaml
0: fire_extinguisher
1: drone
```

输入：

```text
image_path: str
```

即后端或硬件侧保存下来的一张图片路径。

后端可直接调用：

```python
from object_service import detect_image

result = detect_image(
    image_path="uploads/camera_001.jpg",
    conf=0.60,
)
```

输出示例：

```json
{
  "result_image_path": "runs/inference/backend/result/image.jpg",
  "detections": [
    {
      "class_id": 0,
      "label": "fire_extinguisher",
      "confidence": 0.8852,
      "bbox": [464.65, 617.55, 499.15, 706.6]
    }
  ]
}
```

字段说明：

- `label`：物体名称，目前只会是 `fire_extinguisher` 或 `drone`。
- `confidence`：置信度。
- `bbox`：像素坐标 `[x1, y1, x2, y2]`。
- `result_image_path`：带检测框和类别标签的结果图路径。
- 当前建议物体检测推理阈值使用 `conf=0.60`，用于减少非目标图片误检。

### 5.2 人脸门禁接口

人脸门禁使用 InsightFace `buffalo_l`。处理流程：

```text
人脸检测 -> 5 点关键点 -> ArcFace 对齐 -> 提取 embedding -> cosine similarity 比对
```

当前不从数据库直接读取人脸数据。后端只需要把数据库中的授权人员注册照保存或缓存成下面的目录结构，然后传入 `gallery_dir`：

```text
face_gallery/
  user_001/
    001.jpg
    002.jpg
    003.jpg
  user_002/
    001.jpg
    002.jpg
    003.jpg
```

调用接口：

```python
from face_service import verify_face

result = verify_face(
    image_path="uploads/camera_001.jpg",
    gallery_dir="face_gallery",
    threshold=0.40,
    min_margin=0.05,
)
```

输入说明：

```text
image_path: str      # 当前摄像头或上传图片路径
gallery_dir: str     # 授权人员注册照目录
threshold: float     # 默认 0.40
min_margin: float    # 默认建议 0.05
```

判断逻辑：

```text
best_identity_score >= threshold
and best_identity_score - second_best_identity_score >= min_margin
```

授权通过时的输出示例：

```json
{
  "matched": true,
  "user_id": "user_001",
  "name": "user_001",
  "score": 0.7871,
  "threshold": 0.4,
  "min_margin": 0.05,
  "score_margin": 0.8241,
  "bbox": [100.0, 60.0, 180.0, 160.0],
  "landmarks_5": [[120.0, 95.0], [155.0, 95.0], [138.0, 115.0], [124.0, 140.0], [152.0, 140.0]],
  "det_score": 0.99,
  "engine": "insightface",
  "model_pack": "buffalo_l",
  "metric": "cosine_similarity",
  "best_match": {
    "user_id": "user_001",
    "name": "user_001",
    "reference_image": "face_gallery/user_001/003.jpg",
    "score": 0.7871,
    "cosine_distance": 0.2129
  },
  "second_best_identity_match": {
    "user_id": "user_002",
    "name": "user_002",
    "reference_image": "face_gallery/user_002/001.jpg",
    "score": -0.0371,
    "cosine_distance": 1.0371
  },
  "skipped": []
}
```

未授权时的输出示例：

```json
{
  "matched": false,
  "user_id": null,
  "name": null,
  "score": 0.0839,
  "threshold": 0.4,
  "min_margin": 0.05,
  "score_margin": 0.0596,
  "engine": "insightface",
  "model_pack": "buffalo_l",
  "metric": "cosine_similarity"
}
```

后端可以直接按下面逻辑开门或拒绝：

```python
action = "unlock" if result["matched"] else "deny"
```

注意：

- 当前人脸接口返回人脸框 `bbox` 和 5 点关键点 `landmarks_5`，但不默认保存带人脸框结果图。
- 如果输入图片没有检测到人脸，会抛出 `ValueError("no face detected: ...")`，后端应捕获后返回 `deny`。
- 每个授权人员建议录入 3-5 张清晰图片。
- 不建议把多人合照、严重模糊、强遮挡图片放入注册库。

## 6. 门禁演示：2 真 1 假

验收要求中的“2 真 1 假”可以用 `face_access_demo.py` 复现。脚本会从 LFW 数据集中自动选择有多张图片的人，构造两个授权人员和一个未授权人员。

测试人员：

```text
授权人员：
  George_W_Bush：录入 5 张
  Colin_Powell：录入 5 张

测试图片：
  true_George_W_Bush.jpg：期望开门
  true_Colin_Powell.jpg：期望开门
  fake_unknown_Tony_Blair.jpg：期望拒绝
```

运行：

```powershell
python face_access_demo.py --out runs\face_access_demo_threshold040 --gallery-count 5 --threshold 0.40 --min-margin 0.05
```

本机结果：

```text
true_George_W_Bush：score 0.7871 -> unlock -> passed
true_Colin_Powell：score 0.7604 -> unlock -> passed
fake_unknown_Tony_Blair：score 0.0839 -> deny -> passed
```

报告文件：

```text
runs/face_access_demo_threshold040/face_access_demo_result.json
```

## 7. 全流程验证记录

最后一次完整验证时间：2026-07-07。

### 7.1 脚本检查

已执行：

```powershell
python -m py_compile object_service.py face_compare.py face_service.py face_access_demo.py train_joint.py val_joint.py
```

结果：通过。

### 7.2 YOLO 模型类别检查

已执行：

```powershell
python -c "from ultralytics import YOLO; m=YOLO('models/object_fire400_drone2800_yolo26s_v1_best.pt'); print(m.names)"
```

结果：

```python
{0: 'fire_extinguisher', 1: 'drone'}
```

说明：当前 YOLO 模型不包含 `face` 类，只检测灭火器和无人机。

### 7.3 YOLO 推理检查

已使用当前模型分别测试一张灭火器图片和一张无人机图片。

结果：

```text
灭火器样例：检测到 4 个 fire_extinguisher，最高置信度 0.8852
无人机样例：检测到 1 个 drone，置信度 0.8840
```

带框结果图：

```text
runs/inference/object_fire400_drone2800_yolo26s_v1_smoke/image0.jpg
runs/inference/object_fire400_drone2800_yolo26s_v1_smoke/image1.jpg
```

### 7.4 人脸门禁检查

已执行：

```powershell
python face_access_demo.py --out runs\face_access_demo_threshold040 --gallery-count 5 --threshold 0.40 --min-margin 0.05
```

结果：

```text
true_George_W_Bush -> unlock -> passed，score 0.7871
true_Colin_Powell -> unlock -> passed，score 0.7604
fake_unknown_Tony_Blair -> deny -> passed，score 0.0839
```

报告文件：

```text
runs/face_access_demo_threshold040/face_access_demo_result.json
```

### 7.5 当前全流程结论

```text
物体检测：已跑通，可输出类别、置信度、bbox，并保存带框结果图。
人脸门禁：已跑通 2 真 1 假，可输出 matched/user_id/score，并据此 unlock 或 deny。
数据库/后端/硬件：不在本目录实现范围内，后端按本文档接口接入即可。
```
