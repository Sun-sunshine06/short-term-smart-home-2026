# Short Term Smart Home 2026

硬件组参考源码：[两块 Arduino 工程与使用说明](hardware/arduino/README.md)。尚未确认与板上固件一致，信息采集阶段不要直接烧录。

> **2026-11-17 架构更新：** 摄像头改接电脑，香橙派作为 Arduino 硬件网关，Arduino 保留本地自动控制。分工已确认，通信接线与实现仍待验证。详见 [分工决定与实施方案](docs/proposals/pc-camera-hardware-gateway-2026-11-17.md)。下文保留原有实现说明，新架构尚未落地。

2026 国际学院小学期智能家居项目小组协作仓库。

## 项目定位

本仓库用于小组协作，保存项目题目、课件、研发文档、后端/前端/算法代码和可共享资料。

当前分支：`feature/web-gui`

`feature/web-gui` 分支基于 `test` 分支，专门用于开发第一版 Web GUI。当前后端使用 Flask + SQLite，并用 Orange Pi AIpro 昇腾开发板通用规格和模拟信号作为测试数据来源。

## 仓库结构

```text
backend/
  app.py                  Flask + SQLite 后端原型
  requirements.txt        后端 Python 依赖
  data/                   本地 SQLite 数据库目录，.db 文件不提交
  scripts/
    simulate_orange_pi.py Orange Pi AIpro 模拟上报脚本
edge/
  orange_pi_client.py     香橙派端 HTTP 上报与命令轮询脚本
training/                 YOLO 物体检测与 InsightFace 人脸门禁代码、权重和验收样例
docs/
  official/              可共享的官方题目文档
  courseware/
    hardware/            硬件组课件、报告模板、元器件清单
    yolo/                YOLO 安装、训练与使用课件
  notes/                 群聊纪要、录音有效信息提取
    orange-pi-integration-runbook.md  香橙派联调状态和重启手册
    orange-pi-camera-demo-2026-07-08.md  香橙派摄像头实机联调记录
  proposals/             技术方案、接口讨论和任务规划
local/                   本地材料，默认不提交 Git
```

## 分支约定

- `main`：稳定资料和已确认内容。
- `test`：后端、接口、模拟数据、前端联调等第一版开发内容。
- `feature/web-gui`：Web GUI 控制台开发分支。

多人协作时，建议先从 `test` 开小分支开发，确认可用后再合并回 `test`；验收前再从 `test` 合并稳定内容到 `main`。

## 近期节点

- 2026-07-07 08:50：YOLO 训练和使用方法讲解，地点 3-437。
- 2026-07-08 08:50：香橙派使用讲解，地点 3-437。
- 2026-07-08：小组建议对一次进度。
- 2026-07-09 晚：发布验收顺序。
- 2026-07-10 14:00：项目验收。

## 项目方向

题目为智能家居模型，重点包括自动门禁、摄像头、本地保存照片、YOLO 物体识别、人脸识别开门、温度监控、门窗状态、灯光亮度、GUI、历史数据查询和后端数据库。

当前技术判断：短期内优先使用本地电脑作为后端和算法运行环境，YOLO 可先用预训练模型完成通用物体识别，数据库优先 SQLite，GUI 优先 Web。

## 视觉模型权重

- YOLO 推理权重已提交到仓库：`training/models/object_fire400_drone2800_yolo26s_v1_best.pt`。
- 2026-07-10 新增 YOLO v2 清洗后重训权重：`training/models/object_fire400_drone2630_yolo26s_v2_face_removed_pretrained_best.pt`。该权重使用官方 `yolo26s.pt` 基模训练，并保留 v1 权重以兼容现有调用。
- InsightFace `buffalo_l` ONNX 权重体积较大，放在 GitHub Release：`vision-models-v1`。
- 下载地址：`https://github.com/Sun-sunshine06/short-term-smart-home-2026/releases/download/vision-models-v1/buffalo_l.zip`。
- 离线运行人脸识别时，将 `buffalo_l.zip` 解压到 `<USER_HOME>/.insightface/models/buffalo_l/`。

## 后端原型

当前 `test` 分支已提供第一版后端原型：

```powershell
cd <PROJECT_ROOT>\backend
python -m pip install -r requirements.txt
python app.py
```

默认服务地址：

```text
http://127.0.0.1:5000
```

打开根路径即可访问 Web GUI：

```text
http://127.0.0.1:5000/
```

常用接口：

```text
GET  /api/health
GET  /api/hardware/profile
GET  /api/status
POST /api/sensor/update
POST /api/device/control
GET  /api/device/commands
GET  /api/history
POST /api/yolo/detect
POST /api/face/access
GET  /api/face/users
POST /api/face/users
POST /api/face/users/<id>/images
GET  /api/face/gallery
```

没有真实硬件时，可以用模拟脚本测试 Orange Pi AIpro 数据上报：

```powershell
cd <PROJECT_ROOT>\backend
python scripts\simulate_orange_pi.py
```

2026-07-08 已完成一次真实 Orange Pi + USB 摄像头联调，后端电脑运行 Web GUI 和真实 YOLO 推理，香橙派持续上传摄像头帧。记录见：

```text
docs/notes/orange-pi-camera-demo-2026-07-08.md
```

## 域名与部署约定

- 当前可用域名：`wudilyy666.top`。
- 后端可先运行在小组成员的本地电脑上，演示前再根据实际运行机器配置域名解析、端口转发或内网穿透。
- 若某台机器供电或稳定性不足，优先选择性能更强、运行更稳定的电脑作为后端和算法演示环境。
