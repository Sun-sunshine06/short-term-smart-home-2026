"""Share the newest USB JPEG frame across viewers and sample it for local inference."""
import json
from threading import Condition, Lock, Thread
from time import monotonic, sleep

import serial
from flask import Response, jsonify, request

from .face_adapter import verify_camera_frame
from .yolo_adapter import _confidence_threshold, _load_yolo_model


class LiveCamera:
    def __init__(self, port):
        self.port = port
        self.changed = Condition()
        self.frame = b""
        self.received = self.inferred = 0
        self.frame_time = self.view_until = self.infer_until = 0.0
        self.result_time = 0.0
        self.boxes = []
        self.camera_error = self.model_error = ""
        self.started = False

    def capture(self):
        while True:
            with self.changed:
                self.changed.wait_for(lambda: monotonic() < self.view_until)
            try:
                with serial.Serial(None, 921_600, timeout=1, write_timeout=1) as link:
                    link.port = self.port
                    link.dtr = link.rts = False
                    link.open()
                    # Boot in application mode and synchronize with its ready marker.
                    link.rts = True
                    sleep(.15)
                    link.rts = False
                    deadline = monotonic() + 8
                    while monotonic() < deadline:
                        if b"HTTP_READY" in link.read_until(size=256):
                            break
                    link.reset_input_buffer()
                    while monotonic() < self.view_until:
                        link.write(b"CAPTURE" + bytes([10]))
                        header = link.read_until(size=96).strip().split()
                        if len(header) != 2 or header[0] != b"JPEG":
                            raise ValueError("摄像头没有返回 JPEG 帧头")
                        size = int(header[1])
                        if not 100 <= size <= 512_000:
                            raise ValueError("摄像头帧长度无效")
                        data = link.read(size)
                        if len(data) != size or data[:2] != bytes.fromhex("ffd8") or data[-2:] != bytes.fromhex("ffd9"):
                            raise ValueError("JPEG 不完整")
                        with self.changed:
                            self.frame = data
                            self.frame_time = monotonic()
                            self.received += 1
                            self.camera_error = ""
                            self.changed.notify_all()
            except Exception as exc:
                with self.changed:
                    self.camera_error = str(exc)
                sleep(1)

    def infer(self):
        processed = 0
        while True:
            with self.changed:
                self.changed.wait_for(lambda: monotonic() < self.infer_until and self.received != processed)
                processed, data, timestamp = self.received, self.frame, self.frame_time
            try:
                import cv2
                import numpy as np
                model, _, status = _load_yolo_model()
                if model is None:
                    raise RuntimeError("YOLO 模型不可用 (" + status + ")")
                image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                result = model.predict(image, conf=_confidence_threshold(), verbose=False)[0]
                boxes = [[*b.xyxy[0].tolist(), result.names[int(b.cls.item())], round(b.conf.item(), 2)]
                         for b in result.boxes]
                with self.changed:
                    self.boxes = boxes
                    self.result_time = timestamp
                    self.inferred += 1
                    self.model_error = ""
            except Exception as exc:
                with self.changed:
                    self.model_error = str(exc)
                sleep(1)

    def next_frame(self):
        after = request.args.get("after", 0, type=int)
        detect = request.args.get("yolo") == "1"
        with self.changed:
            self.view_until = monotonic() + 5
            if detect:
                self.infer_until = monotonic() + 1
            if not self.started:
                Thread(target=self.capture, daemon=True).start()
                Thread(target=self.infer, daemon=True).start()
                self.started = True
            self.changed.notify_all()
            if not self.changed.wait_for(lambda: self.received != after and monotonic() - self.frame_time < 1, 2):
                return jsonify(error=self.camera_error or "等待摄像头画面"), 503
            headers = {
                "Cache-Control": "no-store",
                "X-Frame": str(self.received),
                "X-Inferences": str(self.inferred),
                "X-Model-Error": "1" if self.model_error and detect else "0",
                "X-Boxes": json.dumps(self.boxes if detect and self.frame_time - self.result_time < .5 else []),
            }
            return Response(self.frame, mimetype="image/jpeg", headers=headers)


def register_live_camera(app, port, authorized_references, open_for_live_face):
    camera = LiveCamera(port) if port else None
    app.add_url_rule("/api/live/camera", "live_camera_status", lambda: jsonify(enabled=bool(camera)))
    if camera:
        app.add_url_rule("/api/live/frame", "live_camera_frame", camera.next_frame)

    verify_lock = Lock()

    attempted = {}
    empty_since = None
    last_sample = 0.0

    @app.route("/api/live/face", methods=["GET", "POST"])
    def live_face():
        nonlocal empty_since, last_sample
        actuate = request.method == "POST"
        if actuate and not request.is_json:
            return jsonify(error="JSON request required"), 415
        if camera is None:
            return jsonify(state="offline")
        if not verify_lock.acquire(blocking=False):
            return jsonify(state="busy")
        try:
            with camera.changed:
                if not camera.frame or monotonic() - camera.frame_time > 1:
                    return jsonify(state="offline")
                frame = camera.frame
                sampled_at = camera.frame_time
            records = authorized_references()
            if not records:
                return jsonify(state="empty_gallery")
            names = {identity: name for identity, name, _ in records}
            result = verify_camera_frame(frame, [(identity, path) for identity, _, path in records])
            if result.get("identity"):
                result["name"] = names[result["identity"]]
            if actuate:
                if monotonic() - sampled_at > 3:
                    return jsonify(state="busy")
                if sampled_at - last_sample > 4:
                    empty_since = None
                last_sample = sampled_at
                if result["state"] == "no_face":
                    if empty_since is None:
                        empty_since = sampled_at
                    elif sampled_at - empty_since >= 2:
                        attempted.clear()
                else:
                    empty_since = None
                if result["state"] == "matched":
                    identity = result["identity"]
                    if identity not in attempted:
                        # Reserve before sending: a timeout can follow a physical delivery.
                        if records != authorized_references():
                            return jsonify(state="busy")
                        attempted[identity] = {"status": "unconfirmed"}
                        attempted[identity] = open_for_live_face(result)
                    result["door"] = attempted[identity]
            return jsonify(result)
        except Exception:
            app.logger.exception("Live face verification failed")
            return jsonify(state="unavailable"), 503
        finally:
            verify_lock.release()
