# 当前技术方案讨论稿

> 状态：讨论稿。用于小组对齐方案、向硬件组确认接口、安排第一版实现。

## 已确认方向

- 验收演示预计使用 **Orange Pi AIpro 20T + 模拟信号/外接传感器**，观察前端 GUI 的状态变化。
- 后端和算法服务先运行在 **性能较稳定的游戏本/本地电脑** 上。
- 前端使用 **Web GUI**，演示时可通过域名 `wudilyy666.top` 访问；如果网络配置不稳定，保留局域网 IP 或本机访问作为备用。
- Orange Pi AIpro 20T 与后端通信先走 **HTTP**，不把 MQTT 作为第一版必做项。
- YOLO 优先接入视觉组已经训练好的模型；预训练模型作为备用方案。
- 人脸识别门禁改为预留 **InsightFace buffalo_l** 方案，不再用 YOLO 做人脸门禁；若环境集成困难，再降级为更简单的演示方案。

## Orange Pi AIpro 20T 角色约定

Orange Pi AIpro 20T 是本项目的硬件/边缘端核心设备。根据官方资料，它具备 20TOPS AI 算力、12GB/24GB LPDDR4X 内存、双 2.5G 网口等能力，后续有条件时可以承载更多边缘计算任务。

但为了第一版稳定验收，建议先把 Orange Pi AIpro 20T 定位为：

- 采集模拟信号或外接传感器状态；
- 控制门锁/舵机、灯光、风扇等执行器；
- 通过 HTTP 向后端上传状态；
- 通过轮询或接收 HTTP 请求执行后端下发的控制命令；
- 如摄像头接在 Orange Pi 上，则负责拍照并把图片上传给后端。

第一版暂不强制把 Flask 后端、数据库、YOLO 或人脸识别全部部署到 Orange Pi 上。原因是 AIpro 20T 的 NPU/Ascend/CANN/MindSpore 推理环境需要额外适配，短期内容易变成环境风险。后端和算法先跑在游戏本上，Orange Pi 先稳定完成硬件交互。

## 第一版目标

第一版先跑通完整链路：

```text
Orange Pi AIpro 20T / 硬件模拟信号
  -> HTTP 上报到后端
  -> 后端写入 SQLite / 更新当前状态
  -> Web GUI 实时展示状态变化
  -> GUI 可发出控制请求
  -> 后端返回控制结果或下发给硬件端
```

图像链路的第一版目标：

```text
Orange Pi AIpro 20T / 摄像头或测试图片
  -> 图片先进入 Orange Pi
  -> Orange Pi 拍照或读取本地测试图片
  -> POST /api/camera/upload 上传给后端
  -> 后端保存图片
  -> 后端把保存后的 image_path 交给 YOLO adapter
  -> YOLO 结果写入 detection_records
  -> Web GUI 展示最新识别结果
```

第一版不追求复杂算法训练或实时视频高帧率，优先保证演示稳定。

## 需要向硬件组确认的接口问题

### 1. 硬件端上报方式

需要确认 Orange Pi AIpro 20T 是否能通过 HTTP 向后端发送状态数据。

建议接口：

```text
POST /api/sensor/update
Content-Type: application/json
```

示例数据：

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

### 2. 后端控制硬件方式

需要确认是：

- 后端直接向 Orange Pi 发送 HTTP 请求；
- 还是 Orange Pi 定时向后端轮询控制命令；
- 或者第一版只做前端状态模拟，不实际反控硬件。

建议第一版采用更容易调试的方式：

```text
Orange Pi 定时 GET /api/device/commands
```

这样后端不需要知道 Orange Pi 的固定 IP，也更适合校园网/局域网不稳定场景。

### 3. 模拟信号范围

需要硬件组确认每个模拟信号的含义：

- 温度：真实温度传感器，还是滑动变阻器/模拟值？
- 门窗：按钮/开关模拟，还是实际磁簧/限位开关？
- 灯光亮度：PWM 数值范围是否为 0-100？
- 风扇：真实风扇开关，还是 LED/继电器状态模拟？
- 门禁：舵机开门，还是页面状态模拟？

### 4. 摄像头归属

需要确认摄像头接在：

- 后端电脑；
- Orange Pi AIpro 20T；
- 其他硬件设备。

目前建议第一版按“图片先进入 Orange Pi，Orange Pi 上传，游戏本后端推理”推进：摄像头或测试图片由 Orange Pi 负责采集/读取和上传，但 YOLO 和人脸识别先在后端电脑运行，稳定性更高。

如果摄像头接在 Orange Pi AIpro 20T 上，需要确认：

- Orange Pi 如何拍照；
- 图片如何传给后端，第一版建议走 `POST /api/camera/upload`；
- 第一版上传原图，由后端保存后交给 YOLO；
- 验收时可以先不接真实摄像头，直接把测试图片复制到 Orange Pi，再用 `orange_pi_client.py --upload-image <图片路径>` 上传；
- 拍照命令由硬件/边缘端确认，后端只要求最终能拿到图片文件或 base64 图片数据。

### 5. Orange Pi 环境与网络

需要硬件组确认：

- Orange Pi AIpro 20T 使用什么系统：Ubuntu、openEuler、Orange Pi OS，还是其他；
- 是否能连接到和后端电脑相同的局域网；
- 是否能稳定访问后端电脑的 IP 和端口；
- 是否能运行 Python 脚本，或使用其他语言发送 HTTP 请求；
- 是否需要固定 IP、热点、网线直连或路由器；
- GPIO、PWM、I2C、UART 等接口最终会用到哪些。

## 后端接口草案

```text
GET  /                     Web GUI
GET  /api/status            获取当前状态
POST /api/sensor/update     Orange Pi 上传传感器/模拟信号
POST /api/device/control    前端提交控制请求
GET  /api/device/commands   Orange Pi 轮询待执行命令
POST /api/camera/upload     Orange Pi 上传图片，后端保存后交给 YOLO
POST /api/yolo/detect       YOLO 物体识别
POST /api/face/verify       InsightFace 人脸门禁
GET  /api/face/users        授权人员列表
POST /api/face/users        新增授权人员，可附带注册照路径
POST /api/face/users/<id>/images  给授权人员追加注册照
GET  /api/face/gallery      查看人脸注册照目录状态
GET  /api/history           查询历史记录
```

## 算法部分策略

### YOLO

- 第一版：优先接入视觉组已经训练好的 YOLO26s 模型，做单张图片或低频识别。
- 备用方案：如果自训练模型集成时间不够，则使用 Ultralytics 预训练模型识别人、车等常见类别。
- 视觉组当前交付模型路径：`training/models/object_fire400_drone2800_yolo26s_v1_best.pt`。
- 模型权重不直接提交 Git，通过 Release、共享盘或网盘分发；后端通过 `MODEL_PATH` 指向本地模型。
- YOLO 权重、类别表、测试图片和真实推理文件由 YOLO 组交付；后端只负责把上传后的图片路径交给 YOLO adapter。
- Orange Pi 上传图片后，后端必须触发 YOLO 记录，不应只保存图片。
- 第一版输入：`image_path: str`。
- 第一版输出：`result_image_path`、`detections`、`model`。
- 视觉组已提供 `training/` 目录中的训练、验证和接口说明；后端 adapter 已按该路径优先适配。

当前类别：

```text
0: fire_extinguisher
1: drone
```

### 人脸识别

- 第一版目标：完成 2 名授权人员 + 1 名非授权人员演示。
- 优先方案：InsightFace `buffalo_l`。
- 计划使用：SCRFD 人脸检测、5 点关键点、ArcFace 标准对齐、w600k_r50 embedding、cosine similarity 比对。
- 视觉组当前建议阈值：cosine similarity `0.40`，`min_margin = 0.05`；后续用实际注册照和测试照重新标定。
- 后端预留 `verify_face(image_path)`，返回 `matched`、`user_id`、`name`、`score`、`threshold`、`min_margin`、`score_margin`、`bbox`、`landmarks_5`、`engine`、`model_pack` 等字段。
- 识别通过后：前端显示授权通过，后端记录日志，并触发开门状态。
- 识别失败后：前端显示未授权，门锁不打开。

## 还需要团队确认的问题

1. 后端最终运行在哪台电脑上，是否确定使用游戏本？
2. 域名 `wudilyy666.top` 谁负责解析、反代、内网穿透或端口转发？
3. Orange Pi AIpro 20T 能否按 JSON 格式走 HTTP 上报？
4. 控制链路采用“后端主动发给 Orange Pi”还是“Orange Pi 轮询后端命令”？
5. 摄像头最终接在哪里？
6. YOLO 组能否提供正式模型文件、类别表、测试图片和 `detect_image(image_path)`？
7. 人脸识别环境由谁搭，InsightFace 注册照/阈值如何标定？
8. GUI 需要哪些页面：只做 Dashboard，还是再加历史记录页/人员录入页？
9. 验收时是否需要手机访问，还是电脑浏览器演示即可？

## 建议下一步

- 先向硬件组确认 Orange Pi AIpro 20T 的系统环境、HTTP 接口、模拟信号含义、摄像头连接方式。
- 软件组先做 Flask + SQLite + Web GUI 空壳，用模拟数据跑通页面。
- Orange Pi 接口未定前，后端先提供 `/api/sensor/update` 和 `/api/status`，方便硬件组联调。
- YOLO、人脸识别先独立做 demo，等后端基本接口稳定后再接入 GUI。
