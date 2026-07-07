# Orange Pi Edge Client

This directory contains the first Orange Pi AIpro 20T edge-side client.

It uses only Python standard library modules, so it can run on openEuler without installing extra packages.

## Run On Orange Pi

```bash
python3 orange_pi_client.py --base-url http://10.200.77.182:5000 --interval 2
```

For a short test:

```bash
python3 orange_pi_client.py --base-url http://10.200.77.182:5000 --count 3
```

## Current Behavior

- Sends mock sensor/status data to `POST /api/sensor/update`.
- Polls pending backend commands from `GET /api/device/commands`.
- Acknowledges consumed commands through `POST /api/device/commands/<id>/ack`.
- Leaves actual GPIO/PWM execution as a small function to fill after pin mapping is confirmed.
