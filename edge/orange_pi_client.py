from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


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


def build_mock_payload(step: int, source: str) -> dict[str, Any]:
    temperature = round(25.0 + random.random() * 6.0, 1)
    return {
        "source": source,
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
    parser.add_argument("--no-ack", action="store_true", help="Do not acknowledge consumed commands.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    step = 0
    print(f"Orange Pi client started: backend={base_url}")
    while args.count <= 0 or step < args.count:
        payload = build_mock_payload(step, args.source)
        try:
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
