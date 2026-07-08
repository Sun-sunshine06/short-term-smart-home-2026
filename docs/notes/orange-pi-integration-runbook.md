# Orange Pi AIpro 昇腾开发板通用联调与重启手册

> 更新时间：2026-07-07。本文面向任意小组成员，不绑定某一台电脑、某一个 IP 或某一个用户目录。使用前先把占位符替换成自己的实际环境。

## 占位符约定

| 占位符 | 含义 | 示例 |
| --- | --- | --- |
| `<PROJECT_ROOT>` | 本仓库在后端电脑上的根目录 | Windows: `<path>\short_term_program`; Linux/macOS: `/path/to/short_term_program` |
| `<BACKEND_HOST>` | 后端电脑在当前局域网中的 IPv4 地址 | `192.168.1.23` |
| `<BACKEND_PORT>` | Flask 后端端口 | `5000` |
| `<BACKEND_BASE_URL>` | 后端完整地址 | `http://<BACKEND_HOST>:<BACKEND_PORT>` |
| `<EDGE_HOME>` | Orange Pi 上保存边缘脚本的目录 | `~/smart_home_edge` |
| `<EDGE_CLIENT>` | Orange Pi 边缘脚本路径 | `<EDGE_HOME>/orange_pi_client.py` |
| `<NODE_ID>` | Orange Pi 节点 ID | `orange-pi-aipro-ascend` |
| `<TEST_IMAGE>` | Orange Pi 上待上传的测试图片 | `<EDGE_HOME>/test_images/demo.jpg` |

后续命令默认：

```text
<BACKEND_PORT> = 5000
<EDGE_HOME> = ~/smart_home_edge
<EDGE_CLIENT> = ~/smart_home_edge/orange_pi_client.py
<NODE_ID> = orange-pi-aipro-ascend
```

## 当前链路目标

第一版采用更稳的分工：

```text
Orange Pi AIpro 昇腾开发板
-> 采集模拟信号 / 读取测试图片
-> HTTP 上传到后端电脑
-> Flask 后端
-> SQLite 数据库
-> Web GUI 展示
```

YOLO 和人脸识别先运行在后端电脑上。Orange Pi 负责采集、上传和执行控制命令，不要求第一版在 Orange Pi 上部署 YOLO 模型。若后续老师要求展示昇腾板端推理，再单独接 CANN/MindSpore/ACLLite 环境。

## 开发板替换影响

如果领取到的不是昇腾版 Orange Pi AIpro，而是混入的鲲鹏开发板，应按老师要求更换为昇腾开发板。更换后对本项目第一版流程的影响如下：

- 不影响：Flask 后端、SQLite 数据库、Web GUI、HTTP 上报、命令轮询、图片上传接口；
- 不影响：YOLO 第一版仍然先在后端电脑运行，Orange Pi 只负责把本地图片上传给后端；
- 需要重新确认：开发板系统镜像、默认用户、IP 获取方式、Python 版本、网络连接方式；
- 需要重新确认：GPIO/PWM/I2C/摄像头接口的实际可用方式；
- 需要更新显示信息：Web GUI 和硬件 Profile 不应写死 `20T`，应按实际换到的昇腾型号填写；
- 暂不作为第一版必做：CANN、MindSpore、ACLLite、Jupyter Lab、板端目标检测样例。

老师发的《手把手教你搭建 OrangePi AIpro 开发环境》主要用于昇腾板系统准备和 AI 环境搭建。它说明 AIpro 走昇腾路线，涉及 Ubuntu 镜像烧录、SSH/网线/Wi-Fi 登录、CANN、ACLLite、MindSpore 和 Jupyter Lab 示例。除非验收要求板端 AI 推理，否则这些内容不会改变当前“Orange Pi 上传，后端推理”的软件闭环。

## 已验证能力

当前软件链路设计支持：

- Orange Pi 调用 `GET /api/health` 检查后端连通性；
- Orange Pi 调用 `POST /api/edge/register` 登记节点信息；
- Orange Pi 调用 `POST /api/edge/heartbeat` 上报在线心跳和系统资源；
- Orange Pi 调用 `POST /api/sensor/update` 上报传感器或模拟状态；
- Orange Pi 调用 `GET /api/device/commands` 轮询待执行命令；
- Orange Pi 调用 `POST /api/device/commands/<id>/ack` 回传命令执行结果；
- Orange Pi 调用 `POST /api/camera/upload` 上传本地图片，后端保存后交给 YOLO adapter；
- 后端写入 SQLite，Web GUI 展示状态和历史数据。

2026-07-08 已记录一次真实 Orange Pi + USB 摄像头联调成功结果。该次测试使用另一台香橙派 `orangepiaipro`，通过 `/dev/video0` 持续上传摄像头帧到后端电脑，并在后端项目 venv 中运行真实 YOLO26s 推理。详细记录见：

```text
docs/notes/orange-pi-camera-demo-2026-07-08.md
```

当前传感器字段仍可先用脚本模拟：

- `temperature`
- `door_open`
- `window_open`
- `light_level`
- `fan_on`
- `lock_open`

硬件组确认真实引脚和传感器后，再替换 `edge/orange_pi_client.py` 中的数据来源。

## 后端电脑启动流程

### 1. 进入仓库目录

Windows PowerShell：

```powershell
cd <PROJECT_ROOT>
```

Linux/macOS shell：

```bash
cd <PROJECT_ROOT>
```

### 2. 创建项目虚拟环境并安装依赖

推荐把依赖安装到仓库内的 `.venv`，并把 pip 缓存、临时目录和 InsightFace 模型包放到 `local/`，避免占用系统 Python 或 C 盘用户目录。

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force -Path .\local\pip-cache, .\local\tmp, .\local\models\insightface | Out-Null
python -m venv .venv
$env:PIP_CACHE_DIR = (Resolve-Path .\local\pip-cache).Path
$env:TMP = (Resolve-Path .\local\tmp).Path
$env:TEMP = (Resolve-Path .\local\tmp).Path
$env:INSIGHTFACE_HOME = (Resolve-Path .\local\models\insightface).Path
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

如果要使用真实 YOLO 或人脸识别依赖，再安装视觉依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-vision.txt
.\.venv\Scripts\python.exe -m pip install scikit-image scikit-learn
```

Linux/macOS shell：

```bash
mkdir -p local/pip-cache local/tmp local/models/insightface
python3 -m venv .venv
export PIP_CACHE_DIR="$(pwd)/local/pip-cache"
export TMPDIR="$(pwd)/local/tmp"
export INSIGHTFACE_HOME="$(pwd)/local/models/insightface"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m pip install -r backend/requirements-vision.txt
.venv/bin/python -m pip install scikit-image scikit-learn
```

### 3. 启动后端

Windows PowerShell：

```powershell
$env:INSIGHTFACE_HOME = (Resolve-Path .\local\models\insightface).Path
.\.venv\Scripts\python.exe backend\app.py
```

Linux/macOS shell：

```bash
export INSIGHTFACE_HOME="$(pwd)/local/models/insightface"
.venv/bin/python backend/app.py
```

本机检查：

```text
http://127.0.0.1:<BACKEND_PORT>/api/health
```

同一局域网内其他设备访问：

```text
http://<BACKEND_HOST>:<BACKEND_PORT>/api/health
```

Web GUI：

```text
http://127.0.0.1:<BACKEND_PORT>/
```

如果要从其他设备访问 Web GUI：

```text
http://<BACKEND_HOST>:<BACKEND_PORT>/
```

## 获取后端电脑 IP

每次更换 Wi-Fi、热点、路由器或网线后，`<BACKEND_HOST>` 都可能变化。

Windows PowerShell：

```powershell
ipconfig
```

Linux/macOS shell：

```bash
ip addr
```

选择和 Orange Pi 在同一网络下的 IPv4 地址，把它填入：

```text
<BACKEND_BASE_URL> = http://<BACKEND_HOST>:<BACKEND_PORT>
```

## Orange Pi 启动与连通性检查

### 1. 开机并接入同一网络

确保 Orange Pi 和后端电脑在同一个 Wi-Fi、热点、路由器或同一可互通网段内。

### 2. 查看 Orange Pi IP

在 Orange Pi 终端执行：

```bash
hostname -I
```

看到与 `<BACKEND_HOST>` 同网段或可互通的 IP 后继续。

### 3. 测试访问后端

```bash
curl http://<BACKEND_HOST>:<BACKEND_PORT>/api/health
```

返回中看到 `"ok": true` 即表示 Orange Pi 可以访问后端。

## 部署或更新 Orange Pi 边缘脚本

仓库中的脚本路径：

```text
edge/orange_pi_client.py
```

Orange Pi 推荐保存路径：

```text
<EDGE_CLIENT>
```

在 Orange Pi 上先创建目录：

```bash
mkdir -p <EDGE_HOME>
```

然后把仓库里的 `edge/orange_pi_client.py` 复制到 Orange Pi 的 `<EDGE_CLIENT>`。复制方式不限，可以用 U 盘、SCP、远程终端粘贴、Git 拉取或临时 HTTP 下载。

## 传感器和心跳测试

短测 3 次：

```bash
python3 <EDGE_CLIENT> \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --count 3
```

持续运行：

```bash
python3 <EDGE_CLIENT> \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --interval 2
```

后端电脑可检查：

```text
GET /api/status
GET /api/history
GET /api/edge/nodes
GET /api/edge/heartbeats
```

浏览器也可以打开：

```text
http://<BACKEND_HOST>:<BACKEND_PORT>/
```

## 图像上传与 YOLO 流程

验收主线建议改为“摄像头低频实时上传”，不先做复杂视频流：

```text
摄像头接入 Orange Pi
-> Orange Pi 每隔 0.5-2 秒取一帧 JPEG
-> Orange Pi 上传图片
-> 后端保存图片
-> 后端把 image_path 交给 YOLO adapter 和 InsightFace adapter
-> detection_records / access_logs 入库
-> Web GUI 展示视觉识别、门禁识别和门锁状态
```

测试图片上传仍然保留为备用验证方式：摄像头未接好时，先用本地图片验证上传、入库和前端联调。YOLO 模型权重、类别表、测试图片和真实推理实现由 YOLO 组交付。后端当前已接入真实 YOLO 权重；如果模型或依赖缺失，会降级为 mock 结果以保证联调不中断。人脸识别默认使用 `FACE_GALLERY_DIR` 下的授权人员图库，摄像头上传后会同步写入门禁日志，并按人脸是否匹配更新 `lock_open`。

### 1. 摄像头低频实时上传

先确认后端可访问：

```bash
curl http://<BACKEND_HOST>:<BACKEND_PORT>/api/health
```

启动摄像头模式：

```bash
python3 <EDGE_CLIENT> \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --camera \
  --camera-device 0 \
  --camera-interval 1 \
  --camera-count 30
```

含义：

- `--camera`：进入摄像头取帧上传模式；
- `--camera-device 0`：默认读取 `/dev/video0`；
- `--camera-interval 1`：每秒上传一帧；
- `--camera-count 30`：上传 30 帧后退出；演示时可去掉，让脚本持续运行。

脚本会优先用 Python OpenCV 读取摄像头；如果没有 OpenCV，会自动尝试 `libcamera-still`、`fswebcam` 或 `ffmpeg`。也可以手动指定拍照命令：

```bash
python3 <EDGE_CLIENT> \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --camera \
  --camera-command 'fswebcam -d "{device}" -r {width}x{height} --no-banner "{output}"'
```

如果摄像头不是 `/dev/video0`，先查看设备：

```bash
ls /dev/video*
```

再把 `--camera-device 0` 换成正确编号或路径，例如：

```bash
--camera-device /dev/video2
```

USB UVC 摄像头接入后也可以用下面命令排查：

```bash
lsusb
v4l2-ctl --list-devices
fswebcam -d /dev/video0 -r 640x480 --no-banner /tmp/smart_home_camera_probe.jpg
ls -l /tmp/smart_home_camera_probe.jpg
```

如果 `lsusb` 看不到摄像头，说明系统尚未识别设备，优先检查是否插在 Orange Pi 上、USB 口是否松动、供电是否稳定。若能看到摄像头但没有 `/dev/video*`，再考虑驱动或权限问题。

当前链路已经按 USB UVC 摄像头验证通过：

```text
USB Camera -> /dev/video0 -> Orange Pi 取帧 -> POST /api/camera/upload
-> 后端保存图片 -> YOLO 记录入库 -> 人脸门禁记录入库
-> /api/status camera_online=true，lock_open 跟随人脸结果
```

### 2. 在 Orange Pi 准备测试图片

推荐目录：

```bash
mkdir -p <EDGE_HOME>/test_images
```

把测试图片放到：

```text
<TEST_IMAGE>
```

例如：

```text
<EDGE_HOME>/test_images/demo.jpg
```

### 3. 从 Orange Pi 上传图片

```bash
python3 <EDGE_CLIENT> \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --upload-image <TEST_IMAGE>
```

脚本会读取 Orange Pi 本地图片，调用：

```text
POST /api/camera/upload
```

后端会保存图片并立即生成 YOLO 记录和人脸门禁记录。查看结果：

```text
GET /api/yolo/latest
GET /api/yolo/history
GET /api/face/latest
GET /api/face/history
```

## 当前已确认接口

```text
GET  /api/health
GET  /api/status
GET  /api/history
GET  /api/edge/nodes
GET  /api/edge/heartbeats
POST /api/edge/register
POST /api/edge/heartbeat
POST /api/sensor/update
POST /api/device/control
GET  /api/device/commands
POST /api/device/commands/<id>/ack
POST /api/camera/upload
POST /api/yolo/detect
GET  /api/yolo/latest
GET  /api/yolo/history
POST /api/face/verify
GET  /api/face/latest
GET  /api/face/history
```

## 关机与下次恢复

关机前建议：

1. 停止 Orange Pi 上正在运行的 `orange_pi_client.py`；
2. 停止后端电脑上的 Flask 进程；
3. 正常关闭 Orange Pi 电源；
4. 断开网络或电源。

下次恢复：

1. 后端电脑启动 `python backend/app.py`；
2. 获取新的 `<BACKEND_HOST>`；
3. Orange Pi 开机并接入同一网络；
4. Orange Pi 执行 `curl http://<BACKEND_HOST>:<BACKEND_PORT>/api/health`；
5. 跑传感器短测；
6. 跑图片上传短测；
7. 打开 Web GUI 查看状态。

## 常见问题

### Orange Pi 访问不到后端

- 确认后端电脑和 Orange Pi 在同一网络或路由可达；
- 确认 `<BACKEND_HOST>` 是后端电脑当前网络的 IPv4，不是虚拟网卡地址；
- 确认 Flask 正在监听 `0.0.0.0:<BACKEND_PORT>`；
- 检查防火墙是否拦截 `<BACKEND_PORT>`；
- 在后端电脑本机先访问 `http://127.0.0.1:<BACKEND_PORT>/api/health`。

### Web GUI 能打开但没有硬件数据

- 确认 Orange Pi 正在运行 `orange_pi_client.py`；
- 检查 `/api/edge/nodes` 是否有节点；
- 检查 `/api/history` 是否有传感器记录；
- 检查脚本 `--base-url` 是否指向正确的 `<BACKEND_BASE_URL>`。

### 上传图片后只有 mock 结果

这是预期降级行为，说明上传和入库链路可用，但真实 YOLO 模型或依赖还未接好。需要 YOLO 组补齐：

- 模型权重；
- 类别表；
- 测试图片；
- 运行依赖；
- `detect_image(image_path)` 的真实推理链路。

### 换网络后无法恢复

重新执行“获取后端电脑 IP”和“Orange Pi 测试访问后端”两步。大多数问题来自 `<BACKEND_HOST>` 变化。

## 硬件组需要补充的信息

- 温度或模拟量来自哪个传感器或 ADC；
- 门窗状态对应哪个 GPIO；
- 灯光亮度是否需要 PWM，范围是否为 0-100；
- 风扇是 GPIO 开关、继电器还是 PWM；
- 门锁或舵机使用哪个 GPIO/PWM；
- 高低电平含义；
- 是否需要上拉/下拉、电平转换、外接驱动模块；
- 是否需要在 Orange Pi 上安装额外 GPIO/PWM/I2C 库；
- 摄像头接入方式和拍照命令。

确认后主要修改：

```text
edge/orange_pi_client.py
```

重点替换：

```python
build_mock_payload(...)
handle_command(...)
```
