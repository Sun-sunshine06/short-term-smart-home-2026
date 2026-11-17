"""Read-only migration check. Does not open USB ports or send control/sample data."""
import json
import os
import sys
import urllib.request
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parents[2]
    config = {}
    path = repo / "local" / "sidecar.env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in ("SIDECAR_URL", "SIDECAR_TOKEN"):
                config[key] = value.strip()
    url = config.get("SIDECAR_URL", os.environ.get("SIDECAR_URL", "")).rstrip("/")
    token = config.get("SIDECAR_TOKEN", os.environ.get("SIDECAR_TOKEN", ""))
    print("Project directory:", repo)
    print("Python:", sys.version.split()[0])
    if not url or not token or token.startswith("replace-"):
        print("Sidecar is not configured. Set local/sidecar.env; local frontend work can continue without the board.")
        return 2
    request = urllib.request.Request(url + "/v1/status", headers={"Authorization": "Bearer " + token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=3) as response:
            raw = response.read(131073)
        if len(raw) > 131072:
            raise ValueError("oversized response")
        result = json.loads(raw)
        if result.get("ok") is not True or not isinstance(result.get("devices"), list):
            raise ValueError("invalid status response")
        print("Sidecar reachable; authentication accepted. Node:", result.get("node_id"))
        for device in result["devices"]:
            print("Device:", device.get("device_id"), "Data:", device.get("data_status"))
        if result.get("last_error"):
            print("Board storage requires attention:", result["last_error"])
            return 3
        print("No samples or control commands were sent. USB and video still require on-site checks.")
        return 0
    except Exception as exc:
        print("Sidecar check failed:", type(exc).__name__)
        print("Check board power/service, the configured address, network reachability and shared secret.")
        print("The backend can still run without the sidecar.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
