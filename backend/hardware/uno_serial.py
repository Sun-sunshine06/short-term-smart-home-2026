from __future__ import annotations

import atexit
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from uno_telemetry import parse_telemetry
except ImportError:
    from backend.uno_telemetry import parse_telemetry


COMMAND_IDS = {
    "DO": 1,
    "DC": 2,
    "FO": 3,
    "FC": 4,
    "LO": 5,
    "LC": 6,
    "BELL": 7,
    "FA": 13,
    "LA": 14,
    "AUTO": 15,
    "FACE_OPEN": 1,
}


class UnoBridgeError(RuntimeError):
    """Base error returned by the UNO serial bridge."""


class UnoBridgeUnavailable(UnoBridgeError):
    """Raised when COM9 is not connected and ready."""


class UnoCommandRejected(UnoBridgeError):
    """Raised when the new UNO explicitly rejects a command."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class UnoCommandResult:
    command: str
    command_id: int
    stage: str
    accepted_line: str
    delivery_line: str | None
    confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "command_id": self.command_id,
            "stage": self.stage,
            "accepted_line": self.accepted_line,
            "delivery_line": self.delivery_line,
            "confirmed": self.confirmed,
        }


class UnoSerialBridge:
    """Own the new UNO USB serial port and provide command-level delivery.

    Only the explicitly configured port is opened. The bridge never probes
    other serial ports, so the old UNO on COM10 is left untouched.
    """

    def __init__(
        self,
        port: str | None = None,
        baudrate: int | None = None,
        *,
        enabled: bool | None = None,
        reconnect_seconds: float = 2.0,
        startup_seconds: float = 2.0,
    ) -> None:
        self.port = port or os.environ.get("UNO_PORT", "COM9")
        self.baudrate = baudrate or int(os.environ.get("UNO_BAUD", "115200"))
        self.enabled = _env_bool("UNO_SERIAL_ENABLED", True) if enabled is None else enabled
        self.reconnect_seconds = reconnect_seconds
        self.startup_seconds = startup_seconds

        self._state_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._command_lock = threading.Lock()
        self._condition = threading.Condition(self._state_lock)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._serial: Any = None

        self._connected = False
        self._ready = False
        self._firmware: str | None = None
        self._last_error: str | None = None
        self._last_line: str | None = None
        self._last_seen_at: str | None = None
        self._line_sequence = 0
        self._lines: deque[tuple[int, str]] = deque(maxlen=200)
        self._telemetry_handler = None
        self._telemetry_thread = None
        self._pending_telemetry = deque(maxlen=1)
        self._telemetry_received = self._telemetry_delivered = 0
        self._telemetry_dropped = self._telemetry_errors = 0
        self._telemetry_error = None
        self.device_id = os.environ.get("UNO_DEVICE_ID", "uno-soil-rain")
        if not 1 <= len(self.device_id) <= 80:
            raise ValueError("UNO_DEVICE_ID must contain 1..80 characters")

    def set_telemetry_handler(self, handler) -> None:
        with self._condition:
            self._telemetry_handler = handler

    def _deliver_telemetry(self) -> None:
        while not self._stop_event.is_set():
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stop_event.is_set() or bool(self._pending_telemetry), timeout=0.2
                )
                if self._stop_event.is_set():
                    return
                if not self._pending_telemetry:
                    continue
                payload, received_at = self._pending_telemetry.popleft()
                handler = self._telemetry_handler
            try:
                if handler is None:
                    raise RuntimeError("Telemetry handler is not configured")
                handler(payload, received_at)
                with self._condition:
                    self._telemetry_delivered += 1
                    self._telemetry_error = None
            except Exception as exc:
                with self._condition:
                    self._telemetry_errors += 1
                    self._telemetry_error = str(exc)

    def start(self) -> None:
        if not self.enabled:
            return
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            if not self._telemetry_thread or not self._telemetry_thread.is_alive():
                self._telemetry_thread = threading.Thread(
                    target=self._deliver_telemetry, name="uno-telemetry", daemon=True
                )
                self._telemetry_thread.start()
            self._thread = threading.Thread(target=self._run, name="uno-serial-bridge", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        serial_connection = None
        with self._state_lock:
            serial_connection = self._serial
            self._condition.notify_all()
        if serial_connection is not None:
            try:
                serial_connection.close()
            except Exception:
                pass
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
        worker = self._telemetry_thread
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=2)

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "enabled": self.enabled,
                "port": self.port,
                "baudrate": self.baudrate,
                "connected": self._connected,
                "ready": self._ready,
                "firmware": self._firmware,
                "last_error": self._last_error,
                "last_line": self._last_line,
                "last_seen_at": self._last_seen_at,
                "telemetry": {
                    "device_id": self.device_id,
                    "pending": len(self._pending_telemetry),
                    "received": self._telemetry_received,
                    "delivered": self._telemetry_delivered,
                    "dropped": self._telemetry_dropped,
                    "errors": self._telemetry_errors,
                    "last_error": self._telemetry_error,
                },
            }

    def send_command(self, command: str, timeout: float = 5.0) -> UnoCommandResult:
        command = command.strip().upper()
        command_id = COMMAND_IDS.get(command)
        if command_id is None:
            raise ValueError(f"unsupported UNO command: {command}")

        with self._command_lock:
            with self._condition:
                if not self._ready or self._serial is None:
                    detail = self._last_error or f"{self.port} is not ready"
                    raise UnoBridgeUnavailable(detail)
                start_sequence = self._line_sequence

            self._write(f"{command}\n".encode("ascii"))
            deadline = time.monotonic() + timeout
            accepted_line: str | None = None
            delivery_line: str | None = None

            while time.monotonic() < deadline:
                with self._condition:
                    new_lines = [item for item in self._lines if item[0] > start_sequence]
                    for sequence, line in new_lines:
                        start_sequence = max(start_sequence, sequence)
                        if line.startswith(f"USB_CMD:{command},") and line.endswith("QUEUED"):
                            accepted_line = line
                        elif line.startswith(f"USB_CMD:{command},COOLDOWN"):
                            raise UnoCommandRejected(line)
                        elif line.startswith("USB_BUSY:") or line.startswith("USB_UNKNOWN:"):
                            raise UnoCommandRejected(line)
                        elif accepted_line and line.startswith(f"LINK_TX:ID:{command_id},"):
                            if line.endswith("SENT_NO_ACK"):
                                delivery_line = line
                                return UnoCommandResult(
                                    command=command,
                                    command_id=command_id,
                                    stage="link_sent_no_ack",
                                    accepted_line=accepted_line,
                                    delivery_line=delivery_line,
                                )
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        self._condition.wait(timeout=min(remaining, 0.25))

            if accepted_line:
                return UnoCommandResult(
                    command=command,
                    command_id=command_id,
                    stage="queued",
                    accepted_line=accepted_line,
                    delivery_line=delivery_line,
                )
            raise UnoBridgeError(f"timeout waiting for {command} response from {self.port}")

    def _run(self) -> None:
        try:
            import serial
        except Exception as exc:
            self._set_disconnected(f"pyserial unavailable: {exc}")
            return

        while not self._stop_event.is_set():
            connection = None
            try:
                connection = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=0.2,
                    write_timeout=1.0,
                )
                with self._condition:
                    self._serial = connection
                    self._connected = True
                    self._ready = False
                    self._last_error = None
                    self._condition.notify_all()

                if self._stop_event.wait(self.startup_seconds):
                    break
                connection.reset_input_buffer()
                self._write(b"PING\n")
                next_ping_at = time.monotonic() + 2.0
                buffer = bytearray()
                discarding = False

                while not self._stop_event.is_set() and connection.is_open:
                    for byte in connection.read(256):
                        if byte == 10:
                            if buffer and not discarding:
                                self._record_line(buffer.decode("utf-8", errors="replace").strip())
                            buffer.clear()
                            discarding = False
                        elif not discarding:
                            buffer.append(byte)
                            if len(buffer) > 512:
                                buffer.clear()
                                discarding = True
                    if not self.snapshot()["ready"] and time.monotonic() >= next_ping_at:
                        self._write(b"PING\n")
                        next_ping_at = time.monotonic() + 2.0
            except Exception as exc:
                self._set_disconnected(str(exc))
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
                with self._condition:
                    self._serial = None
                    self._connected = False
                    self._ready = False
                    self._condition.notify_all()

            self._stop_event.wait(self.reconnect_seconds)

    def _write(self, payload: bytes) -> None:
        with self._write_lock:
            with self._state_lock:
                connection = self._serial
            if connection is None or not connection.is_open:
                raise UnoBridgeUnavailable(f"{self.port} is disconnected")
            connection.write(payload)
            connection.flush()

    def _record_line(self, line: str) -> None:
        payload = parse_telemetry(line)
        with self._condition:
            if payload is not None:
                payload["device_id"] = self.device_id
                self._telemetry_received += 1
                self._telemetry_dropped += int(bool(self._pending_telemetry))
                self._pending_telemetry.append((payload, datetime.now(timezone.utc).isoformat()))
            self._line_sequence += 1
            self._lines.append((self._line_sequence, line))
            self._last_line = line
            self._last_seen_at = _utc_now()
            if line.startswith("PONG,USB_ASR_D3_V1"):
                self._ready = True
                self._firmware = "USB_ASR_D3_V1"
                self._last_error = None
            self._condition.notify_all()

    def _set_disconnected(self, error: str) -> None:
        with self._condition:
            self._connected = False
            self._ready = False
            self._last_error = error
            self._condition.notify_all()


_default_bridge = UnoSerialBridge()
atexit.register(_default_bridge.stop)


def get_uno_bridge() -> UnoSerialBridge:
    return _default_bridge
