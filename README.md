# Short Term Smart Home 2026

2026 国际学院小学期智能家居项目小组协作仓库。

## 项目定位

本仓库用于小组协作，保存项目题目、课件、研发文档、后端/前端/算法代码和可共享资料。

当前分支：`test_webGUI`

`test_webGUI` 分支基于 `test` 分支，专门用于开发第一版 Web GUI。当前后端使用 Flask + SQLite，并用 Orange Pi AIpro 20T 官方规格和模拟信号作为测试数据来源。

## 仓库结构

```text
backend/
  app.py                  Flask + SQLite 后端原型
  requirements.txt        后端 Python 依赖
  data/                   本地 SQLite 数据库目录，.db 文件不提交
  scripts/
    simulate_orange_pi.py Orange Pi AIpro 20T 模拟上报脚本
docs/
  official/              可共享的官方题目文档
  courseware/
    hardware/            硬件组课件、报告模板、元器件清单
    yolo/                YOLO 安装、训练与使用课件
  notes/                 群聊纪要、录音有效信息提取
  proposals/             技术方案、接口讨论和任务规划
local/                   本地材料，默认不提交 Git
```

## 分支约定

- `main`：稳定资料和已确认内容。
- `test`：后端、接口、模拟数据、前端联调等第一版开发内容。
- `test_webGUI`：Web GUI 控制台开发分支。

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

## 后端原型

当前 `test` 分支已提供第一版后端原型：

```powershell
cd D:\大二下\01_课程\short_term_program\backend
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
```

没有真实硬件时，可以用模拟脚本测试 Orange Pi AIpro 20T 数据上报：

```powershell
cd D:\大二下\01_课程\short_term_program\backend
python scripts\simulate_orange_pi.py
```

## 域名与部署约定

- 当前可用域名：`wudilyy666.top`。
- 后端可先运行在小组成员的本地电脑上，演示前再根据实际运行机器配置域名解析、端口转发或内网穿透。
- 若某台机器供电或稳定性不足，优先选择性能更强、运行更稳定的电脑作为后端和算法演示环境。
