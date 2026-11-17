from __future__ import annotations

import os
import tempfile
import unittest
import gc
from pathlib import Path

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
        self.assertEqual(status["light_level"], 0)
        self.assertFalse(status["fan_on"])
        self.assertFalse(status["door_open"])


if __name__ == "__main__":
    unittest.main()
