# 硬件组 Arduino 参考源码

2026-11-17 收录用户提供的两份代码，按附件原样保存，未修改程序逻辑。两块板均为 Arduino UNO R3（用户确认）。尚未编译、烧录或确认这些文件与板上当前固件完全一致。

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
