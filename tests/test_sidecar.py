import json
import gc
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from backend.sidecar import SidecarForwarder
from edge.sidecar_service import Store

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"uno": {"required": ["soil_state", "rain_state"], "timeout_seconds": 15,
                   "dry_seconds": 10, "ranges": {"temperature": [-40, 85]}}}


def sample(seq=1, now=1000, **values):
    return {"version": 1, "device_id": "uno", "boot_id": "boot-1", "seq": seq,
            "pc_received_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "values": values or {"soil_state": "DRY", "rain_state": "WET"}, "quality": {}}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "edge.db")
        self.store = Store(self.path, CONFIG, max_rows=5, retention=100)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_quality_and_ranges(self):
        result = self.store.accept(sample(temperature=100, soil_state="DRY"), 1000)["result"]
        self.assertEqual(result["quality"], "issues")
        self.assertIn({"field": "rain_state", "reason": "missing"}, result["issues"])
        self.assertIn({"field": "temperature", "reason": "out_of_range"}, result["issues"])
        invalid = sample(2, 1001)
        invalid["quality"] = {"soil_state": "invalid", "rain_state": "unknown"}
        result = self.store.accept(invalid, 1001)["result"]
        self.assertEqual(result["valid"], {})

    def test_dry_transition_and_dedup(self):
        self.store.accept(sample(), 1000)
        result = self.store.accept(sample(2, 1010), 1010)["result"]
        self.assertEqual(result["events"][0]["kind"], "continuous_dry")
        self.assertEqual(self.store.accept(sample(3, 1011), 1011)["result"]["events"], [])
        self.assertFalse(self.store.accept(sample(2, 1010), 1011)["accepted"])
        result = self.store.accept(sample(4, 1012, soil_state="OK", rain_state="WET"), 1012)["result"]
        self.assertEqual(result["events"][0]["kind"], "state_changed")
        self.assertEqual(result["transition_count"], 1)

    def test_gap_persisted_once_and_recovery(self):
        self.store.accept(sample(), 1000)
        self.store.tick(1016)
        self.assertEqual(self.store.status(1016)["devices"][0]["data_status"], "timeout")
        self.assertEqual(self.store.history()[0]["events"][0]["kind"], "data_timeout")
        count = self.store.status(1016)["record_count"]
        self.store.tick(1017)
        self.assertEqual(self.store.status(1017)["record_count"], count)
        recovered = self.store.accept(sample(2, 1018), 1018)["result"]
        self.assertEqual(recovered["events"][0]["kind"], "data_resumed")
        self.assertEqual(recovered["dry_active"], [])

    def test_restart_and_old_stream(self):
        self.store.accept(sample(), 1000)
        self.store.db.close()
        self.store = Store(self.path, CONFIG)
        self.assertFalse(self.store.accept(sample(), 1001)["accepted"])
        new = sample(1, 1002)
        new["boot_id"] = "boot-2"
        self.assertTrue(self.store.accept(new, 1002)["accepted"])
        self.assertFalse(self.store.accept(sample(99, 1001), 1003)["accepted"])

    def test_bounds_and_retention(self):
        for seq in range(1, 25):
            self.store.accept(sample(seq, 1000 + seq), 1000 + seq)
        self.assertLessEqual(self.store.status(1025)["record_count"], 5)
        self.store.tick(1200)
        self.store.tick(1400)
        self.assertEqual(self.store.status(1400)["record_count"], 0)

    def test_unknown_device_clock_skew_and_expired_result(self):
        bad = sample()
        bad["device_id"] = "COM9"
        with self.assertRaises(ValueError):
            self.store.accept(bad, 1000)
        with self.assertRaises(ValueError):
            self.store.accept(sample(), 2000)
        malformed = sample()
        malformed["pc_received_at"] = None
        with self.assertRaises(ValueError):
            self.store.accept(malformed, 1000)
        self.store.accept(sample(), 1020)
        self.assertEqual(self.store.status(1020)["devices"][0]["data_status"], "timeout")

    def test_invalid_breaks_continuous_dry(self):
        self.store.accept(sample(), 1000)
        self.store.accept(sample(2, 1009, soil_state="UNKNOWN", rain_state="WET"), 1009)
        result = self.store.accept(sample(3, 1011), 1011)["result"]
        self.assertEqual(result["dry_active"], [])

    def test_storage_failure_does_not_advance_watermark(self):
        self.store.db.execute("PRAGMA query_only=ON")
        with self.assertRaises(Exception):
            self.store.accept(sample(), 1000)
        self.assertNotIn("uno", self.store.states)
        self.assertIsNotNone(self.store.last_error)
        self.store.db.execute("PRAGMA query_only=OFF")
        self.assertTrue(self.store.accept(sample(), 1000)["accepted"])


class ForwarderTests(unittest.TestCase):
    def test_bounded_coalescing_allowlist(self):
        sender = SidecarForwarder("http://127.0.0.1:1", capacity=3)
        for i in range(20):
            sender.submit({"device_id": f"uno-{i}", "soil_state": "DRY", "image": "private"}, "now")
        self.assertEqual(len(sender.pending), 3)
        self.assertEqual(len(sender.latest), 3)
        self.assertEqual(sender.dropped, 17)
        sender.submit({"device_id": "uno-19", "soil_state": "WET"}, "now")
        self.assertEqual(len(sender.pending), 3)
        self.assertEqual(sender.dropped, 18)
        self.assertNotIn("image", sender.pending["uno-19"]["values"])
        sender.submit({"source": "COM9"}, "now")
        self.assertEqual(sender.skipped, 1)

    def test_network_never_on_submission_thread(self):
        sender = SidecarForwarder("http://127.0.0.1:1")
        with patch.object(sender, "_request", side_effect=AssertionError("unexpected I/O")):
            sender.submit({"device_id": "uno", "soil_state": "DRY"}, "now")
            self.assertEqual(sender.snapshot()["pending"], 1)

    def test_offline_worker_bounded_and_stoppable(self):
        sender = SidecarForwarder("http://127.0.0.1:1", timeout=0.1)
        sender.start()
        try:
            for _ in range(1000):
                sender.submit({"device_id": "uno", "soil_state": "DRY"}, "now")
            time.sleep(0.3)
            self.assertGreater(sender.snapshot()["errors"], 0)
            self.assertLessEqual(sender.snapshot()["pending"], 1)
            self.assertFalse(sender.snapshot()["online"])
        finally:
            sender.close()
        self.assertFalse(sender.thread.is_alive())

    def test_reconnect_replays_latest_once_without_new_input(self):
        sender = SidecarForwarder("http://unused")
        posts = []
        def request(path, data=None):
            if data is not None:
                posts.append(data["seq"])
                if len(posts) == 1:
                    raise OSError("edge was offline")
                return {"ok": True}
            return {"ok": True, "node_id": "edge", "devices": []}
        with patch.object(sender, "_request", side_effect=request):
            sender.submit({"device_id": "uno", "soil_state": "DRY"}, "now")
            sender.start()
            try:
                deadline = time.monotonic() + 5
                while sender.sent < 1 and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(sender.sent, 1)
                self.assertEqual(posts, [1, 1])
                self.assertTrue(sender.latest["uno"][2])
            finally:
                sender.close()


class IntegrationTests(unittest.TestCase):
    def test_real_http_delivery_auth_history_and_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text(json.dumps(CONFIG))
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            url = f"http://127.0.0.1:{port}"
            token = "test-only-token-123456"
            sender = SidecarForwarder(url, token, timeout=0.3)
            command = [sys.executable, str(ROOT / "edge/sidecar_service.py"), "--port", str(port), "--config", str(config), "--db", str(Path(folder) / "data.db")]
            process = subprocess.Popen(command, env=dict(os.environ, SIDECAR_TOKEN=token), stdout=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 8
                while True:
                    try:
                        sender._request("/v1/status")
                        break
                    except Exception:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(0.1)
                with self.assertRaises(urllib.error.HTTPError):
                    SidecarForwarder(url, "wrong")._request("/v1/status")
                with self.assertRaises(urllib.error.HTTPError):
                    sender._request("/v1/samples", {"version": 9})
                sender.start()
                sender.submit({"device_id": "uno", "soil_state": "DRY", "rain_state": "WET"}, datetime.now(timezone.utc).isoformat())
                deadline = time.monotonic() + 5
                while sender.snapshot()["sent"] == 0 and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertEqual(sender.snapshot()["sent"], 1)
                self.assertEqual(sender._request("/v1/history")["records"][0]["device_id"], "uno")
                process.terminate()
                process.wait(timeout=5)
                time.sleep(0.2)  # Windows can release file handles just after process termination.
                sender.submit({"device_id": "uno", "soil_state": "WET"}, datetime.now(timezone.utc).isoformat())
                time.sleep(0.5)
                self.assertGreater(sender.snapshot()["errors"], 0)
                process = subprocess.Popen(command, env=dict(os.environ, SIDECAR_TOKEN=token), stdout=subprocess.DEVNULL)
                time.sleep(0.3)
                sender.submit({"device_id": "uno", "soil_state": "WET", "rain_state": "WET"}, datetime.now(timezone.utc).isoformat())
                deadline = time.monotonic() + 7
                while sender.snapshot()["sent"] < 2 and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertGreaterEqual(sender.snapshot()["sent"], 2)
            finally:
                sender.close()
                process.terminate()
                process.wait(timeout=5)
                time.sleep(0.2)

    def test_firmware_telemetry_preserves_ok_and_ignores_command_logs(self):
        from backend.uno_telemetry import parse_telemetry
        payload = parse_telemetry("RAIN_RAW:900,RAIN:0%,RAIN_STATE:DRY,SOIL_RAW:500,SOIL:63%,SOIL_STATE:OK,DIST:NO_ECHO,NEAR:NO")
        self.assertEqual(payload["soil_state"], "OK")
        self.assertEqual(payload["quality"]["soil_state"], "valid")
        self.assertEqual(payload["soil_percent"], 63)
        self.assertNotIn("temperature", payload)
        self.assertIsNone(parse_telemetry("USB_CMD:DO,ID:1,QUEUED"))
        self.assertIsNone(parse_telemetry("LINK_TX:ID:1,SEQ:2,SENT_NO_ACK"))
        bad = parse_telemetry("RAIN_RAW:9999,SOIL:unknown")
        self.assertEqual(bad["quality"]["rain_raw"], "invalid")
        self.assertEqual(bad["quality"]["soil_percent"], "invalid")

    def test_backend_primary_commits_even_when_enqueue_fails(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"SMART_HOME_DB": str(Path(folder) / "pc.db"), "SIDECAR_URL": ""}):
            from backend.app import create_app
            app = create_app()
            with self.assertLogs(app.logger, level="ERROR"), patch.object(app.extensions["sidecar"], "submit", side_effect=RuntimeError("injected")):
                response = app.test_client().post("/api/sensor/update", json={"device_id": "uno", "temperature": 22})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(app.test_client().get("/api/status").json["temperature"], 22)
            self.assertEqual(app.test_client().get("/api/sidecar/status").status_code, 200)
            # Existing backend connections use SQLite transaction contexts; collect
            # their cycles before Windows removes the temporary database file.
            gc.collect()

    def test_slow_or_invalid_edge_does_not_delay_sensor_requests(self):
        class FaultHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.reply()

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.reply()

            def reply(self):
                if self.server.mode == "slow":
                    time.sleep(0.4)
                try:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"not json")
                except OSError:
                    pass

        server = HTTPServer(("127.0.0.1", 0), FaultHandler)
        server.mode = "slow"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"SMART_HOME_DB": str(Path(folder) / "pc.db"), "SIDECAR_URL": ""}):
                from backend.app import create_app
                app = create_app()
                sender = app.extensions["sidecar"]
                client = app.test_client()
                times = {}
                for mode in ("disabled", "slow", "invalid"):
                    server.mode = mode
                    if mode != "disabled":
                        sender.url = f"http://127.0.0.1:{server.server_port}"
                        sender.timeout = 0.1
                        sender.start()
                        sender.next_attempt = 0
                        time.sleep(0.2)
                    durations = []
                    for i in range(10):
                        started = time.monotonic()
                        response = client.post("/api/sensor/update", json={"device_id": "uno", "temperature": i, "soil_state": "DRY"})
                        durations.append(time.monotonic() - started)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(client.get("/api/health").status_code, 200)
                    times[mode] = max(durations)
                sender.close()
                self.assertGreater(sender.errors, 0)
                self.assertLess(times["slow"], max(0.2, times["disabled"] * 5))
                self.assertLess(times["invalid"], max(0.2, times["disabled"] * 5))
                print("\nSensor request max seconds (10 requests each):", times)
                gc.collect()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
