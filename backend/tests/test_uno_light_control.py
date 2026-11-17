from __future__ import annotations

import os
import tempfile
import unittest
import gc
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ["UNO_SERIAL_ENABLED"] = "0"

from backend.hardware.uno_serial import UnoCommandResult, UnoSerialBridge  # noqa: E402


class _LoopbackSerial:
    def __init__(self, bridge: UnoSerialBridge) -> None:
        self.bridge = bridge
        self.is_open = True
        self.writes: list[bytes] = []

    def write(self, payload: bytes) -> int:
        self.writes.append(payload)
        command = payload.decode("ascii").strip()
        command_id = {"DO": 1, "DC": 2, "FO": 3, "FC": 4, "LO": 5, "LC": 6}[command]
        self.bridge._record_line(f"USB_CMD:{command},ID:{command_id},QUEUED")
        self.bridge._record_line(f"LINK_TX:ID:{command_id},SEQ:1,SENT_NO_ACK")
        return len(payload)

    def flush(self) -> None:
        return None


class UnoSerialBridgeTests(unittest.TestCase):
    def test_control_commands_wait_for_new_board_delivery(self) -> None:
        bridge = UnoSerialBridge(port="COM9", enabled=False)
        serial_connection = _LoopbackSerial(bridge)
        bridge._serial = serial_connection
        bridge._connected = True
        bridge._ready = True

        results = [bridge.send_command(command) for command in ("LO", "LC", "FO", "FC", "DO", "DC")]

        self.assertEqual(serial_connection.writes, [b"LO\n", b"LC\n", b"FO\n", b"FC\n", b"DO\n", b"DC\n"])
        self.assertTrue(all(result.stage == "link_sent_no_ack" for result in results))
        self.assertEqual([result.command_id for result in results], [5, 6, 3, 4, 1, 2])
        self.assertTrue(all(not result.confirmed for result in results))


class _FakeBridge:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def start(self) -> None:
        return None

    def snapshot(self) -> dict[str, object]:
        return {"enabled": True, "port": "COM9", "connected": True, "ready": True}

    def send_command(self, command: str) -> UnoCommandResult:
        self.commands.append(command)
        command_id = {"DO": 1, "DC": 2, "FO": 3, "FC": 4, "LO": 5, "LC": 6}[command]
        return UnoCommandResult(
            command=command,
            command_id=command_id,
            stage="link_sent_no_ack",
            accepted_line=f"USB_CMD:{command},ID:{command_id},QUEUED",
            delivery_line=f"LINK_TX:ID:{command_id},SEQ:1,SENT_NO_ACK",
        )


class LightControlApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["SMART_HOME_DB"] = str(Path(self.temp_dir.name) / "test.db")
        from backend.app import create_app

        self.bridge = _FakeBridge()
        self.app = create_app(self.bridge)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.client = None
        self.app = None
        gc.collect()
        self.temp_dir.cleanup()

    def test_web_controls_map_to_uno_commands(self) -> None:
        before = self.client.get("/api/status").get_json()
        requests = [
            ("light", "on", "LO"),
            ("light", "off", "LC"),
            ("fan", "on", "FO"),
            ("fan", "off", "FC"),
            ("door", "open", "DO"),
            ("door", "close", "DC"),
        ]
        responses = [
            self.client.post("/api/device/control", json={"target": target, "action": action})
            for target, action, _ in requests
        ]

        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(self.bridge.commands, [command for _, _, command in requests])
        self.assertTrue(all(response.get_json()["status"] == "link_sent_no_ack" for response in responses))

        status = self.client.get("/api/status").get_json()
        for field in ("light_level", "fan_on", "door_open", "hardware_online", "updated_at"):
            self.assertEqual(status[field], before[field])
        for field in ("light_level", "fan_on", "door_open"):
            self.assertEqual(status["expected_states"][field]["value"], 0)
            self.assertFalse(status["expected_states"][field]["confirmed"])

    def test_open_estimate_expires_after_refresh_and_app_restart(self) -> None:
        from backend.app import create_app
        self.client.post("/api/device/control", json={"target": "door", "action": "open"})
        state = self.client.get("/api/status").get_json()["expected_states"]["door_open"]
        self.assertTrue(state["value"])
        deadline = datetime.fromisoformat(state["auto_close_at"])
        restarted = create_app(self.bridge).test_client()
        with patch("backend.app.datetime") as clock:
            clock.fromisoformat.side_effect = datetime.fromisoformat
            clock.now.return_value = deadline - timedelta(milliseconds=1)
            self.assertTrue(restarted.get("/api/status").get_json()["expected_states"]["door_open"]["value"])
            clock.now.return_value = deadline
            self.assertFalse(restarted.get("/api/status").get_json()["expected_states"]["door_open"]["value"])

    def test_failed_command_does_not_create_estimate_or_mark_online(self) -> None:
        from backend.hardware.uno_serial import UnoBridgeUnavailable
        before = self.client.get("/api/status").get_json()
        with patch.object(self.bridge, "send_command", side_effect=UnoBridgeUnavailable("offline")):
            response = self.client.post("/api/device/control", json={"target": "door", "action": "open"})
        self.assertEqual(response.status_code, 503)
        after = self.client.get("/api/status").get_json()
        self.assertEqual(after, before)

    def test_queued_command_is_not_an_execution_estimate(self) -> None:
        result = UnoCommandResult("DO", 1, "queued", "USB_CMD:DO,ID:1,QUEUED", None)
        with patch.object(self.bridge, "send_command", return_value=result):
            self.client.post("/api/device/control", json={"target": "door", "action": "open"})
        self.assertEqual(self.client.get("/api/status").get_json()["expected_states"], {})


if __name__ == "__main__":
    unittest.main()
