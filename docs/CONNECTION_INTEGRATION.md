# connection 分支合并预演

本分支基于 `codex/orange-pi-sidecar`，先复制当前本地未提交内容作为独立快照，再引入 `connection` 的 backend 改动及状态修复。原工作目录没有切换、暂存或覆盖。

已保留 `/next/` 前端入口、旧页面 hash 导航、SidecarForwarder 启动与传感器转发。只处理 backend 的改动；未引入根目录重复的 UNO 固件及旧方案文档，当前固件仍在 hardware/arduino/usb_asr_d3_v1。

## 状态语义

USB 命令成功仅说明新板已发送，不代表旧板执行成功。实际设备状态保持不变；预计值位于 `/api/status` 的 `expected_states`，标记 `confirmed: false`。旧网页展示“预计、未确认”。门的预计值从持久化投递时间计算，四秒后预计关闭，刷新和后端重启不影响结果。

## 统一串口归属

`UnoSerialBridge` 独占新板 USB 串口，同时读取控制响应和传感器遥测。完整行分帧与 512 字节上限防止串口超时或异常长行影响解析。断线后自动重连，不重放控制命令。

遥测使用独立后台工作线程，待处理队列只保留最新一条，繁忙时合并旧样本。工作线程复用 HTTP 传感器接口的入库与旁路转发函数，不在串口读取线程中执行数据库或网络操作。新板雨滴/土壤样本不会把旧板灯光清零或把旧板标为在线。队列合并、入库成功和异常计数可从 `/api/hardware/uno` 的 `telemetry` 字段检查。

`collect_uno.py` 现在只是后端状态监视器，不导入串口库、不打开端口、不重复上传样本。旧版本采集进程必须先停止。启动单个后端进程，由它独占端口；不要同时启动多个后端服务或 Arduino 串口监视器。

配置 `local/sidecar.env` 中的 `UNO_PORT`、`UNO_BAUD`、`UNO_DEVICE_ID`、`UNO_SERIAL_ENABLED`；稳定设备 ID 默认 `uno-soil-rain`，应与香橙派配置匹配。无硬件开发时设置 `UNO_SERIAL_ENABLED=0`。

新 frontend 的设备交互仍按本地原实现保留，不能把本次旧 dashboard 的状态修复视作新前端硬件接入已经完成。

自动测试覆盖混合串口数据、分段读取、慢存储、队列上限、存储失败恢复、断线重连及旁路转发。真机 USB 与板端联调仍需在接有硬件的电脑验收。
