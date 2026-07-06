# Backend Prototype

Flask + SQLite backend for the first smart-home integration test branch.

This version does not require real hardware. It seeds an Orange Pi AIpro 20T hardware profile from official public specifications and provides mock-friendly APIs for frontend, hardware, YOLO, and face-recognition integration.

## Run

```powershell
cd D:\大二下\01_课程\short_term_program\backend
python -m pip install -r requirements.txt
python app.py
```

Default server:

```text
http://127.0.0.1:5000
```

## Simulate Orange Pi Uploads

Open another terminal:

```powershell
cd D:\大二下\01_课程\short_term_program\backend
python scripts\simulate_orange_pi.py
```

## Main APIs

```text
GET  /api/health
GET  /api/hardware/profile
GET  /api/status
POST /api/sensor/update
POST /api/device/control
GET  /api/device/commands
POST /api/device/commands/<id>/ack
GET  /api/history
POST /api/yolo/detect
GET  /api/yolo/latest
GET  /api/yolo/history
POST /api/face/access
GET  /api/face/history
```

## Example Sensor Update

```json
{
  "temperature": 28.5,
  "door_open": false,
  "window_open": true,
  "light_level": 70,
  "fan_on": false,
  "lock_open": false
}
```
