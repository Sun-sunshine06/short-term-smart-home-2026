# Orange Pi Edge Client

This directory contains the Orange Pi AIpro edge-side client.

The client uses only Python standard library modules, so it can run on openEuler, Ubuntu, or similar Linux systems without installing extra packages.

## Placeholders

```text
<BACKEND_HOST>  Backend computer IPv4 address reachable from Orange Pi
<BACKEND_PORT>  Backend port, default 5000
<EDGE_HOME>     Orange Pi working directory, default ~/smart_home_edge
<NODE_ID>       Stable node id, for example orange-pi-aipro-20t
<TEST_IMAGE>    Test image path on Orange Pi
```

## Run On Orange Pi

From the directory containing `orange_pi_client.py`:

```bash
python3 orange_pi_client.py \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --interval 2
```

Short test:

```bash
python3 orange_pi_client.py \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --count 3
```

If the backend computer changes network, check its current IPv4 address again and replace `<BACKEND_HOST>`.

Recommended Orange Pi copy:

```text
<EDGE_HOME>/orange_pi_client.py
```

## Current Behavior

- Registers the Orange Pi node through `POST /api/edge/register`.
- Sends node heartbeat/system metrics to `POST /api/edge/heartbeat`.
- Sends mock sensor/status data to `POST /api/sensor/update`.
- Polls pending backend commands from `GET /api/device/commands`.
- Acknowledges consumed commands through `POST /api/device/commands/<id>/ack`.
- Uploads a local image with `--upload-image`; the backend saves the image, runs YOLO, and runs face verification by default.
- Captures low-frequency live camera frames with `--camera` and uploads each frame to the same vision flow.
- Leaves actual GPIO/PWM execution as a small function to fill after pin mapping is confirmed.

## Upload A Test Image For YOLO

Put a test image on Orange Pi, for example:

```text
<EDGE_HOME>/test_images/demo.jpg
```

Then run:

```bash
python3 <EDGE_HOME>/orange_pi_client.py \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --upload-image <EDGE_HOME>/test_images/demo.jpg
```

This uploads the local Orange Pi image to `POST /api/camera/upload`. The backend saves it and immediately creates a YOLO detection record plus a face access record. Face verification can be disabled on the backend with `CAMERA_UPLOAD_FACE_VERIFY=0`.

## Low-Frequency Live Camera Upload

For acceptance, use the camera mode instead of full video streaming first:

```bash
python3 <EDGE_HOME>/orange_pi_client.py \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --camera \
  --camera-device 0 \
  --camera-interval 1 \
  --camera-count 30
```

This captures one JPEG frame every second, uploads it to `POST /api/camera/upload`, and keeps heartbeat, mock sensor state, and command polling active.

The default capture path is:

```text
<EDGE_HOME>/captures/
```

Capture priority:

1. Python OpenCV `cv2.VideoCapture`.
2. Auto-detected system tools: `libcamera-still`, `fswebcam`, or `ffmpeg`.
3. Custom command through `--camera-command`.

Examples:

```bash
python3 <EDGE_HOME>/orange_pi_client.py \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --camera \
  --camera-command 'fswebcam -d "{device}" -r {width}x{height} --no-banner "{output}"'
```

```bash
python3 <EDGE_HOME>/orange_pi_client.py \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --camera \
  --camera-command 'ffmpeg -y -f v4l2 -video_size {width}x{height} -i "{device}" -frames:v 1 "{output}" -loglevel error'
```

If the camera is not `/dev/video0`, replace `--camera-device 0` with the correct index or path, for example `--camera-device /dev/video2`.

## Useful Backend APIs

```text
GET /api/edge/nodes
GET /api/edge/heartbeats
GET /api/yolo/latest
GET /api/yolo/history
GET /api/face/latest
GET /api/face/history
```

## Restart After Power Off

1. Start the Flask backend on the backend computer.
2. Check the backend computer IPv4 address and set `<BACKEND_HOST>`.
3. Boot Orange Pi and connect it to the same reachable network.
4. Test from Orange Pi:

```bash
curl http://<BACKEND_HOST>:<BACKEND_PORT>/api/health
```

5. Start the edge client:

```bash
python3 <EDGE_HOME>/orange_pi_client.py \
  --base-url http://<BACKEND_HOST>:<BACKEND_PORT> \
  --node-id <NODE_ID> \
  --interval 2
```

More detailed steps are in `docs/notes/orange-pi-integration-runbook.md`.
