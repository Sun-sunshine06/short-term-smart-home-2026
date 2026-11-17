"""Compatibility monitor: only the backend opens the UNO serial port."""
import argparse
import json
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='expected backend UNO_PORT; does not open it')
    parser.add_argument('--device-id', help='expected backend UNO_DEVICE_ID')
    parser.add_argument('--backend', default='http://127.0.0.1:5000')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    print('USB collection now runs inside the backend. This command only monitors status.', flush=True)
    try:
        while True:
            try:
                with opener.open(args.backend.rstrip('/') + '/api/hardware/uno', timeout=2) as response:
                    status = json.load(response)['uno']
                if args.port and args.port != status['port']:
                    parser.error('Set UNO_PORT on the backend to match --port, then restart it.')
                if args.device_id and args.device_id != status['telemetry']['device_id']:
                    parser.error('Set UNO_DEVICE_ID on the backend to match --device-id, then restart it.')
                print(json.dumps(status, ensure_ascii=False), flush=True)
            except (OSError, ValueError, KeyError) as exc:
                if args.once:
                    raise SystemExit(f'Backend unavailable: {exc}')
                print(f'Backend unavailable: {exc}', flush=True)
            if args.once:
                return
            time.sleep(5)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
