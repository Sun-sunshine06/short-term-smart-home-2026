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

If the backend computer changes network, replace `10.200.77.182` with the current computer IPv4 address from `ipconfig`.

The current tested Orange Pi copy is:

```text
/home/openEuler/smart_home_edge/orange_pi_client.py
```

## Current Behavior

- Registers the Orange Pi node through `POST /api/edge/register`.
- Sends node heartbeat/system metrics to `POST /api/edge/heartbeat`.
- Sends mock sensor/status data to `POST /api/sensor/update`.
- Polls pending backend commands from `GET /api/device/commands`.
- Acknowledges consumed commands through `POST /api/device/commands/<id>/ack`.
- Leaves actual GPIO/PWM execution as a small function to fill after pin mapping is confirmed.
- Camera/image validation: put the test image on Orange Pi, then run `--upload-image`. The backend saves the image and passes its `image_path` to YOLO.

## Upload A Test Image For YOLO

Copy a test image to Orange Pi, for example:

```text
/home/openEuler/smart_home_edge/test_images/demo.jpg
```

Then run:

```bash
python3 ~/smart_home_edge/orange_pi_client.py \
  --base-url http://<BACKEND_IP>:5000 \
  --node-id orange-pi-aipro-20t \
  --upload-image ~/smart_home_edge/test_images/demo.jpg
```

This uploads the local Orange Pi image to `POST /api/camera/upload`. The backend saves it and immediately creates a YOLO detection record.

The backend stores edge-node status in:

```text
GET /api/edge/nodes
GET /api/edge/heartbeats
```

## Restart After Power Off

1. Start the Flask backend on the computer.
2. Check the computer IPv4 address.
3. Boot Orange Pi and connect it to the same network.
4. Test from Orange Pi:

```bash
curl http://<BACKEND_IP>:5000/api/health
```

5. Start the edge client:

```bash
python3 ~/smart_home_edge/orange_pi_client.py --base-url http://<BACKEND_IP>:5000 --interval 2
```

More detailed steps are in `docs/notes/orange-pi-integration-runbook.md`.
