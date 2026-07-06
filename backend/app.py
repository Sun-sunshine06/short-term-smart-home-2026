from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

try:
    from vision.face_adapter import verify_face
    from vision.yolo_adapter import detect_image
except ImportError:
    from backend.vision.face_adapter import verify_face
    from backend.vision.yolo_adapter import detect_image


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "smart_home.db"


ORANGE_PI_AIPRO_20T_PROFILE = {
    "name": "Orange Pi AIpro 20T",
    "model": "Orange Pi AIpro (20T)",
    "role": "hardware_edge_node",
    "ai_compute": "20 TOPS",
    "cpu": "4-core 64-bit processor + AI processor",
    "memory": "12GB/24GB LPDDR4X",
    "networking": "dual 2.5G Ethernet, Wi-Fi, Bluetooth",
    "storage": "eMMC module, SATA/NVMe SSD, SPI flash, microSD",
    "camera": "2 x MIPI CSI 4-lane camera interfaces",
    "expansion": "40-pin header supporting GPIO, UART, I2C, SPI, I2S, PWM",
    "supported_os": "Ubuntu, openEuler",
    "source_url": "https://www.orangepi.org/html/hardWare/computerAndMicrocontrollers/details/Orange-Pi-AIpro%2820t%29.html",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db_path() -> Path:
    return Path(os.environ.get("SMART_HOME_DB", DEFAULT_DB_PATH))


def connect_db() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("door_open", "window_open", "fan_on", "lock_open", "camera_online", "hardware_online", "matched"):
        if key in result and result[key] is not None:
            result[key] = bool(result[key])
    for key in ("labels", "detections", "raw_result_json", "spec_json", "bbox", "landmarks_5"):
        if key in result and isinstance(result[key], str):
            try:
                result[key] = json.loads(result[key])
            except json.JSONDecodeError:
                pass
    return result


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with connect_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hardware_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                model TEXT NOT NULL,
                role TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                source_url TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS device_states (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                temperature REAL,
                door_open INTEGER NOT NULL DEFAULT 0,
                window_open INTEGER NOT NULL DEFAULT 0,
                light_level INTEGER NOT NULL DEFAULT 0,
                fan_on INTEGER NOT NULL DEFAULT 0,
                lock_open INTEGER NOT NULL DEFAULT 0,
                camera_online INTEGER NOT NULL DEFAULT 0,
                hardware_online INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sensor_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temperature REAL,
                door_open INTEGER,
                window_open INTEGER,
                light_level INTEGER,
                fan_on INTEGER,
                lock_open INTEGER,
                source TEXT NOT NULL DEFAULT 'orange_pi_aipro_20t',
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS device_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL,
                action TEXT NOT NULL,
                value TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                sent_at TEXT,
                ack_at TEXT
            );

            CREATE TABLE IF NOT EXISTS detection_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT,
                result_image_path TEXT,
                model_name TEXT,
                model_weights TEXT,
                labels TEXT NOT NULL DEFAULT '[]',
                confidence REAL,
                detections TEXT NOT NULL DEFAULT '[]',
                raw_result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS authorized_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                image_path TEXT,
                encoding_path TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT,
                result TEXT NOT NULL,
                matched INTEGER,
                score REAL,
                threshold REAL,
                bbox TEXT,
                landmarks_5 TEXT,
                image_path TEXT,
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )
        ensure_column(conn, "detection_records", "model_name", "TEXT")
        ensure_column(conn, "detection_records", "model_weights", "TEXT")
        ensure_column(conn, "access_logs", "matched", "INTEGER")
        ensure_column(conn, "access_logs", "score", "REAL")
        ensure_column(conn, "access_logs", "threshold", "REAL")
        ensure_column(conn, "access_logs", "bbox", "TEXT")
        ensure_column(conn, "access_logs", "landmarks_5", "TEXT")

        existing_profile = conn.execute("SELECT id FROM hardware_profiles LIMIT 1").fetchone()
        if existing_profile is None:
            conn.execute(
                """
                INSERT INTO hardware_profiles
                    (name, model, role, spec_json, source_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ORANGE_PI_AIPRO_20T_PROFILE["name"],
                    ORANGE_PI_AIPRO_20T_PROFILE["model"],
                    ORANGE_PI_AIPRO_20T_PROFILE["role"],
                    json.dumps(ORANGE_PI_AIPRO_20T_PROFILE, ensure_ascii=False),
                    ORANGE_PI_AIPRO_20T_PROFILE["source_url"],
                    utc_now(),
                ),
            )

        existing_state = conn.execute("SELECT id FROM device_states WHERE id = 1").fetchone()
        if existing_state is None:
            conn.execute(
                """
                INSERT INTO device_states
                    (id, temperature, door_open, window_open, light_level,
                     fan_on, lock_open, camera_online, hardware_online, updated_at)
                VALUES (1, 26.0, 0, 0, 50, 0, 0, 0, 0, ?)
                """,
                (utc_now(),),
            )
        conn.commit()


def parse_bool(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(bool(value))
    if isinstance(value, str):
        return int(value.strip().lower() in {"1", "true", "yes", "on", "open"})
    return None


def parse_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def create_app() -> Flask:
    app = Flask(__name__)
    init_db()

    @app.get("/")
    def index():
        return jsonify(
            {
                "service": "smart-home-backend",
                "branch": "test",
                "hardware_profile": "/api/hardware/profile",
                "status": "/api/status",
                "health": "/api/health",
            }
        )

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "time": utc_now(), "database": str(get_db_path())})

    @app.get("/api/hardware/profile")
    def hardware_profile():
        with connect_db() as conn:
            row = conn.execute("SELECT * FROM hardware_profiles ORDER BY id LIMIT 1").fetchone()
        return jsonify(row_to_dict(row))

    @app.get("/api/status")
    def status():
        with connect_db() as conn:
            row = conn.execute("SELECT * FROM device_states WHERE id = 1").fetchone()
        return jsonify(row_to_dict(row))

    @app.post("/api/sensor/update")
    def sensor_update():
        payload = request.get_json(silent=True) or {}
        now = utc_now()

        temperature = payload.get("temperature")
        light_level = parse_int(payload.get("light_level"), 0)
        door_open = parse_bool(payload.get("door_open"))
        window_open = parse_bool(payload.get("window_open"))
        fan_on = parse_bool(payload.get("fan_on"))
        lock_open = parse_bool(payload.get("lock_open"))

        with connect_db() as conn:
            current = conn.execute("SELECT * FROM device_states WHERE id = 1").fetchone()
            current_dict = row_to_dict(current) or {}
            next_values = {
                "temperature": temperature if temperature is not None else current_dict.get("temperature"),
                "door_open": door_open if door_open is not None else int(bool(current_dict.get("door_open"))),
                "window_open": window_open if window_open is not None else int(bool(current_dict.get("window_open"))),
                "light_level": light_level if light_level is not None else current_dict.get("light_level", 0),
                "fan_on": fan_on if fan_on is not None else int(bool(current_dict.get("fan_on"))),
                "lock_open": lock_open if lock_open is not None else int(bool(current_dict.get("lock_open"))),
            }

            conn.execute(
                """
                UPDATE device_states
                SET temperature = ?, door_open = ?, window_open = ?, light_level = ?,
                    fan_on = ?, lock_open = ?, hardware_online = 1, updated_at = ?
                WHERE id = 1
                """,
                (
                    next_values["temperature"],
                    next_values["door_open"],
                    next_values["window_open"],
                    next_values["light_level"],
                    next_values["fan_on"],
                    next_values["lock_open"],
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO sensor_records
                    (temperature, door_open, window_open, light_level, fan_on,
                     lock_open, source, raw_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    next_values["temperature"],
                    next_values["door_open"],
                    next_values["window_open"],
                    next_values["light_level"],
                    next_values["fan_on"],
                    next_values["lock_open"],
                    payload.get("source", "orange_pi_aipro_20t"),
                    json.dumps(payload, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM device_states WHERE id = 1").fetchone()
        return jsonify({"ok": True, "status": row_to_dict(updated)})

    @app.post("/api/device/control")
    def device_control():
        payload = request.get_json(silent=True) or {}
        target = str(payload.get("target", "")).strip()
        action = str(payload.get("action", "")).strip()
        value = payload.get("value")
        if not target or not action:
            return jsonify({"ok": False, "error": "target and action are required"}), 400

        with connect_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO device_commands (target, action, value, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (
                    target,
                    action,
                    json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else None if value is None else str(value),
                    utc_now(),
                ),
            )
            conn.commit()
        return jsonify({"ok": True, "command_id": cursor.lastrowid})

    @app.get("/api/device/commands")
    def device_commands():
        limit = min(parse_int(request.args.get("limit"), 20) or 20, 100)
        consume = request.args.get("consume", "true").lower() != "false"
        now = utc_now()
        with connect_db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM device_commands
                WHERE status = 'pending'
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            if consume and rows:
                conn.executemany(
                    "UPDATE device_commands SET status = 'sent', sent_at = ? WHERE id = ?",
                    [(now, row["id"]) for row in rows],
                )
                conn.commit()
        commands = []
        for row in rows:
            item = row_to_dict(row) or {}
            if isinstance(item.get("value"), str):
                try:
                    item["value"] = json.loads(item["value"])
                except json.JSONDecodeError:
                    pass
            commands.append(item)
        return jsonify({"ok": True, "commands": commands})

    @app.post("/api/device/commands/<int:command_id>/ack")
    def command_ack(command_id: int):
        payload = request.get_json(silent=True) or {}
        status = payload.get("status", "done")
        with connect_db() as conn:
            conn.execute(
                "UPDATE device_commands SET status = ?, ack_at = ? WHERE id = ?",
                (status, utc_now(), command_id),
            )
            conn.commit()
        return jsonify({"ok": True, "command_id": command_id, "status": status})

    @app.get("/api/history")
    def history():
        limit = min(parse_int(request.args.get("limit"), 50) or 50, 200)
        with connect_db() as conn:
            rows = conn.execute(
                "SELECT * FROM sensor_records ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return jsonify({"ok": True, "records": [row_to_dict(row) for row in rows]})

    @app.post("/api/yolo/detect")
    def yolo_detect():
        payload = request.get_json(silent=True) or {}
        image_path = payload.get("image_path")
        adapter_result: dict[str, Any] = {}

        if image_path and "detections" not in payload:
            try:
                adapter_result = detect_image(str(image_path))
            except Exception as exc:
                return jsonify({"ok": False, "error": str(exc)}), 500

        merged = {**payload, **adapter_result}
        detections = merged.get("detections", [])
        labels = payload.get("labels")
        if labels is None:
            labels = [item.get("label") for item in detections if isinstance(item, dict) and item.get("label")]
        confidence = merged.get("confidence")
        if confidence is None and detections:
            confidences = [item.get("confidence") for item in detections if isinstance(item, dict) and item.get("confidence") is not None]
            confidence = max(confidences) if confidences else None
        model = merged.get("model") if isinstance(merged.get("model"), dict) else {}

        with connect_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO detection_records
                    (image_path, result_image_path, model_name, model_weights, labels, confidence,
                     detections, raw_result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    merged.get("image_path") or image_path,
                    merged.get("result_image_path"),
                    model.get("name"),
                    model.get("weights"),
                    json.dumps(labels or [], ensure_ascii=False),
                    confidence,
                    json.dumps(detections or [], ensure_ascii=False),
                    json.dumps(merged, ensure_ascii=False),
                    utc_now(),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM detection_records WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "record": row_to_dict(row)})

    @app.get("/api/yolo/latest")
    def yolo_latest():
        with connect_db() as conn:
            row = conn.execute("SELECT * FROM detection_records ORDER BY id DESC LIMIT 1").fetchone()
        return jsonify({"ok": True, "record": row_to_dict(row)})

    @app.get("/api/yolo/history")
    def yolo_history():
        limit = min(parse_int(request.args.get("limit"), 50) or 50, 200)
        with connect_db() as conn:
            rows = conn.execute("SELECT * FROM detection_records ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return jsonify({"ok": True, "records": [row_to_dict(row) for row in rows]})

    @app.post("/api/face/access")
    @app.post("/api/face/verify")
    def face_access():
        payload = request.get_json(silent=True) or {}
        image_path = payload.get("image_path")
        adapter_result: dict[str, Any] = {}

        if image_path and "matched" not in payload and "granted" not in payload and "result" not in payload:
            try:
                adapter_result = verify_face(str(image_path))
            except Exception as exc:
                return jsonify({"ok": False, "error": str(exc)}), 500

        merged = {**payload, **adapter_result}
        matched = merged.get("matched")
        if matched is None:
            matched = bool(merged.get("granted"))
        result = merged.get("result") or ("granted" if matched else "denied")
        user_name = merged.get("user_name") or merged.get("name")
        with connect_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO access_logs
                    (user_name, result, matched, score, threshold, bbox,
                     landmarks_5, image_path, raw_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_name,
                    result,
                    int(bool(matched)),
                    merged.get("score"),
                    merged.get("threshold"),
                    json.dumps(merged.get("bbox"), ensure_ascii=False) if merged.get("bbox") is not None else None,
                    json.dumps(merged.get("landmarks_5"), ensure_ascii=False) if merged.get("landmarks_5") is not None else None,
                    image_path,
                    json.dumps(merged, ensure_ascii=False),
                    utc_now(),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM access_logs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "record": row_to_dict(row)})

    @app.get("/api/face/history")
    def face_history():
        limit = min(parse_int(request.args.get("limit"), 50) or 50, 200)
        with connect_db() as conn:
            rows = conn.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return jsonify({"ok": True, "records": [row_to_dict(row) for row in rows]})

    return app


app = create_app()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
        debug=debug,
        use_reloader=False,
    )
