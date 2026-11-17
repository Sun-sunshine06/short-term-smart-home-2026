"""Read new-board USB telemetry; never send actuator commands or poll their queue."""
import argparse
import json
import queue
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uno_telemetry import parse_telemetry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="new expansion board USB port, e.g. COM9")
    parser.add_argument("--device-id", required=True, help="stable identity matching edge configuration")
    parser.add_argument("--backend", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    if not 1 <= len(args.device_id) <= 80:
        parser.error("device-id must be 1..80 characters")
    import serial
    pending = queue.Queue(maxsize=1)
    stop = threading.Event()
    counters = {"parsed": 0, "merged": 0, "sent": 0, "failed": 0}

    def upload():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while not stop.is_set():
            try:
                payload = pending.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                request = urllib.request.Request(args.backend.rstrip("/") + "/api/sensor/update",
                          data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
                with opener.open(request, timeout=1) as response:
                    if response.status != 200:
                        raise ValueError("backend rejected sample")
                counters["sent"] += 1
            except Exception:
                counters["failed"] += 1
                stop.wait(0.5)

    worker = threading.Thread(target=upload, daemon=True)
    worker.start()
    print("Opening USB may reset the new UNO. Telemetry only; no commands will be sent.", flush=True)
    try:
        with serial.Serial(args.port, 115200, timeout=0.2) as port:
            buffer = bytearray()
            discarding = False
            report_at = time.monotonic() + 5
            while not stop.is_set():
                for byte in port.read(256):
                    if byte == 10:
                        if not discarding:
                            payload = parse_telemetry(buffer.decode("ascii", errors="replace").strip())
                            if payload:
                                payload["device_id"] = args.device_id
                                counters["parsed"] += 1
                                try:
                                    pending.put_nowait(payload)
                                except queue.Full:
                                    try:
                                        pending.get_nowait()
                                        counters["merged"] += 1
                                    except queue.Empty:
                                        pass
                                    pending.put_nowait(payload)
                        buffer.clear()
                        discarding = False
                    elif not discarding:
                        buffer.append(byte)
                        if len(buffer) > 512:
                            buffer.clear()
                            discarding = True
                if time.monotonic() >= report_at:
                    print(json.dumps(counters), flush=True)
                    report_at = time.monotonic() + 5
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        worker.join(timeout=2)


if __name__ == "__main__":
    main()
