# Orange Pi AIpro 20T 联调状态与重启手册

> 更新时间：2026-07-07。本文记录当前已经跑通的链路、给小组同步用的话术，以及关机/断开网络后下一次恢复联调的步骤。

## 当前状态

已经完成：

```text
Orange Pi AIpro 20T
-> openEuler
-> Python 3.9.9
-> HTTP 上报
-> Flask 后端
-> SQLite
-> Web GUI 状态刷新
```

本次实测信息：

- Orange Pi 用户：`openEuler`
- Orange Pi 系统：`openEuler aarch64`
- Orange Pi 当前同网段 IP：`10.200.77.110`
- 后端电脑当前 IP：`10.200.77.182`
- 后端地址：`http://10.200.77.182:5000`
- Web GUI 本机地址：`http://127.0.0.1:5000/`
- Orange Pi 端脚本路径：`/home/openEuler/smart_home_edge/orange_pi_client.py`

已验证：

- Orange Pi 可以访问 `GET /api/health`。
- Orange Pi 可以调用 `POST /api/sensor/update`。
- 后端可以写入 SQLite。
- Web GUI 可以看到状态变化。
- Orange Pi 端脚本可以轮询 `GET /api/device/commands` 并 ack 命令。

当前仍是模拟输入：

- `temperature`
- `door_open`
- `window_open`
- `light_level`
- `fan_on`
- `lock_open`

这些字段现在由脚本生成。硬件组给出实际引脚/传感器方案后，只需要替换 `edge/orange_pi_client.py` 中的数据来源。

## 给小组同步的话术

可以直接发到群里：

```text
目前 Orange Pi AIpro 20T 已经开机并接入网络，软件侧链路已经跑通：

香橙派 openEuler -> Python 脚本 -> HTTP 上报 -> Flask 后端 -> SQLite -> Web GUI 展示。

我们已经实测从香橙派向后端 POST /api/sensor/update 成功，前端控制台可以看到状态变化；香橙派端也能轮询 /api/device/commands，后续可以接硬件执行。

现在还差硬件组确认真实模拟输入/执行器的接线和含义，例如门窗开关、灯光亮度、风扇、门锁/舵机分别接哪个 GPIO/PWM/I2C/ADC。确认后只需要把 orange_pi_client.py 里生成 mock 数据的部分替换成真实读取即可。
```

更短版本：

```text
香橙派到后端和前端的链路已跑通：Orange Pi -> HTTP -> Flask/SQLite -> Web GUI。现在上报的是脚本模拟数据，等硬件组确认引脚和传感器定义后，把脚本的数据源替换成真实 GPIO/传感器读取即可。
```

## 关机/断开后下次恢复步骤

### 1. 电脑端启动后端

在电脑 PowerShell 中执行：

```powershell
cd D:\大二下\01_课程\short_term_program
python backend\app.py
```

如果已经有后台服务在跑，也可以直接测试：

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

### 2. 电脑端查看当前 IP

每次换 Wi-Fi/热点后，电脑 IP 可能变化。执行：

```powershell
ipconfig
```

找到当前网络的 IPv4 地址，例如：

```text
10.200.77.182
```

后面命令里的 `<BACKEND_IP>` 就替换成这个地址。

### 3. Orange Pi 开机并接入同一网络

确认 Orange Pi 和后端电脑在同一 Wi-Fi/热点/路由器下。

在 Orange Pi 终端执行：

```bash
hostname -I
```

确认能看到同网段 IP，例如：

```text
10.200.77.110
```

### 4. Orange Pi 测试后端连通性

在 Orange Pi 终端执行：

```bash
curl http://<BACKEND_IP>:5000/api/health
```

例如：

```bash
curl http://10.200.77.182:5000/api/health
```

看到 `"ok": true` 即可继续。

### 5. Orange Pi 运行边缘端脚本

短测 3 次：

```bash
python3 ~/smart_home_edge/orange_pi_client.py --base-url http://<BACKEND_IP>:5000 --count 3
```

持续运行：

```bash
python3 ~/smart_home_edge/orange_pi_client.py --base-url http://<BACKEND_IP>:5000 --interval 2
```

运行后电脑打开：

```text
http://127.0.0.1:5000/
```

观察 Web GUI 状态是否变化。

## 如果脚本丢失

仓库中有同一份脚本：

```text
edge/orange_pi_client.py
```

可重新复制到 Orange Pi：

```bash
mkdir -p ~/smart_home_edge
```

然后把仓库里的 `edge/orange_pi_client.py` 放到：

```text
/home/openEuler/smart_home_edge/orange_pi_client.py
```

## 当前已确认接口

Orange Pi 上报状态：

```text
POST /api/sensor/update
```

Orange Pi 轮询控制命令：

```text
GET /api/device/commands
```

Orange Pi ack 命令：

```text
POST /api/device/commands/<id>/ack
```

## 硬件组需要补充的信息

后续接真实硬件时，需要确认：

- 温度/模拟量来自哪个传感器或 ADC；
- 门窗状态对应哪个 GPIO；
- 灯光亮度是否需要 PWM，范围是否为 0-100；
- 风扇是 GPIO 开关、继电器还是 PWM；
- 门锁/舵机使用哪个 GPIO/PWM；
- 高低电平含义：`1` 表示打开还是关闭；
- 是否需要上拉/下拉、电平转换、外接驱动模块；
- 是否需要在 Orange Pi 上安装额外 GPIO/PWM/I2C 库。

确认后修改位置：

```text
edge/orange_pi_client.py
```

重点替换：

```python
build_mock_payload(...)
handle_command(...)
```

