# Orange Pi Camera Demo Record - 2026-07-08

This note records the successful real-device integration run for the smart-home demo.

## Demo Topology

Final demo should use the backend computer as the control and inference host:

```text
Orange Pi AIpro + USB camera
-> HTTP camera frame upload / heartbeat / sensor status
-> backend computer Flask service
-> SQLite records + Web GUI
-> YOLO inference on backend computer
```

Backend computer:

- Backend URL on current network: `http://10.75.29.155:5000`
- Web GUI: `http://10.75.29.155:5000/`
- Control/download helper used during integration: `http://10.75.29.155:5055/client.py`
- Python environment: project venv at `D:\ashotterm\.venv`
- Runtime model/cache path: `D:\ashotterm\local\`

Orange Pi:

- Node id: `orange-pi-aipro-remote`
- Hostname: `orangepiaipro`
- Reachable IPv4 during test: `10.75.29.240`
- Other reported interface: `172.17.0.1`
- OS: Ubuntu 22.04.3 LTS
- Kernel: `5.10.0+`
- Architecture: `aarch64`
- Python: `3.9.2`
- Persistent client path: `/home/HwHiAiUser/smart_home_edge/orange_pi_client.py`
- Persistent client log: `/home/HwHiAiUser/smart_home_edge/orange_pi_client.log`

Camera:

- USB device: `Generic HD camera`
- Linux devices: `/dev/video0`, `/dev/video1`
- Active capture device: `/dev/video0`
- Capture/upload mode: one JPEG frame every 2 seconds

## Verified Result

The Orange Pi is confirmed to keep a persistent connection by polling and posting to the backend:

- `POST /api/edge/register`
- `POST /api/edge/heartbeat`
- `POST /api/sensor/update`
- `GET /api/device/commands`
- `POST /api/camera/upload`

Latest verified backend state during the test:

```json
{
  "camera_online": true,
  "hardware_online": true,
  "node_id": "orange-pi-aipro-remote",
  "hostname": "orangepiaipro"
}
```

Latest verified YOLO record:

```json
{
  "model_name": "YOLO26s",
  "model": {
    "status": "loaded",
    "weights": "training/models/object_fire400_drone2800_yolo26s_v1_best.pt",
    "conf": 0.6
  },
  "source": "orange_pi_camera",
  "upload_mode": "multipart"
}
```

This confirms that the flow is no longer using the YOLO mock adapter. Real YOLO inference is running on the backend computer through the project venv.

## Backend Environment

The backend dependencies were installed into the project-local venv:

```powershell
D:\ashotterm\.venv\Scripts\python.exe -m pip install -r D:\ashotterm\backend\requirements.txt -r D:\ashotterm\backend\requirements-vision.txt
```

Verified installed packages include:

```text
Flask 3.1.3
ultralytics 8.4.90
opencv-python 5.0.0.93
torch 2.12.1
torchvision 0.27.1
onnxruntime 1.27.0
insightface 1.0.1
numpy 2.5.1
```

Backend startup used for the successful YOLO camera demo:

```powershell
$env:INSIGHTFACE_HOME = "D:\ashotterm\local\models\insightface"
$env:PIP_CACHE_DIR = "D:\ashotterm\local\pip-cache"
$env:TMP = "D:\ashotterm\local\tmp"
$env:TEMP = "D:\ashotterm\local\tmp"
$env:CAMERA_UPLOAD_FACE_VERIFY = "0"
cd D:\ashotterm\backend
D:\ashotterm\.venv\Scripts\python.exe app.py
```

`CAMERA_UPLOAD_FACE_VERIFY=0` was used only to keep the camera + real YOLO path stable while the InsightFace model package is prepared.

## Code Fixes Included In This Branch

Two adapter fixes are included because real inference needs absolute image paths:

- `backend/vision/yolo_adapter.py`
  - Resolves uploaded relative image paths before passing them to `ultralytics`.
  - Keeps API responses in the existing relative path format.
- `backend/vision/face_adapter.py`
  - Resolves uploaded relative image paths before passing them into the training face service.

Without the YOLO path fix, uploaded camera frames saved as `backend/data/uploads/...` work in mock mode but fail in real `ultralytics` inference because the process working directory is `backend/`.

## Current Known Gap

Face verification dependencies are installed, but the InsightFace `buffalo_l` model package still needs a clean model download or offline copy under:

```text
D:\ashotterm\local\models\insightface\models\buffalo_l\
```

Expected files include:

```text
1k3d68.onnx
2d106det.onnx
det_10g.onnx
genderage.onnx
w600k_r50.onnx
```

During this integration run, GitHub connectivity reset while downloading `buffalo_l.zip`, and the partial zip was invalid. Because of that, automatic face verification for each camera upload was temporarily disabled. Once the model files are present, remove or set:

```powershell
$env:CAMERA_UPLOAD_FACE_VERIFY = "1"
```

Then restart the backend from the same venv.

## Demo Notes

- Keep backend computer and Orange Pi on the same reachable network.
- Use `10.75.29.155` only for the current network session; re-check the backend computer IPv4 if the network changes.
- The Web GUI should be opened from the backend computer or another device at `http://<BACKEND_HOST>:5000/`.
- For the final demonstration, the expected stable path is:

```text
Orange Pi camera -> backend /api/camera/upload -> YOLO26s real inference -> Web GUI status/history
```

## 中文演示提示

- 本次成功结果记录的是另一台真实香橙派 `orangepiaipro` 的运行数据，不是本机模拟数据。
- 最终演示建议沿用这次已跑通的拓扑：香橙派连接 USB 摄像头并持续上传图片，本电脑作为后端、数据库、Web GUI 和 YOLO 推理主机。
- 当前已验证的本电脑后端地址是 `http://10.75.29.155:5000/`，Web GUI 也打开这个地址。
- `10.75.29.155` 是当前网络下本电脑的 IPv4；如果换 Wi-Fi、热点、网线或路由器，演示前必须重新查看本电脑 IPv4，并同步修改香橙派 `--base-url`。
- 香橙派端已验证的节点 ID 是 `orange-pi-aipro-remote`，摄像头设备是 `/dev/video0`。
- 演示主线应优先展示：摄像头实时帧上传 -> 后端生成 YOLO26s 真实推理记录 -> Web GUI 状态、历史和最新识别结果刷新。
