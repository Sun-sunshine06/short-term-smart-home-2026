import gc
import json
import os
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['UNO_SERIAL_ENABLED'] = '0'
from backend.hardware.uno_serial import UnoSerialBridge

LINE = 'RAIN_RAW:123,RAIN:12%,RAIN_STATE:DRY,SOIL_RAW:456,SOIL:63%,SOIL_STATE:OK'


def wait_for(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError('condition did not become true')


class SerialPort:
    def __init__(self):
        self.is_open = True
        self.input = queue.Queue()
        self.writes = []

    def read(self, size):
        try:
            value = self.input.get(timeout=0.01)
        except queue.Empty:
            return b''
        if isinstance(value, Exception):
            raise value
        return value

    def write(self, payload):
        self.writes.append(payload)
        if payload == b'PING\n':
            self.input.put(b'PONG,USB_ASR_D3_V1\n')
        else:
            self.input.put((LINE + '\nUSB_CMD:LO,ID:5,QUEUED\nLINK_TX:ID:5,SEQ:1,SENT_NO_ACK\n').encode())
        return len(payload)

    def reset_input_buffer(self):
        pass

    def flush(self):
        pass

    def close(self):
        self.is_open = False


class BridgeTests(unittest.TestCase):
    def test_slow_sink_does_not_block_commands_queue_is_bounded_and_reconnects(self):
        first, second = SerialPort(), SerialPort()
        bridge = UnoSerialBridge(enabled=True, startup_seconds=0, reconnect_seconds=0.01)
        entered, release = threading.Event(), threading.Event()
        delivered = []

        def sink(payload, received_at):
            entered.set()
            release.wait(2)
            delivered.append(payload)

        bridge.set_telemetry_handler(sink)
        with patch('serial.Serial', side_effect=[first, second]) as factory:
            try:
                bridge.start()
                bridge.start()
                wait_for(lambda: bridge.snapshot()['ready'])
                # Fragmented lines survive read timeouts; oversized lines are discarded.
                first.input.put(b'x' * 513 + b'\n' + LINE[:20].encode())
                first.input.put((LINE[20:] + '\n').encode())
                self.assertTrue(entered.wait(1))
                for _ in range(25):
                    first.input.put((LINE + '\n').encode())
                wait_for(lambda: bridge.snapshot()['telemetry']['received'] >= 26)
                result = bridge.send_command('LO', timeout=0.5)
                self.assertEqual(result.stage, 'link_sent_no_ack')
                status = bridge.snapshot()['telemetry']
                self.assertEqual(status['pending'], 1)
                self.assertGreater(status['dropped'], 0)
                self.assertEqual(factory.call_count, 1)
                first.input.put(OSError('unplugged'))
                wait_for(lambda: factory.call_count == 2 and bridge.snapshot()['ready'])
                self.assertFalse(first.is_open)
                self.assertEqual(second.writes, [b'PING\n'])  # Never replay actuator commands.
                release.set()
                wait_for(lambda: bridge.snapshot()['telemetry']['delivered'] >= 2)
                self.assertEqual(delivered[-1]['soil_state'], 'OK')
            finally:
                release.set()
                bridge.stop()
        self.assertFalse(bridge._thread.is_alive())
        self.assertFalse(bridge._telemetry_thread.is_alive())

    def test_storage_failure_is_visible_and_next_sample_recovers(self):
        bridge = UnoSerialBridge(enabled=True, startup_seconds=0)
        sink = unittest.mock.Mock(side_effect=[OSError('disk failure'), None])
        bridge.set_telemetry_handler(sink)
        with patch('serial.Serial', return_value=SerialPort()):
            try:
                bridge.start()
                bridge._record_line(LINE)
                wait_for(lambda: bridge.snapshot()['telemetry']['errors'] == 1)
                bridge._record_line(LINE)
                wait_for(lambda: bridge.snapshot()['telemetry']['delivered'] == 1)
                self.assertIsNone(bridge.snapshot()['telemetry']['last_error'])
            finally:
                bridge.stop()

    def test_telemetry_persists_and_forwards_without_fabricating_old_board_state(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SMART_HOME_DB': str(Path(folder) / 'test.db')}):
            from backend.app import create_app, connect_db
            bridge = UnoSerialBridge(enabled=False)
            app = create_app(bridge)
            client = app.test_client()
            with connect_db() as conn:
                conn.execute('UPDATE device_states SET hardware_online=0, light_level=71 WHERE id=1')
                conn.commit()
            before = client.get('/api/status').get_json()
            bridge._record_line('USB_CMD:LO,ID:5,QUEUED')
            self.assertEqual(bridge.snapshot()['telemetry']['received'], 0)
            bridge._record_line(LINE)
            payload, timestamp = bridge._pending_telemetry.popleft()
            with patch.object(app.extensions['sidecar'], 'submit') as submit:
                bridge._telemetry_handler(payload, timestamp)
                submit.assert_called_once_with(payload, timestamp)
            after = client.get('/api/status').get_json()
            for field in ('door_open', 'fan_on', 'light_level', 'hardware_online'):
                self.assertEqual(before[field], after[field])
            with connect_db() as conn:
                raw = conn.execute('SELECT raw_json FROM sensor_records ORDER BY id DESC LIMIT 1').fetchone()[0]
            self.assertEqual(json.loads(raw)['device_id'], 'uno-soil-rain')
            self.assertEqual(json.loads(raw)['soil_percent'], 63)
            conn.close()
            app.extensions['sidecar'].close()
            client = app = None
            bridge.set_telemetry_handler(None)
            gc.collect()


if __name__ == '__main__':
    unittest.main()
