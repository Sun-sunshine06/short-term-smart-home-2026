"""Orange Pi sidecar: standard-library HTTP, bounded SQLite storage, advisory rules only."""
from __future__ import annotations

import argparse
import hmac
import json
import math
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FIELDS = {"temperature", "soil_raw", "soil_percent", "soil_state", "rain_raw", "rain_percent", "rain_state"}
RULE_VERSION = "1"


def timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("timestamp must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.timestamp()


def validate_config(config):
    if not isinstance(config, dict) or not 1 <= len(config) <= 32:
        raise ValueError("configure 1..32 stable devices")
    for device, rule in config.items():
        if not isinstance(device, str) or not 1 <= len(device) <= 80 or not isinstance(rule, dict):
            raise ValueError("invalid device configuration")
        required = rule.get("required", [])
        if not isinstance(required, list) or not set(required) <= FIELDS:
            raise ValueError("unknown required field")
        for key in ("timeout_seconds", "dry_seconds"):
            value = rule.get(key, 15 if key == "timeout_seconds" else 60)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("invalid rule duration")
        for field, limits in rule.get("ranges", {}).items():
            if field not in FIELDS or field.endswith("_state") or not isinstance(limits, list) or len(limits) != 2:
                raise ValueError("invalid range")
            if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in limits) or limits[0] >= limits[1]:
                raise ValueError("invalid range bounds")
    return config


class Store:
    def __init__(self, path, config, node_id="orange-pi-sidecar", max_rows=10000, retention=604800):
        self.config = validate_config(config)
        self.node_id, self.boot_id = node_id, str(uuid.uuid4())
        self.started = time.time()
        self.max_rows, self.retention = max_rows, retention
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=DELETE")
        # 32 MiB hard limit for database pages, plus bounded rollback journal.
        self.db.execute("PRAGMA max_page_count=8192")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, received REAL, body TEXT, result TEXT);
            CREATE TABLE IF NOT EXISTS devices(device TEXT PRIMARY KEY, state TEXT);
        """)
        self.states = {d: json.loads(s) for d, s in self.db.execute("SELECT device,state FROM devices") if d in config}
        self.last_error = None

    def _prune(self, now):
        self.db.execute("DELETE FROM samples WHERE received < ?", (now - self.retention,))
        self.db.execute("DELETE FROM samples WHERE id IN (SELECT id FROM samples ORDER BY id DESC LIMIT -1 OFFSET ?)", (self.max_rows - 1,))

    def accept(self, sample, now=None):
        now = time.time() if now is None else now
        if not isinstance(sample, dict) or type(sample.get("version")) is not int or sample.get("version") != 1:
            raise ValueError("unsupported envelope")
        device, boot, seq = sample.get("device_id"), sample.get("boot_id"), sample.get("seq")
        if not isinstance(device, str) or device not in self.config:
            raise ValueError("unknown device_id; configure stable identity first")
        if not isinstance(boot, str) or not 1 <= len(boot) <= 80 or type(seq) is not int or seq < 1:
            raise ValueError("invalid boot_id or seq")
        pc_time = timestamp(sample["pc_received_at"])
        if pc_time > now + 30 or pc_time < now - 180:
            raise ValueError("sample expired or PC clock skew exceeds limit")
        values, quality = sample.get("values"), sample.get("quality", {})
        if not isinstance(values, dict) or not set(values) <= FIELDS or not isinstance(quality, dict) or not set(quality) <= FIELDS:
            raise ValueError("invalid fields")
        if any(not isinstance(v, (str, int, float, bool, type(None))) or
               isinstance(v, str) and len(v) > 80 for v in values.values()):
            raise ValueError("invalid value type or length")
        if any(v not in ("valid", "invalid", "unknown") for v in quality.values()):
            raise ValueError("invalid quality flag")
        previous = self.states.get(device)
        if previous:
            if boot == previous["source_boot_id"] and seq <= previous["source_seq"]:
                return {"ok": True, "accepted": False, "reason": "duplicate_or_out_of_order"}
            if pc_time < previous["pc_time"] or (boot != previous["source_boot_id"] and pc_time <= previous["pc_time"]):
                return {"ok": True, "accepted": False, "reason": "old_stream"}
        rule = self.config[device]
        issues, valid, events, dry_since = [], {}, [], {}
        for field in set(values) | set(rule.get("required", [])):
            value = values.get(field)
            reason = None
            if field not in values:
                reason = "missing"
            elif value is None or quality.get(field) == "unknown":
                reason = "unknown"
            elif quality.get(field) == "invalid":
                reason = "invalid"
            elif field.endswith("_state"):
                allowed = ("DRY", "OK") if field == "soil_state" else ("DRY", "WET")
                if value not in allowed:
                    reason = "invalid"
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                reason = "invalid"
            else:
                limits = rule.get("ranges", {}).get(field, [0, 100] if field.endswith("_percent") else None)
                if limits and not limits[0] <= value <= limits[1]:
                    reason = "out_of_range"
            if reason:
                issues.append({"field": field, "reason": reason})
            else:
                valid[field] = value
        contiguous = previous and not previous.get("timed_out") and now <= previous["expires_at"] and boot == previous["source_boot_id"]
        if previous and not contiguous:
            events.append({"kind": "data_resumed", "reason": "new stream or data gap"})
        for field in ("soil_state", "rain_state"):
            value = valid.get(field)
            old = previous.get("valid", {}).get(field) if contiguous else None
            if old is not None and value is not None and value != old:
                events.append({"kind": "state_changed", "field": field, "from": old, "to": value})
            if value == "DRY":
                since = previous.get("dry_since", {}).get(field, now) if contiguous and old == "DRY" else now
                dry_since[field] = since
                threshold = rule.get("dry_seconds", 60)
                already = contiguous and field in previous.get("dry_active", [])
                if now - since >= threshold and not already:
                    events.append({"kind": "continuous_dry", "field": field, "seconds": now - since,
                                   "reason": "device reports DRY; not calibrated moisture"})
        dry_active = [f for f, start in dry_since.items() if now - start >= rule.get("dry_seconds", 60)]
        for index, event in enumerate(events):
            event.update({"event_id": f"{device}:{boot}:{seq}:{index}", "source_seq": seq})
        state = {"device_id": device, "source_boot_id": boot, "source_seq": seq,
                 "pc_time": pc_time, "pc_received_at": sample["pc_received_at"], "received_at": now,
                 "analyzed_at": now, "expires_at": min(now, pc_time) + rule.get("timeout_seconds", 15),
                 "rule_version": RULE_VERSION, "quality": "issues" if issues else "valid" if valid else "unknown",
                 "issues": issues, "valid": valid, "events": events, "dry_since": dry_since,
                 "dry_active": dry_active,
                 "interval_seconds": now - previous["received_at"] if previous else None,
                 "sample_count": (previous.get("sample_count", 0) if previous else 0) + 1,
                 "transition_count": (previous.get("transition_count", 0) if previous else 0) + sum(e["kind"] == "state_changed" for e in events)}
        try:
            with self.db:
                self._prune(now)
                self.db.execute("INSERT INTO samples(received,body,result) VALUES(?,?,?)",
                                (now, json.dumps(sample, allow_nan=False), json.dumps(state)))
                self.db.execute("INSERT OR REPLACE INTO devices VALUES(?,?)", (device, json.dumps(state)))
            self.states[device] = state
            self.last_error = None
        except (sqlite3.Error, OSError) as exc:
            self.last_error = type(exc).__name__
            raise
        return {"ok": True, "accepted": True, "result": state}

    def status(self, now=None):
        now = time.time() if now is None else now
        devices = []
        for device, rule in self.config.items():
            state = dict(self.states.get(device, {"device_id": device, "quality": "unknown"}))
            state["data_status"] = "never_received" if "received_at" not in state else "timeout" if now > state["expires_at"] else "current"
            if state["data_status"] != "current":
                state["quality"] = "unknown"
            devices.append(state)
        return {"ok": True, "node_id": self.node_id, "boot_id": self.boot_id, "time": now,
                "last_error": self.last_error, "devices": devices,
                "record_count": self.db.execute("SELECT count(*) FROM samples").fetchone()[0],
                "max_records": self.max_rows, "retention_seconds": self.retention}

    def history(self, limit=50):
        return [json.loads(row[0]) for row in self.db.execute("SELECT result FROM samples ORDER BY id DESC LIMIT ?", (min(100, max(1, limit)),))]

    def tick(self, now=None):
        """Persist one interruption event per gap, even with no incoming PC traffic."""
        now = time.time() if now is None else now
        try:
            with self.db:
                self._prune(now)
            for device, old in list(self.states.items()):
                if now <= old["expires_at"] or old.get("timed_out"):
                    continue
                state = dict(old, timed_out=True, quality="unknown", dry_active=[], dry_since={})
                state["events"] = [{"kind": "data_timeout", "event_id": f"{device}:{old['source_boot_id']}:{old['source_seq']}:timeout",
                                    "source_seq": old["source_seq"], "detected_at": now}]
                with self.db:
                    self._prune(now)
                    self.db.execute("INSERT INTO samples(received,body,result) VALUES(?,?,?)", (now, "null", json.dumps(state)))
                    self.db.execute("INSERT OR REPLACE INTO devices VALUES(?,?)", (device, json.dumps(state)))
                self.states[device] = state
        except (sqlite3.Error, OSError) as exc:
            self.last_error = type(exc).__name__


def make_handler(store, token):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)

        def log_message(self, *args):
            pass

        def respond(self, code, body):
            raw = json.dumps(body, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.respond(401, {"ok": False, "error": "unauthorized"})
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            try:
                if self.path == "/v1/status":
                    self.respond(200, store.status())
                elif self.path == "/v1/history":
                    self.respond(200, {"ok": True, "records": store.history()})
                else:
                    self.respond(404, {"ok": False})
            except sqlite3.Error:
                self.respond(503, {"ok": False, "error": "storage unavailable"})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path != "/v1/samples":
                self.respond(404, {"ok": False})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 8192 or self.headers.get("Transfer-Encoding"):
                    raise ValueError("body must be 1..8192 bytes with Content-Length")
                sample = json.loads(self.rfile.read(size))
                result = store.accept(sample)
                self.respond(200, result)
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                self.respond(400, {"ok": False, "error": str(exc)})
            except (sqlite3.Error, OSError):
                self.respond(503, {"ok": False, "error": "storage or transport unavailable"})
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", default="local/sidecar.db")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    token = os.environ.get("SIDECAR_TOKEN", "")
    if len(token) < 16:
        parser.error("set SIDECAR_TOKEN to a shared random secret of at least 16 characters")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    store = Store(args.db, config)
    server = HTTPServer((args.host, args.port), make_handler(store, token))
    server.timeout = 1
    print(f"Sidecar listening on {args.host}:{args.port}; advisory only", flush=True)
    try:
        while True:
            server.handle_request()
            # Retention applies even when the PC is offline.
            store.tick()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.db.close()


if __name__ == "__main__":
    main()
