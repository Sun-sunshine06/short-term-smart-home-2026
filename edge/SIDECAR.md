# 电脑采集与香橙派旁路分析

当前硬件：USB_ASR_D3_V1，新扩展板 USB 115200，ASR D3 9600；板间 V2 单向协议。用户转述已完成改线/烧录并确认控制正常，详见 `hardware/arduino/README.md`。旧板不向电脑提供实际执行确认或温湿度，不能凭新板日志补造这些数据。

## 链路与边界

`新板 USB → 电脑 collect_uno.py → Flask 入库 → 有界后台队列 → 香橙派 HTTP / SQLite / 分析`

电脑提交原有业务事务后再尝试入队；采集、浏览器请求均不等待香橙派网络。队列最多 64 个设备，每个设备合并为最新一条；满时淘汰最旧项并计数。另保留最多 64 个设备的最新快照用于重连恢复。每个 HTTP 请求超时 1 秒；失败样本结束本次发送，后台连接检查按 2/4/8 秒退避。重连后最多重发一次各设备 180 秒内的最新快照，并处理后续新数据；每条快照的恢复重发次数有上限，不反复补发历史。副本是尽力交付，不能保证零丢失。旁路服务不访问控制接口，不触发开门。电脑停止发送时，香橙派只能检测中断并保存已有记录。

电脑通过同一个后台线程每 2 秒读取 `/v1/status`，与样本入口 `/v1/samples` 分开；不要求板端回调电脑。超过 8 秒未读到有效状态即显示节点离线。页面分别显示节点连接与各设备数据有效期；离线/过期时不展示为当前正常结论。

## 数据协议

`POST /v1/samples`，JSON，最多 8192 字节；`Authorization: Bearer <本地共享密钥>`。

```json
{
  "version": 1,
  "device_id": "uno-soil-rain",
  "boot_id": "电脑后端每次启动生成的 UUID",
  "seq": 1,
  "pc_received_at": "2026-11-17T12:00:00+00:00",
  "values": {"soil_raw": 500, "soil_percent": 63, "soil_state": "OK", "rain_raw": 900, "rain_percent": 0, "rain_state": "DRY"},
  "quality": {"soil_raw": "valid"}
}
```

`device_id` 是人为配置的稳定身份，不能使用 COM 号；后端收到的原始 payload 必须带该字段，否则跳过旁路并计入 skipped。时间是电脑后端接收时间，非 Arduino 采样时间。电脑和板端时钟需一致；拒绝超过 180 秒的旧样本及未来超过 30 秒的时间。结果有效期不因网络迟到而延长。重复/乱序序号不重复记账，新启动标识必须有更新的接收时间；水位持久化，板端重启仍能去重。

仅转发温度（将来接入）、雨滴/土壤原始值、相对百分比、原始状态和质量标记。土壤 `OK` 只表示固件未报告干燥，不转换为 WET；雨滴 DRY/WET 原样保存。没有校准物理含水率。命令日志、图像、人脸图库、视频均不转发。无温度字段时不编造温度或报警。

检查包括：必需字段缺失、unknown/invalid 标记、类型、配置范围和超时。支持状态变化、连续 DRY 达配置时长、数据中断和恢复。未知/无效/中断会打断连续 DRY 计时。每个事件有稳定事件 ID、来源序号，记录规则版本、原因、分析时间与有效期。重复事件不重复写入。

`GET /v1/status`：节点心跳、当前各设备状态、采集间隔、累计样本数/变化次数、记录条数和存储错误。
`GET /v1/history`：最近 50 条结果（含超时事件）。两者也需要密钥。

SQLite 最多 10000 条、保留 7 天，数据库页数硬限约 32 MiB（默认 4 KiB 页）；回滚日志也会占用少量空间。旧记录删除后空闲页复用，文件不会每次缩小。设备配置最多 32 个。存储满或只读时返回 503，电脑丢弃副本，主流程继续。无数据时板端仍维护保留期并记录一次超时事件。

## 启动

仓库根目录下，电脑使用 uv 管理运行环境。将 `edge/sidecar.example.json` 复制为本地配置并核实稳定设备 ID、原始 ADC 范围、超时及干燥阈值。示例只有雨滴与土壤；未接入温度时不要求温度。

香橙派仅依赖 Python 标准库（Python 3.9+）；复制 `sidecar_service.py` 和配置文件到专用目录。先在本地安全生成共享随机密钥，分别设置两端 `SIDECAR_TOKEN`，不要提交密钥。

```bash
# 香橙派；已有系统 Python 即可，无需安装模型/AI 框架
export SIDECAR_TOKEN='<双方相同的随机密钥，至少16字符>'
python3 sidecar_service.py --host 192.168.137.100 --port 8787 --config sidecar.json --db local/sidecar.db
```

```powershell
# 电脑，仓库根目录
$env:SIDECAR_URL = 'http://192.168.137.100:8787'
$env:SIDECAR_TOKEN = '<双方相同的随机密钥>'
uv run --with-requirements backend/requirements.txt python backend/app.py
```

```powershell
# 另一个终端。先关闭占用新板串口的串口监视器；打开串口可能重启新板。
# 将 COM9 换成确认过的新扩展板端口。仅读取，不发送任何控制命令。
uv run --with-requirements backend/requirements-hardware.txt python backend/scripts/collect_uno.py --port COM9 --device-id uno-soil-rain
```

采集器独立读取线程外发送 HTTP，队列只保留最新一条；后端不通时也不会无限堆积。每 5 秒打印解析、合并、发送和失败计数。串口断开会退出，需要重新确认端口后启动。

本次用户提供的历史启动流程使用香橙派 `192.168.137.100`、电脑有线 `192.168.137.101/24`、用户 `HwHiAiUser`。地址配置是本机联调信息，不是通用硬编码默认值。Windows ActiveStore 配置重启后可能失效；不设置有线默认网关。旧文档的 `192.168.1.101` 不应盲用。不要启动旧的 `orange_pi_client.py --camera` 流程。

## 验证

```powershell
uv run --with-requirements backend/requirements.txt python -m unittest discover -s tests -v
```

覆盖规则、缺失/未知/无效值、重复/乱序/重启、超时与恢复、记录上限与清理、存储失败、真实 HTTP 认证/接收/重连、固件遥测格式、离线/慢响应/错误响应时电脑入库成功，以及同条件启用/禁用旁路的数据请求耗时比较。

2026-11-17 本机 16 项测试通过。禁用、慢响应、错误响应三组各 10 次请求，观测最大耗时均约 16 ms；这是当前 Windows 环境中的一次运行记录，不是硬实时保证。新增页面脚本通过 Node 语法检查，浏览器已核对“节点在线 / 尚未收到数据”的独立状态显示。

本地自动化不等同于实物验收：真实 USB 采集间隔、ESP32-CAM 预览性能、现场控制并发仍需设备接入后测量；没有实现的正式硬件控制链路不能声称通过了隔离验收。

## 本次实机部署（2026-11-17）

- 已通过网线 SSH 登录 `orangepiaipro`，Ubuntu 22.04.3 / aarch64 / Python 3.10.12。
- 板端时钟原为 2026-07-09，已与电脑当前时间对齐。断电后应再次检查时钟，避免旧时间导致协议拒收。
- 服务目录 `~/smart_home_sidecar/`，代码按版本保存在 `releases/`，数据库在 `data/sidecar.db`。
- 用户级 `smart-home-sidecar.service` 已启用；已启用用户 linger，使退出 SSH 后继续运行并随系统启动。
- 在香橙派运行 `systemctl --user status smart-home-sidecar.service`、`journalctl --user -u smart-home-sidecar.service -n 50` 查看状态。停止/启动分别使用 `systemctl --user stop/start smart-home-sidecar.service`。
- 电脑的共享密钥保存在未纳入 Git 的 `local/sidecar.env`，板端保存在 `~/.config/smart-home-sidecar.env`（权限 600）；未提交登录密码或共享密钥。
- 电脑可运行 `backend/scripts/start_backend.ps1` 自动加载本地旁路配置并通过 uv 启动后端。
- 已验证真实 HTTP 收发与板端 SQLite 历史；停止板端服务时，电脑 10/10 次传感器请求成功，最大约 29 ms；恢复服务后最新数据重新送达。测试设备 `integration-test` 的记录已清理，生产设备保持“尚未收到数据”。
- 本机尚未检测到 UNO 串口，因此没有运行真实串口采集或发送控制命令；视频性能仍待现场接入验证。
