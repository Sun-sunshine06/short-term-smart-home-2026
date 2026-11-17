# 同学电脑拉取与启动

当前新版已合并 main，团队统一从 main 拉取。先检查界面，再接入硬件。

## 首次启动（Windows PowerShell）

安装 Git、uv、Node.js 22.18+（或 24 LTS），在存放项目的目录运行：

```powershell
git clone --branch main https://github.com/Sun-sunshine06/short-term-smart-home-2026.git
cd short-term-smart-home-2026
New-Item -ItemType Directory -Force local
Copy-Item backend/pc.env.example local/sidecar.env
cd frontend
npm ci
npm run build
cd ..
.\backend\scripts\start_backend.ps1
```

访问 **http://127.0.0.1:5000/next/**。没有硬件时打开右上角“演练模式”。
旧页面在 /。frontend/dist 不提交 Git，拉取后必须构建。模板禁用串口及旁路，仅监听本机。

脚本使用 uv 管理依赖，读取 local/sidecar.env 中的 HOST、PORT、UNO 和 SIDECAR 配置。
若本机限制执行脚本，可设置进程环境变量后直接启动（下面为无硬件预览）：

```powershell
$env:HOST = '127.0.0.1'
$env:PORT = '5000'
$env:UNO_SERIAL_ENABLED = '0'
$env:SIDECAR_URL = ''
$env:SIDECAR_TOKEN = ''
uv run --with-requirements backend/requirements.txt python backend/app.py
```

## 已有项目更新

先 git status 检查并保存同学自己的改动，不强制覆盖。工作区干净后：

```powershell
git fetch origin
git switch main
git pull --ff-only origin main
cd frontend
npm ci
npm run build
cd ..
.\backend\scripts\start_backend.ps1
```

更新前停止旧后端，保留 local/sidecar.env，不重复覆盖。

## 接入硬件

1. 本地配置将 UNO_SERIAL_ENABLED 改为 1，UNO_PORT 填同学电脑新板实际 COM 号，波特率 115200。不要照搬 COM9；UNO_DEVICE_ID 可保持 uno-soil-rain。
2. 关闭 Arduino 串口监视器和旧独立采集进程，只运行一个后端读取串口。打开串口可能使新板复位。旧板 D0/D1 接键盘，不作为遥测 USB 接口。
3. 关闭演练模式，检查真实读数来源、新鲜度，再现场核对指令与实物变化。指令投递不等于执行确认。
4. 香橙派可选：填写 SIDECAR_URL 和与板端一致的 SIDECAR_TOKEN。板端地址曾为 192.168.137.100，迁移需重新确认网络；密钥私下交接，不入 Git。运行 uv run python backend/scripts/check_sidecar.py 只读检查。
5. 摄像头、模型和授权图库按各自部署说明配置。前端构建成功不表示视觉环境已就绪。现场验证香橙派断开和恢复时电脑主流程仍可工作。

不要复制 .venv、node_modules、个人绝对路径、运行数据库和缓存；按源码与锁文件重建环境。实机验收仍需同学完成。
