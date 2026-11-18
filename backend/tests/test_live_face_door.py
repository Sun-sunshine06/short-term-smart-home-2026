from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from flask import Flask
from backend.vision import live_camera


class LiveFaceDoorTests(TestCase):
    def test_only_one_open_per_visit(self):
        camera = live_camera.LiveCamera("test")
        camera.frame = b"test frame"
        references = lambda: [("member", "Member", Path("reference.jpg"))]
        door = Mock(return_value={"status": "link_sent_no_ack", "command_id": 1})
        app = Flask(__name__)
        with patch.object(live_camera, "LiveCamera", return_value=camera):
            live_camera.register_live_camera(app, "test", references, door)
        client = app.test_client()
        with patch.object(live_camera, "monotonic") as clock, patch.object(live_camera, "verify_camera_frame") as model:
            def sample(t, state, method="POST"):
                clock.return_value = camera.frame_time = t
                model.return_value = {"state": state, "identity": "member" if state == "matched" else None}
                return client.open("/api/live/face", method=method, json={}).get_json()

            sample(10, "matched", "GET")
            sample(11, "unknown")
            door.assert_not_called()
            self.assertEqual(sample(12, "matched")["door"]["command_id"], 1)
            sample(14, "matched")
            sample(15, "no_face")
            sample(16, "matched")
            door.assert_called_once()
            sample(17, "no_face")
            sample(18, "no_face")
            sample(19, "no_face")
            sample(20, "matched")
            self.assertEqual(door.call_count, 2)
