from __future__ import annotations

import argparse
import json
import mimetypes
import os
import platform
import random
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


CLIENT_VERSION = "0.2.0"


def post_json(base_url: str, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url, path),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(urllib.parse.urljoin(base_url, path), method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_multipart_file(
    base_url: str,
    path: str,
    file_path: str,
    fields: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    image_path = os.path.expanduser(file_path)
    filename = os.path.basename(image_path)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary = f"----smart-home-{os.urandom(8).hex()}"

    body = bytearray()
    for key, value in fields.items():
        if value is None:
            continue
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    with open(image_path, "rb") as handle:
        body.extend(handle.read())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    request = urllib.request.Request(
        urllib.parse.urljoin(base_url, path),
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run_text(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=2)
    except Exception:
        return ""
    return completed.stdout.strip()


def read_os_release() -> dict[str, str]:
    path = "/etc/os-release"
    values: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if "=" not in line:
                    continue
                key, value = line.strip().split("=", 1)
                values[key] = value.strip().strip('"')
    except OSError:
        pass
    return values


def get_ip_addresses() -> list[str]:
    output = run_text(["hostname", "-I"])
    addresses = [item for item in output.split() if item]
    if addresses:
        return addresses
    try:
        return [socket.gethostbyname(socket.gethostname())]
    except OSError:
        return []


def read_meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                parts = value.strip().split()
                if parts:
                    result[key] = int(parts[0])
    except (OSError, ValueError):
        pass
    return result


def read_uptime_seconds() -> Any:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as handle:
            return float(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def build_registration_payload(node_id: str, name: str, role: str) -> dict[str, Any]:
    os_release = read_os_release()
    uname = platform.uname()
    return {
        "node_id": node_id,
        "name": name,
        "role": role,
        "hostname": socket.gethostname(),
        "os_name": os_release.get("PRETTY_NAME") or os_release.get("NAME") or platform.system(),
        "os_version": os_release.get("VERSION") or os_release.get("VERSION_ID"),
        "kernel": uname.release,
        "arch": uname.machine,
        "python_version": platform.python_version(),
        "client_version": CLIENT_VERSION,
        "ip_addresses": get_ip_addresses(),
    }


def build_heartbeat_payload(node_id: str, name: str) -> dict[str, Any]:
    disk = shutil.disk_usage("/")
    meminfo = read_meminfo()
    metrics: dict[str, Any] = {
        "uptime_seconds": read_uptime_seconds(),
        "disk_total_bytes": disk.total,
        "disk_used_bytes": disk.used,
        "disk_free_bytes": disk.free,
        "mem_total_kb": meminfo.get("MemTotal"),
        "mem_available_kb": meminfo.get("MemAvailable"),
    }
    if hasattr(os, "getloadavg"):
        try:
            metrics["load_avg"] = list(os.getloadavg())
        except OSError:
            pass
    return {
        "node_id": node_id,
        "name": name,
        "hostname": socket.gethostname(),
        "status": "online",
        "client_version": CLIENT_VERSION,
        "ip_addresses": get_ip_addresses(),
        "metrics": metrics,
    }


def upload_image(base_url: str, image_path: str, node_id: str, source: str, timeout: float) -> dict[str, Any]:
    response = post_multipart_file(
        base_url,
        "/api/camera/upload",
        image_path,
        {
            "source": source,
            "node_id": node_id,
        },
        timeout,
    )
    record = response.get("yolo_record") or {}
    print(
        "image upload: "
        f"ok={response.get('ok')} "
        f"image_path={response.get('image_path')} "
        f"model={record.get('model_name') or '--'}"
    )
    return response


def build_mock_payload(step: int, source: str, node_id: str) -> dict[str, Any]:
    temperature = round(25.0 + random.random() * 6.0, 1)
    return {
        "source": source,
        "node_id": node_id,
        "temperature": temperature,
        "door_open": step % 12 in {0, 1},
        "window_open": step % 20 in {5, 6, 7},
        "light_level": random.randint(20, 95),
        "fan_on": temperature >= 28.0,
        "lock_open": step % 30 == 0,
    }


def handle_command(command: dict[str, Any]) -> str:
    target = command.get("target")
    action = command.get("action")
    value = command.get("value")
    print(f"command #{command.get('id')}: target={target} action={action} value={value}")
    # Hardware GPIO/PWM calls can be wired here after the hardware pin mapping is confirmed.
    return "done"


def poll_commands(base_url: str, timeout: float, acknowledge: bool) -> None:
    data = get_json(base_url, "/api/device/commands?limit=10", timeout)
    for command in data.get("commands", []):
        status = handle_command(command)
        if acknowledge and command.get("id") is not None:
            post_json(
                base_url,
                f"/api/device/commands/{command['id']}/ack",
                {"status": status},
                timeout,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Orange Pi AIpro 20T edge client.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SMART_HOME_BACKEND", "http://127.0.0.1:5000"),
        help="Backend base URL, for example http://10.200.77.182:5000",
    )
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between sensor updates.")
    parser.add_argument("--count", type=int, default=0, help="Number of loops; 0 means forever.")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout seconds.")
    parser.add_argument("--source", default="orange_pi_aipro_20t", help="Sensor source name.")
    parser.add_argument("--node-id", default=os.environ.get("ORANGE_PI_NODE_ID"), help="Stable edge node id.")
    parser.add_argument("--name", default="Orange Pi AIpro 20T", help="Human-readable node name.")
    parser.add_argument("--role", default="orange_pi_edge", help="Node role stored by the backend.")
    parser.add_argument("--heartbeat-every", type=int, default=1, help="Send heartbeat every N loops; 0 disables it.")
    parser.add_argument("--upload-image", help="Upload one local image from Orange Pi to backend YOLO flow, then exit by default.")
    parser.add_argument("--image-source", default="orange_pi_camera", help="Source name for image upload records.")
    parser.add_argument("--continue-after-upload", action="store_true", help="Continue sensor loop after --upload-image.")
    parser.add_argument("--no-ack", action="store_true", help="Do not acknowledge consumed commands.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    node_id = (args.node_id or socket.gethostname() or args.source).strip()
    step = 0
    print(f"Orange Pi client started: backend={base_url} node_id={node_id}")
    try:
        registration = post_json(
            base_url,
            "/api/edge/register",
            build_registration_payload(node_id, args.name, args.role),
            args.timeout,
        )
        print(f"register: {registration.get('ok')}")
    except urllib.error.URLError as exc:
        print(f"register network error: {exc}")
    except Exception as exc:
        print(f"register error: {exc}")

    if args.upload_image:
        try:
            upload_image(base_url, args.upload_image, node_id, args.image_source, args.timeout)
        except urllib.error.URLError as exc:
            print(f"image upload network error: {exc}")
        except Exception as exc:
            print(f"image upload error: {exc}")
        if not args.continue_after_upload:
            return

    while args.count <= 0 or step < args.count:
        payload = build_mock_payload(step, args.source, node_id)
        try:
            if args.heartbeat_every > 0 and step % args.heartbeat_every == 0:
                heartbeat = post_json(
                    base_url,
                    "/api/edge/heartbeat",
                    build_heartbeat_payload(node_id, args.name),
                    args.timeout,
                )
                print(f"heartbeat #{step + 1}: {heartbeat.get('ok')}")
            response = post_json(base_url, "/api/sensor/update", payload, args.timeout)
            print(f"sensor #{step + 1}: {payload} -> {response.get('ok')}")
            poll_commands(base_url, args.timeout, acknowledge=not args.no_ack)
        except urllib.error.URLError as exc:
            print(f"network error: {exc}")
        except Exception as exc:
            print(f"client error: {exc}")
        step += 1
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
