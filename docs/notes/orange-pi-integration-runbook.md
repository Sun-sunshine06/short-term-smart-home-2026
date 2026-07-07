# Orange Pi AIpro 20T 联调状态与重启手册

> 更新时间：2026-07-07。本文记录当前已经跑通的链路、给小组同步用的话术，以及关机/断开网络后下一次恢复联调的步骤。

## 当前状态

已经完成：

```text
Orange Pi AIpro 20T
-> openEuler
-> Python 3.9.9
-> HTTP 上报
-> Flask 后端
-> SQLite
-> Web GUI 状态刷新
```

本次实测信息：

- Orange Pi 用户：`openEuler`
- Orange Pi 系统：`openEuler aarch64`
- Orange Pi 当前同网段 IP：`10.200.77.110`
- 后端电脑当前 IP：`10.200.77.182`
- 后端地址：`http://10.200.77.182:5000`
- Web GUI 本机地址：`http://127.0.0.1:5000/`
- Orange Pi 端脚本路径：`/home/openEuler/smart_home_edge/orange_pi_client.py`

已验证：

- Orange Pi 可以访问 `GET /api/health`。
- Orange Pi 可以调用 `POST /api/sensor/update`。
- Orange Pi 可以调用 `POST /api/edge/register` 登记节点信息。
- Orange Pi 可以调用 `POST /api/edge/heartbeat` 上报在线心跳和系统资源。
- 后端可以写入 SQLite。
- Web GUI 可以看到状态变化。
- Orange Pi 端脚本可以轮询 `GET /api/device/commands` 并 ack 命令。

当前仍是模拟输入：

- `temperature`
- `door_open`
- `window_open`
- `light_level`
- `fan_on`
- `lock_open`

这些字段现在由脚本生成。硬件组给出实际引脚/传感器方案后，只需要替换 `edge/orange_pi_client.py` 中的数据来源。

## 图像采集和上传流程

第一版约定：**图像采集/图片入口走 Orange Pi，YOLO 推理先走后端游戏本**。Orange Pi 不需要先部署 YOLO 模型，它只负责拿到图片、保存本地图片、通过 HTTP 上传给后端。

推荐链路：

```text
摄像头 / 测试图片
-> 图片先放到 Orange Pi
-> POST /api/camera/upload 上传到后端
-> 后端保存到 backend/data/uploads/camera/
-> 后端把保存后的 image_path 交给 YOLO adapter
-> detection_records 入库
-> Web GUI / API 查询识别结果
```

注意：上传图片不是只做文件保存，后端收到图片后应立即把保存后的 `image_path` 交给 YOLO 流程。当前后端接口 `POST /api/camera/upload` 已按这个方向预留：上传成功后会返回 `image_path` 和 `yolo_record`。

YOLO 相关模型文件和推理实现由 YOLO 组交付：

- 模型权重：`training/models/object_fire400_drone2800_yolo26s_v1_best.pt`
- 类别表和测试图片；
- 必要的运行依赖；
- `detect_image(image_path)` 的真实推理实现或确认当前 adapter 可用。

在 YOLO 文件未交付前，后端会使用 mock 检测结果保证上传、入库和前端联调可以继续。

验收时如果暂时不接真实摄像头，可以直接把测试图片复制到 Orange Pi，例如：

```text
/home/openEuler/smart_home_edge/test_images/demo.jpg
```

然后在 Orange Pi 上执行：

```bash
python3 ~/smart_home_edge/orange_pi_client.py \
  --base-url http://<BACKEND_IP>:5000 \
  --node-id orange-pi-aipro-20t \
  --upload-image ~/smart_home_edge/test_images/demo.jpg
```

这条命令会从 Orange Pi 本地读取图片，上传到 `POST /api/camera/upload`，后端保存图片并立即交给 YOLO 流程。结果可以在 Web GUI 或下面接口查看：

```text
GET /api/yolo/latest
GET /api/yolo/history
```

## 给小组同步的话术

可以直接发到群里：

```text
目前 Orange Pi AIpro 20T 已经开机并接入网络，软件侧链路已经跑通：

香橙派 openEuler -> Python 脚本 -> HTTP 上报 -> Flask 后端 -> SQLite -> Web GUI 展示。

我们已经实测从香橙派向后端 POST /api/sensor/update 成功，前端控制台可以看到状态变化；同时香橙派会向 /api/edge/register 和 /api/edge/heartbeat 上报节点信息、IP 和基础资源状态，后端数据库可以记录板子是否在线。香橙派端也能轮询 /api/device/commands，后续可以接硬件执行。

图像链路按“图片先进入 Orange Pi，Orange Pi 上传，游戏本后端做 YOLO”处理。验收时可以直接把测试图片放进香橙派，再运行 orange_pi_client.py 的 --upload-image；后端已预留 /api/camera/upload，上传图片会保存并交给 YOLO 检测流程；YOLO 权重、类别表和真实推理文件由 YOLO 组交付。

现在还差硬件组确认真实模拟输入/执行器的接线和含义，例如门窗开关、灯光亮度、风扇、门锁/舵机分别接哪个 GPIO/PWM/I2C/ADC。确认后只需要把 orange_pi_client.py 里生成 mock 数据的部分替换成真实读取即可。
```

更短版本：

```text
香橙派到后端和前端的链路已跑通：Orange Pi -> HTTP -> Flask/SQLite -> Web GUI。现在后端已能记录香橙派节点在线心跳，传感器部分仍是脚本模拟数据，等硬件组确认引脚和传感器定义后，把脚本的数据源替换成真实 GPIO/传感器读取即可。
```

## 关机/断开后下次恢复步骤

### 1. 电脑端启动后端

在电脑 PowerShell 中执行：

```powershell
cd D:\大二下\01_课程\short_term_program
python backend\app.py
```

如果已经有后台服务在跑，也可以直接测试：

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

### 2. 电脑端查看当前 IP

每次换 Wi-Fi/热点后，电脑 IP 可能变化。执行：

```powershell
ipconfig
```

找到当前网络的 IPv4 地址，例如：

```text
10.200.77.182
```

后面命令里的 `<BACKEND_IP>` 就替换成这个地址。

### 3. Orange Pi 开机并接入同一网络

确认 Orange Pi 和后端电脑在同一 Wi-Fi/热点/路由器下。

在 Orange Pi 终端执行：

```bash
hostname -I
```

确认能看到同网段 IP，例如：

```text
10.200.77.110
```

### 4. Orange Pi 测试后端连通性

在 Orange Pi 终端执行：

```bash
curl http://<BACKEND_IP>:5000/api/health
```

例如：

```bash
curl http://10.200.77.182:5000/api/health
```

看到 `"ok": true` 即可继续。

### 5. Orange Pi 运行边缘端脚本

短测 3 次：

```bash
python3 ~/smart_home_edge/orange_pi_client.py --base-url http://<BACKEND_IP>:5000 --count 3
```

持续运行：

```bash
python3 ~/smart_home_edge/orange_pi_client.py --base-url http://<BACKEND_IP>:5000 --interval 2
```

运行后电脑打开：

```text
http://127.0.0.1:5000/
```

观察 Web GUI 状态是否变化。

也可以在电脑端检查香橙派节点是否已经写入数据库：

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/edge/nodes
Invoke-RestMethod http://127.0.0.1:5000/api/edge/heartbeats?limit=5
```

## 如果脚本丢失

仓库中有同一份脚本：

```text
edge/orange_pi_client.py
```

可重新复制到 Orange Pi：

```bash
mkdir -p ~/smart_home_edge
```

然后把仓库里的 `edge/orange_pi_client.py` 放到：

```text
/home/openEuler/smart_home_edge/orange_pi_client.py
```

## 当前已确认接口

Orange Pi 上报状态：

```text
POST /api/sensor/update
```

Orange Pi 注册边缘节点：

```text
POST /api/edge/register
```

Orange Pi 上报在线心跳：

```text
POST /api/edge/heartbeat
```

查看边缘节点和心跳历史：

```text
GET /api/edge/nodes
GET /api/edge/heartbeats
```

Orange Pi 上传摄像头图片，并交给 YOLO 检测：

```text
POST /api/camera/upload
```

YOLO 组或后端直接用本地图片触发检测：

```text
POST /api/yolo/detect
```

Orange Pi 轮询控制命令：

```text
GET /api/device/commands
```

Orange Pi ack 命令：

```text
POST /api/device/commands/<id>/ack
```

## 硬件组需要补充的信息

后续接真实硬件时，需要确认：

- 温度/模拟量来自哪个传感器或 ADC；
- 门窗状态对应哪个 GPIO；
- 灯光亮度是否需要 PWM，范围是否为 0-100；
- 风扇是 GPIO 开关、继电器还是 PWM；
- 门锁/舵机使用哪个 GPIO/PWM；
- 高低电平含义：`1` 表示打开还是关闭；
- 是否需要上拉/下拉、电平转换、外接驱动模块；
- 是否需要在 Orange Pi 上安装额外 GPIO/PWM/I2C 库。

确认后修改位置：

```text
edge/orange_pi_client.py
```

重点替换：

```python
build_mock_payload(...)
handle_command(...)
```

