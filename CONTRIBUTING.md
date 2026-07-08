# 协作规范

本仓库用于小学期智能家居项目协作。规则尽量简单，目标是让大家能快速提交、快速联调，同时避免误传大文件和个人信息。

## 分支使用

- `main`：稳定资料和最终验收版本，不直接开发。
- `test`：主要开发和联调分支，后端、硬件、算法、前端都以这里为基础。
- `feature/web-gui`：Web GUI 控制台开发分支。
- `feature/xxx`：个人或小功能分支，从 `test` 拉出，例如 `feature/hardware-http`、`feature/yolo-api`。

建议流程：

```powershell
git checkout test
git pull
git checkout -b feature/your-task
```

短期项目允许直接 push 到自己的功能分支；小改动确认无冲突后也可以直接 push 到 `test`。涉及接口、数据库结构、公共文件的大改动，建议先在群里或 issue 里说一声。

## 提交信息

提交信息写清楚做了什么即可，建议用简短动词开头：

```text
Add sensor history API
Fix dashboard layout
Update hardware interface notes
Docs add YOLO result contract
```

中文也可以，例如：

```text
补充硬件 HTTP 接口说明
修复控制台移动端布局
```

## 目录约定

```text
backend/        后端服务、数据库、接口、模拟脚本
docs/           官方资料、课件、方案、接口讨论和会议纪要
models/         模型文件说明；不要提交真实权重文件
local/          本地临时材料，默认不提交
```

如果新增接口说明，建议放在：

```text
docs/interfaces/
```

例如：

```text
docs/interfaces/hardware-http-contract.md
docs/interfaces/yolo-result-contract.md
docs/interfaces/face-access-contract.md
```

## Issue 使用

以下内容建议开 issue 或在已有 issue 下评论：

- 接口字段确认
- 硬件组、YOLO 组、前端组之间的联调问题
- bug 和无法复现的问题
- 已完成的开发状态
- 验收演示流程

标题可以这样写：

```text
[接口] 硬件 HTTP 上报字段确认
[后端] 设备控制命令队列开发
[前端] Web GUI 页面联调
[YOLO] 识别结果 JSON 格式确认
```

## 不要提交的内容

不要提交以下内容：

- 个人信息、教师个人信息、账号密码、token
- `.env`
- SQLite 数据库文件，例如 `*.db`
- 模型权重，例如 `*.pt`、`*.onnx`
- 本地日志、缓存、截图、临时文件
- `__pycache__/`

如果不确定某个文件能不能提交，先放到 `local/`，或者在群里问一下。

## 本地运行

后端默认运行方式：

```powershell
cd D:\大二下\01_课程\short_term_program\backend
python -m pip install -r requirements.txt
python app.py
```

默认地址：

```text
http://127.0.0.1:5000/
```

没有真实硬件时，可以用模拟脚本：

```powershell
python scripts\simulate_orange_pi.py
```

## 联调原则

- 先保证接口能返回 JSON，再接前端页面。
- 先用模拟数据跑通，再替换真实硬件或真实模型。
- YOLO、人脸识别、硬件控制的字段格式要同步到文档或 issue。
- 验收前优先保证可演示，不做无关重构。
