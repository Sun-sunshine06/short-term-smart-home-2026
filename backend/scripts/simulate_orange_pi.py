from __future__ import annotations

import argparse
import random
import time

import requests


def build_payload(step: int) -> dict:
    temperature = round(25.0 + random.random() * 6.0, 1)
    return {
        "source": "orange_pi_aipro_simulator",
        "temperature": temperature,
        "door_open": step % 12 in {0, 1},
        "window_open": step % 20 in {5, 6, 7},
        "light_level": random.randint(20, 95),
        "fan_on": temperature >= 28.0,
        "lock_open": step % 30 == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate Orange Pi AIpro sensor uploads.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Backend base URL.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between updates.")
    parser.add_argument("--count", type=int, default=0, help="Number of updates; 0 means forever.")
    args = parser.parse_args()

    step = 0
    while args.count <= 0 or step < args.count:
        payload = build_payload(step)
        response = requests.post(f"{args.base_url}/api/sensor/update", json=payload, timeout=5)
        response.raise_for_status()
        print(f"sent #{step + 1}: {payload} -> {response.status_code}")
        step += 1
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
