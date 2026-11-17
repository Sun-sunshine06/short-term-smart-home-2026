"""Best-effort telemetry copies. No network I/O on the sensor request thread."""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.request
import uuid
from collections import OrderedDict

FIELDS = ("temperature", "soil_raw", "soil_percent", "soil_state", "rain_raw", "rain_percent", "rain_state")


class SidecarForwarder:
    def __init__(self, url="", token="", capacity=64, timeout=1.0):
        self.url = url.rstrip("/")
        self.token = token
        self.capacity = capacity
        self.timeout = timeout
        self.boot_id = str(uuid.uuid4())
        self.sequence = 0
        self.pending = OrderedDict()
        self.latest = OrderedDict()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.dropped = self.errors = self.sent = self.skipped = 0
        self.last_contact = 0.0
        self.remote = None
        self.last_error = None
        self.next_attempt = 0.0
        self.failures = 0

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("SIDECAR_URL", ""), os.environ.get("SIDECAR_TOKEN", ""))

    def start(self):
        if self.url and self.thread is None:
            self.thread = threading.Thread(target=self._run, name="sidecar-forwarder", daemon=True)
            self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=self.timeout * 2 + 1)

    def submit(self, payload, received_at):
        if not self.url:
            return
        # A stable ID must be assigned by the PC collector, never inferred from COM ports.
        device = payload.get("device_id")
        if not isinstance(device, str) or not 1 <= len(device) <= 80:
            with self.lock:
                self.skipped += 1
            return
        values = {key: payload[key] for key in FIELDS if key in payload}
        # Bound size before enqueueing; no faces, images, commands, or arbitrary raw payload.
        if any(not isinstance(v, (str, int, float, bool, type(None))) or
               (isinstance(v, str) and len(v) > 80) or
               (isinstance(v, float) and not math.isfinite(v)) for v in values.values()):
            with self.lock:
                self.skipped += 1
            return
        flags = payload.get("quality", {})
        if not isinstance(flags, dict):
            flags = {}
        quality = {key: flags[key] for key in FIELDS if flags.get(key) in
                   ("valid", "invalid", "unknown")}
        with self.lock:
            self.sequence += 1
            sample = {"version": 1, "device_id": device, "boot_id": self.boot_id,
                      "seq": self.sequence, "pc_received_at": received_at,
                      "values": values, "quality": quality}
            self.latest.pop(device, None)
            if len(self.latest) >= self.capacity:
                self.latest.popitem(last=False)
            self.latest[device] = (time.monotonic(), sample, False)
            if device in self.pending:
                self.pending.pop(device)
                self.dropped += 1
            elif len(self.pending) >= self.capacity:
                self.pending.popitem(last=False)
                self.dropped += 1
            self.pending[device] = sample

    def snapshot(self):
        with self.lock:
            return {"enabled": bool(self.url), "online": bool(self.last_contact and
                    time.time() - self.last_contact < 8), "last_contact": self.last_contact or None,
                    "pending": len(self.pending), "capacity": self.capacity,
                    "dropped": self.dropped, "sent": self.sent, "errors": self.errors,
                    "skipped": self.skipped, "last_error": self.last_error, "analysis": self.remote}

    def _request(self, path, sample=None):
        body = None if sample is None else json.dumps(sample, allow_nan=False).encode()
        request = urllib.request.Request(self.url + path, data=body,
                  headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token})
        # Local direct connections must not be sent through a system HTTP proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=self.timeout) as response:
            raw = response.read(131073)
            if len(raw) > 131072:
                raise ValueError("oversized edge response")
            result = json.loads(raw)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise ValueError("invalid edge response")
        return result

    def _run(self):
        poll_at = 0.0
        while not self.stop_event.wait(0.1):
            if time.monotonic() < self.next_attempt:
                continue
            sample = None
            with self.lock:
                if self.pending:
                    _, sample = self.pending.popitem(last=False)
            try:
                if sample:
                    self._request("/v1/samples", sample)
                    with self.lock:
                        self.sent += 1
                if time.monotonic() >= poll_at:
                    remote = self._request("/v1/status")
                    if not isinstance(remote.get("devices"), list) or "node_id" not in remote:
                        raise ValueError("invalid edge status")
                    with self.lock:
                        recovering = self.failures > 0
                        self.remote = remote
                        self.last_contact = time.time()
                        if recovering:
                            # One latest snapshot per device on reconnection, never old commands.
                            for device, (queued_at, latest, replayed) in self.latest.items():
                                if not replayed and device not in self.pending and time.monotonic() - queued_at < 180:
                                    if len(self.pending) >= self.capacity:
                                        self.pending.popitem(last=False)
                                        self.dropped += 1
                                    self.pending[device] = latest
                                    self.latest[device] = (queued_at, latest, True)
                    poll_at = time.monotonic() + 2
                with self.lock:
                    self.failures = 0
                    self.last_error = None
            except Exception as exc:
                # Samples are best-effort, never replayed indefinitely. Keep newer queued values.
                with self.lock:
                    self.errors += 1
                    self.dropped += int(sample is not None)
                    self.failures += 1
                    self.last_error = type(exc).__name__
                    self.next_attempt = time.monotonic() + min(8, 2 ** min(self.failures, 3))
