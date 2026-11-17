# connection 分支合并预演

本分支基于 `codex/orange-pi-sidecar`，先复制当前本地未提交内容作为独立快照，再引入 `connection` 的 backend 改动及状态修复。原工作目录没有切换、暂存或覆盖。

已保留 `/next/` 前端入口、旧页面 hash 导航、SidecarForwarder 启动与传感器转发。只处理 backend 的改动；未引入根目录重复的 UNO 固件及旧方案文档，当前固件仍在 hardware/arduino/usb_asr_d3_v1。

## 状态语义

USB 命令成功仅说明新板已发送，不代表旧板执行成功。实际设备状态保持不变；预计值位于 `/api/status` 的 `expected_states`，标记 `confirmed: false`。旧网页展示“预计、未确认”。门的预计值从持久化投递时间计算，四秒后预计关闭，刷新和后端重启不影响结果。

## 正式联调前必须解决的串口归属

现有 `backend/scripts/collect_uno.py` 与新增 `UnoSerialBridge` 都会打开新板 USB 串口，不能同时启动并争用同一个端口。

- 保持现有采集模式时，启动后端前设置 `UNO_SERIAL_ENABLED=0`，继续运行 collect_uno；此时 USB 控制不可用。
- 验证 USB 控制时，停止 collect_uno，设置 UNO_PORT 为实际新板端口并启用 UNO_SERIAL_ENABLED；此时桥接器尚未把雨滴、土壤遥测转发给旁路分析。
- 要同时使用两者，应让 UnoSerialBridge 独占端口，将遥测行送入现有解析、存储和旁路转发流程，并采用有界异步队列，避免网络等待阻塞串口读取。该整合不属于本次两个状态问题的修复，预演版本尚未完成它。

新 frontend 的设备交互仍按本地原实现保留，不能把本次旧 dashboard 的状态修复视作新前端硬件接入已经完成。

本分支用于审查，不应在完成串口整合及真机联调前宣称整套硬件已可同时运行。
