# Orange Pi AIpro 环境与网线直连检查记录 - 2026-07-09

本文记录一次真实 Orange Pi AIpro 昇腾开发板环境检查结果，用于验收前确认开发板型号、CANN 环境和稳定直连网络。

## 连接方式

已通过 Wi-Fi SSH 临时接入开发板，并写入本仓库 `local/ssh/orangepi_codex_ed25519.pub` 对应公钥。随后配置有线直连通道：

```text
后端电脑以太网 IPv4：192.168.1.100/24
Orange Pi eth0 IPv4：192.168.1.101/24
Orange Pi Wi-Fi IPv4：10.75.29.240/24
```

电脑到 Orange Pi 的网线直连已验证：

```powershell
ping 192.168.1.101
ssh -i local\ssh\orangepi_codex_ed25519 HwHiAiUser@192.168.1.101
```

Orange Pi 侧 `eth0` 状态：

```text
eth0 UP 192.168.1.101/24
```

## 系统与用户

```text
hostname: orangepiaipro
user: HwHiAiUser
OS: Ubuntu 22.04.3 LTS
Python: 3.10.12
```

## NPU 检查

`npu-smi info` 已能识别昇腾设备：

```text
npu-smi: 23.0.0
NPU Name: 310B4
Health: Alarm
Temp(C): 58
Memory-Usage(MB): 1844 / 15609
Hugepages-Usage(page): 15 / 15
```

结论：开发板已确认是昇腾路线 AIpro，具备 310B4 NPU。`Health=Alarm` 需要记录，但当前项目主线是 Orange Pi 采集上传、后端电脑推理，不依赖板端 NPU 推理，因此不阻塞当前演示链路。若后续必须跑板端 AI 推理，应继续排查告警原因。

## CANN / Ascend 环境

已确认以下路径存在：

```text
/usr/local/Ascend/ascend-toolkit/set_env.sh
/usr/local/Ascend/ascend-toolkit/7.0.0/aarch64-linux/script/set_env.sh
/usr/local/Ascend/thirdpart/aarch64/acllite
```

加载环境后可找到 ATC：

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
which atc
```

结果：

```text
/usr/local/Ascend/ascend-toolkit/latest/bin/atc
ASCEND_HOME_PATH=/usr/local/Ascend/ascend-toolkit/latest
ASCEND_TOOLKIT_HOME=/usr/local/Ascend/ascend-toolkit/latest
```

## 官方 YOLOv5 样例

老师指南中的板端 YOLOv5 示例目录存在：

```text
/home/HwHiAiUser/samples/notebooks/01-yolov5
```

目录中已确认包含：

```text
coco_names.txt
det_utils.py
main.ipynb
racing.mp4
world_cup.jpg
yolo.om
yolov5s.onnx
```

这说明官方 Jupyter/OM 模型样例文件在板端可用。当前项目暂不依赖该样例；若验收要求使用 AIpro 板端 NPU 推理，可从此目录继续验证 `yolo.om`。

## 摄像头状态

当前检查时未检测到摄像头设备：

```text
ls: cannot access '/dev/video*': No such file or directory
```

已安装/可用的拍照相关工具：

```text
/usr/bin/v4l2-ctl
/usr/bin/fswebcam
/usr/bin/ffmpeg
```

当前 Python 环境未安装 OpenCV：

```text
cv2 missing
```

结论：摄像头插上后应先跑：

```bash
ls /dev/video*
v4l2-ctl --list-devices
fswebcam -d /dev/video0 -r 640x480 --no-banner /tmp/smart_home_camera_probe.jpg
ls -l /tmp/smart_home_camera_probe.jpg
```

项目边缘脚本可在没有 OpenCV 时自动回退到 `fswebcam` 或 `ffmpeg`，所以 `cv2 missing` 不阻塞当前上传路线。

## 项目边缘脚本

已将仓库最新版边缘脚本复制到：

```text
/home/HwHiAiUser/smart_home_edge/orange_pi_client.py
```

版本：

```text
CLIENT_VERSION = "0.3.1"
```

语法检查已通过：

```bash
python3 -m py_compile ~/smart_home_edge/orange_pi_client.py
```

## 明天恢复命令

后端电脑启动 Flask 后，Orange Pi 可通过网线直连访问：

```bash
curl http://192.168.1.100:5000/api/health
```

短测：

```bash
python3 ~/smart_home_edge/orange_pi_client.py \
  --base-url http://192.168.1.100:5000 \
  --node-id orange-pi-aipro-ascend \
  --count 3
```

摄像头模式：

```bash
python3 ~/smart_home_edge/orange_pi_client.py \
  --base-url http://192.168.1.100:5000 \
  --node-id orange-pi-aipro-ascend \
  --camera \
  --camera-device 0 \
  --camera-interval 0.5
```
