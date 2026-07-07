# Orange Pi AIpro 20T 通用联调与重启手册

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
| `<NODE_ID>` | Orange Pi 节点 ID | `orange-pi-aipro-20t` |
| `<TEST_IMAGE>` | Orange Pi 上待上传的测试图片 | `<EDGE_HOME>/test_images/demo.jpg` |

后续命令默认：

```text
<BACKEND_PORT> = 5000
<EDGE_HOME> = ~/smart_home_edge
<EDGE_CLIENT> = ~/smart_home_edge/orange_pi_client.py
<NODE_ID> = orange-pi-aipro-20t
```

## 当前链路目标

第一版采用更稳的分工：

```text
Orange Pi AIpro 20T
-> 采集模拟信号 / 读取测试图片
-> HTTP 上传到后端电脑
-> Flask 后端
-> SQLite 数据库
-> Web GUI 展示
```

YOLO 和人脸识别先运行在后端电脑上。Orange Pi 负责采集、上传和执行控制命令，不要求第一版在 Orange Pi 上部署 YOLO 模型。

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

### 2. 安装依赖

首次运行需要：

```bash
python -m pip install -r backend/requirements.txt
```

如果要使用真实 YOLO 或人脸识别依赖，再安装：

```bash
python -m pip install -r backend/requirements-vision.txt
```

### 3. 启动后端

```bash
python backend/app.py
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

第一版验收口径：

```text
测试图片先放到 Orange Pi
-> Orange Pi 上传图片
-> 后端保存图片
-> 后端把 image_path 交给 YOLO adapter
-> detection_records 入库
-> Web GUI 或 API 查看识别结果
```

YOLO 模型权重、类别表、测试图片和真实推理实现由 YOLO 组交付。后端当前已预留 mock 结果，模型未交付时也能验证上传、入库和前端联调。

### 1. 在 Orange Pi 准备测试图片

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

### 2. 从 Orange Pi 上传图片

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

后端会保存图片并立即生成 YOLO 记录。查看结果：

```text
GET /api/yolo/latest
GET /api/yolo/history
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
