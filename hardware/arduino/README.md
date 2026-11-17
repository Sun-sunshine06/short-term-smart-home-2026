# 硬件组 Arduino 源码与当前版本

## 当前版本：USB_ASR_D3_V1（2026-11-17）

最新入口是 [usb_asr_d3_v1](usb_asr_d3_v1/README_接线烧录与测试.md)，来自用户提供的 `智能家居_双UNO_USB控制_ASR改D3_20261117.zip`，完整保留源码、头文件、HEX、校验清单和包内验证记录。导入时全部 25 个文件通过 SHA-256 校验。包内编译结果属于随包记录，不代表本次重新编译。

用户转述现场同学已完成改线和两板烧录，原功能正常，开关灯、风扇能响应命令。这是现场反馈；本次软件工作没有再次烧录或独立验证实物动作。

| 项目 | 当前约定 |
| --- | --- |
| 旧主控板工程 | `usb_asr_d3_v1/OldBoard_Main/OldBoard_Main.ino`，保留同目录 `HomeLink.h` |
| 新扩展板工程 | `usb_asr_d3_v1/NewBoard_Expansion/NewBoard_Expansion.ino`，保留全部三个头文件 |
| ASR | 新板 D3 / INT1，9600 8N1；新板 D0/D1 留给 USB 硬件串口 |
| USB | 新板 115200 8N1，接电脑；香橙派通过网络接收副本 |
| 板间通信 | 新板 D10 → 旧板 D5，V2 同步帧、序号与 CRC，单向、无执行回执 |
| 遥测 | 雨滴 DRY/WET，土壤 DRY/OK；原始值和相对百分比；超声波距离或 NO_ECHO |
| 能力边界 | 无旧板温湿度或执行状态回传；灯亮度固定 35；QUEUED/SENT_NO_ACK 不是执行成功 |

电脑采集与香橙派旁路部署见 [旁路运行说明](../../edge/SIDECAR.md)。本轮采集程序仅读取遥测，不发送控制命令。网页执行控制和人脸开门的 USB 桥接尚未由本轮实现。

## 历史参考版本（不再作为当前接入依据）

下列两份是早期参考代码，按附件原样保存。D0 ASR、9600 USB、脉冲计数等描述只适用于这个历史版本，不能套用到当前 USB_ASR_D3_V1。

## 工程入口

| 工程 | 职责 |
| --- | --- |
| [old_board_controller](old_board_controller/old_board_controller.ino) | 旧板：DHT11 温湿度、风扇、光控灯环、密码键盘、舵机、蜂鸣器、OLED；D5 接收脉冲命令 |
| [new_board_bridge](new_board_bridge/new_board_bridge.ino) | 新板：D0 接收 ASRPRO 串口命令，D10 向旧板发脉冲；采集雨滴、土壤、触摸和超声波；串口输出 9600 baud |

每个 `.ino` 与所在文件夹同名，可分别在 Arduino IDE 中打开。两个工程烧录到不同板子，不能合并成同一个 sketch。

旧板引用 Arduino 核心、SPI、U8g2、DHT、Adafruit NeoPixel 和 Servo。具体库版本未由硬件组提供，尚未验证兼容版本。新板只显式引用 Arduino 核心。原始代码保留演示用硬编码密码；这不是可用于正式门禁的安全配置。

## 使用前先检查

- 本轮设备信息采集不要求上传固件。不要为了读取数据覆盖板上现有程序。
- 旧板 D0/D1 被键盘使用且未启用 Serial；新板 D0/RX 已连接 ASRPRO。不能未经接线核实直接通过 USB 发送控制命令。
- 打开新板串口可能触发 UNO 重启；先由现场人员确认可以接受设备重启和输出变化。
- 现有脉冲协议有阻塞等待且没有旧板执行回执；新板未发送旧板定义的 ID 8–12。不要把发送日志当作执行成功。
- 引脚与行为应对照实际接线核实，不能以参考源码代替实物检查。

详细分析见[架构与两板代码核对方案](../../docs/proposals/pc-camera-hardware-gateway-2026-11-17.md)。设备采集步骤见 [Issue #4](https://github.com/Sun-sunshine06/short-term-smart-home-2026/issues/4)。
