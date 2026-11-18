from __future__ import annotations

import base64
import binascii
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

try:
    from sidecar import SidecarForwarder
except ImportError:
    from backend.sidecar import SidecarForwarder

try:
    from hardware.uno_serial import UnoBridgeError, UnoBridgeUnavailable, UnoCommandRejected, get_uno_bridge
    from vision.face_adapter import verify_face
    from vision.live_camera import register_live_camera
    from vision.yolo_adapter import detect_image
except ImportError:
    from backend.hardware.uno_serial import UnoBridgeError, UnoBridgeUnavailable, UnoCommandRejected, get_uno_bridge
    from backend.vision.face_adapter import verify_face
    from backend.vision.live_camera import register_live_camera
    from backend.vision.yolo_adapter import detect_image


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "smart_home.db"
DEFAULT_CAMERA_UPLOAD_DIR = DATA_DIR / "uploads" / "camera"
DEFAULT_FACE_UPLOAD_DIR = DATA_DIR / "uploads" / "face_enroll"
DEFAULT_FACE_GALLERY_DIR = BASE_DIR.parent / "training" / "face_gallery"


ORANGE_PI_AIPRO_PROFILE = {
    "name": "Orange Pi AIpro",
    "model": "Orange Pi AIpro (Ascend, variant to confirm)",
    "role": "hardware_edge_node",
    "ai_compute": "Depends on assigned Ascend variant, for example 8 TOPS or 20 TOPS",
    "cpu": "4-core 64-bit processor + AI processor",
    "memory": "Depends on assigned variant, for example 8GB/16GB LPDDR4X",
    "networking": "Ethernet / Wi-Fi depending on setup",
    "storage": "microSD, eMMC module, SATA/NVMe SSD depending on variant",
    "camera": "2 x MIPI CSI 4-lane camera interfaces",
    "expansion": "40-pin header supporting GPIO, UART, I2C, SPI, I2S, PWM",
    "supported_os": "Ubuntu, openEuler",
    "source_url": "http://www.orangepi.cn/html/hardWare/computerAndMicrocontrollers/details/Orange-Pi-AIpro.html",
    "note": "Board is expected to be an Ascend-based Orange Pi AIpro. Confirm the exact 8T/20T variant after replacement.",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db_path() -> Path:
    return Path(os.environ.get("SMART_HOME_DB", DEFAULT_DB_PATH))


def get_camera_upload_dir() -> Path:
    return Path(os.environ.get("CAMERA_UPLOAD_DIR", DEFAULT_CAMERA_UPLOAD_DIR))


def get_face_upload_dir() -> Path:
    return Path(os.environ.get("FACE_UPLOAD_DIR", DEFAULT_FACE_UPLOAD_DIR))


def get_face_gallery_dir() -> Path:
    return Path(os.environ.get("FACE_GALLERY_DIR", DEFAULT_FACE_GALLERY_DIR))


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
    for key in (
        "door_open",
        "window_open",
        "fan_on",
        "lock_open",
        "camera_online",
        "hardware_online",
        "matched",
        "active",
        "copied",
    ):
        if key in result and result[key] is not None:
            result[key] = bool(result[key])
    for key in (
        "labels",
        "detections",
        "raw_result_json",
        "raw_json",
        "spec_json",
        "ip_addresses",
        "metrics_json",
        "latest_metrics_json",
        "bbox",
        "landmarks_5",
        "best_match",
        "second_best_identity_match",
        "top_matches",
        "skipped",
    ):
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
                source TEXT NOT NULL DEFAULT 'orange_pi_aipro',
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

            CREATE TABLE IF NOT EXISTS edge_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL UNIQUE,
                name TEXT,
                role TEXT NOT NULL DEFAULT 'orange_pi_edge',
                hostname TEXT,
                os_name TEXT,
                os_version TEXT,
                kernel TEXT,
                arch TEXT,
                python_version TEXT,
                client_version TEXT,
                ip_addresses TEXT NOT NULL DEFAULT '[]',
                raw_json TEXT NOT NULL DEFAULT '{}',
                last_seen_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS edge_heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'online',
                ip_addresses TEXT NOT NULL DEFAULT '[]',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(node_id) REFERENCES edge_nodes(node_id)
            );

            CREATE TABLE IF NOT EXISTS detection_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT,
                result_image_path TEXT,
                model_name TEXT,
                model_weights TEXT,
                source TEXT,
                node_id TEXT,
                inference_ms REAL,
                labels TEXT NOT NULL DEFAULT '[]',
                confidence REAL,
                detections TEXT NOT NULL DEFAULT '[]',
                raw_result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS authorized_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity TEXT,
                name TEXT NOT NULL,
                image_path TEXT,
                encoding_path TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS face_gallery_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                original_image_path TEXT,
                copied INTEGER NOT NULL DEFAULT 0,
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES authorized_users(id)
            );

            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_name TEXT,
                result TEXT NOT NULL,
                matched INTEGER,
                score REAL,
                threshold REAL,
                min_margin REAL,
                score_margin REAL,
                det_score REAL,
                engine TEXT,
                model_pack TEXT,
                bbox TEXT,
                landmarks_5 TEXT,
                best_match TEXT,
                second_best_identity_match TEXT,
                top_matches TEXT,
                skipped TEXT,
                source_detection_id INTEGER,
                image_path TEXT,
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )
        ensure_column(conn, "detection_records", "model_name", "TEXT")
        ensure_column(conn, "detection_records", "model_weights", "TEXT")
        ensure_column(conn, "detection_records", "source", "TEXT")
        ensure_column(conn, "detection_records", "node_id", "TEXT")
        ensure_column(conn, "detection_records", "inference_ms", "REAL")
        ensure_column(conn, "authorized_users", "identity", "TEXT")
        ensure_column(conn, "authorized_users", "active", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "authorized_users", "updated_at", "TEXT")
        ensure_column(conn, "access_logs", "matched", "INTEGER")
        ensure_column(conn, "access_logs", "user_id", "TEXT")
        ensure_column(conn, "access_logs", "score", "REAL")
        ensure_column(conn, "access_logs", "threshold", "REAL")
        ensure_column(conn, "access_logs", "min_margin", "REAL")
        ensure_column(conn, "access_logs", "score_margin", "REAL")
        ensure_column(conn, "access_logs", "det_score", "REAL")
        ensure_column(conn, "access_logs", "engine", "TEXT")
        ensure_column(conn, "access_logs", "model_pack", "TEXT")
        ensure_column(conn, "access_logs", "bbox", "TEXT")
        ensure_column(conn, "access_logs", "landmarks_5", "TEXT")
        ensure_column(conn, "access_logs", "best_match", "TEXT")
        ensure_column(conn, "access_logs", "second_best_identity_match", "TEXT")
        ensure_column(conn, "access_logs", "top_matches", "TEXT")
        ensure_column(conn, "access_logs", "skipped", "TEXT")
        ensure_column(conn, "access_logs", "source_detection_id", "INTEGER")
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_sensor_records_created_at
                ON sensor_records(created_at);
            CREATE INDEX IF NOT EXISTS idx_device_commands_status_id
                ON device_commands(status, id);
            CREATE INDEX IF NOT EXISTS idx_edge_heartbeats_node_id_id
                ON edge_heartbeats(node_id, id);
            CREATE INDEX IF NOT EXISTS idx_edge_heartbeats_created_at
                ON edge_heartbeats(created_at);
            CREATE INDEX IF NOT EXISTS idx_detection_records_created_at
                ON detection_records(created_at);
            CREATE INDEX IF NOT EXISTS idx_detection_records_source_node
                ON detection_records(source, node_id);
            CREATE INDEX IF NOT EXISTS idx_access_logs_created_at
                ON access_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_access_logs_source_detection_id
                ON access_logs(source_detection_id);
            CREATE INDEX IF NOT EXISTS idx_authorized_users_identity
                ON authorized_users(identity);
            CREATE INDEX IF NOT EXISTS idx_face_gallery_images_user_id_id
                ON face_gallery_images(user_id, id);
            """
        )

        existing_profile = conn.execute("SELECT * FROM hardware_profiles LIMIT 1").fetchone()
        if existing_profile is None:
            conn.execute(
                """
                INSERT INTO hardware_profiles
                    (name, model, role, spec_json, source_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ORANGE_PI_AIPRO_PROFILE["name"],
                    ORANGE_PI_AIPRO_PROFILE["model"],
                    ORANGE_PI_AIPRO_PROFILE["role"],
                    json.dumps(ORANGE_PI_AIPRO_PROFILE, ensure_ascii=False),
                    ORANGE_PI_AIPRO_PROFILE["source_url"],
                    utc_now(),
                ),
            )
        elif "20T" in (existing_profile["model"] or existing_profile["name"] or ""):
            conn.execute(
                """
                UPDATE hardware_profiles
                SET name = ?, model = ?, role = ?, spec_json = ?, source_url = ?
                WHERE id = ?
                """,
                (
                    ORANGE_PI_AIPRO_PROFILE["name"],
                    ORANGE_PI_AIPRO_PROFILE["model"],
                    ORANGE_PI_AIPRO_PROFILE["role"],
                    json.dumps(ORANGE_PI_AIPRO_PROFILE, ensure_ascii=False),
                    ORANGE_PI_AIPRO_PROFILE["source_url"],
                    existing_profile["id"],
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


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item for item in value.replace(",", " ").split() if item]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def json_text(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, ensure_ascii=False)


ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def path_for_response(path: Path) -> str:
    try:
        return path.relative_to(BASE_DIR.parent).as_posix()
    except ValueError:
        return str(path)


def resolve_image_path_for_response(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = BASE_DIR.parent / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None

    allowed_roots = [
        BASE_DIR.parent.resolve(),
        get_camera_upload_dir().resolve(),
        (BASE_DIR / "static" / "results").resolve(),
    ]
    if resolved.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        return None
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        return None
    return resolved


def camera_upload_filename(original_name: str | None) -> str:
    fallback = "camera.jpg"
    safe_name = secure_filename(original_name or fallback) or fallback
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        suffix = ".jpg"
    stem = Path(safe_name).stem or "camera"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:8]}_{stem}{suffix}"


def face_upload_filename(original_name: str | None) -> str:
    fallback = "face.jpg"
    safe_name = secure_filename(original_name or fallback) or fallback
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        suffix = ".jpg"
    stem = Path(safe_name).stem or "face"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:8]}_{stem}{suffix}"


def save_face_upload_file() -> str | None:
    image_file = request.files.get("image") or request.files.get("face_image")
    if image_file is None or not image_file.filename:
        return None
    suffix = Path(image_file.filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise ValueError("unsupported image file type")
    upload_dir = get_face_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / face_upload_filename(image_file.filename)
    image_file.save(target)
    return str(target)


def save_camera_upload() -> tuple[str | None, dict[str, Any], str | None]:
    upload_dir = get_camera_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    if request.files.get("image") is not None:
        image_file = request.files["image"]
        if not image_file.filename:
            return None, {}, "image filename is required"
        target = upload_dir / camera_upload_filename(image_file.filename)
        image_file.save(target)
        payload = {
            "source": request.form.get("source", "orange_pi_camera"),
            "node_id": request.form.get("node_id"),
            "filename": image_file.filename,
            "upload_mode": "multipart",
        }
        return path_for_response(target), payload, None

    payload = request.get_json(silent=True) or {}
    if payload.get("image_path"):
        return str(payload["image_path"]), payload, None

    encoded = payload.get("image_base64")
    if not encoded:
        return None, payload, "image file, image_path, or image_base64 is required"
    if "," in encoded and encoded.strip().startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None, payload, "image_base64 is invalid"

    target = upload_dir / camera_upload_filename(str(payload.get("filename") or "camera.jpg"))
    target.write_bytes(image_bytes)
    payload = {**payload, "upload_mode": "base64"}
    return path_for_response(target), payload, None


def create_yolo_record(payload: dict[str, Any]) -> sqlite3.Row:
    image_path = payload.get("image_path")
    adapter_result: dict[str, Any] = {}
    measured_inference_ms: float | None = None

    if image_path and "detections" not in payload:
        started_at = time.perf_counter()
        adapter_result = detect_image(str(image_path))
        measured_inference_ms = round((time.perf_counter() - started_at) * 1000, 2)

    merged = {**payload, **adapter_result}
    if merged.get("inference_ms") is None and measured_inference_ms is not None:
        merged["inference_ms"] = measured_inference_ms
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
                (image_path, result_image_path, model_name, model_weights, source, node_id,
                 inference_ms, labels, confidence, detections, raw_result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                merged.get("image_path") or image_path,
                merged.get("result_image_path"),
                model.get("name"),
                model.get("weights"),
                merged.get("source"),
                merged.get("node_id"),
                merged.get("inference_ms"),
                json.dumps(labels or [], ensure_ascii=False),
                confidence,
                json.dumps(detections or [], ensure_ascii=False),
                json.dumps(merged, ensure_ascii=False),
                utc_now(),
            ),
        )
        conn.commit()
        return conn.execute("SELECT * FROM detection_records WHERE id = ?", (cursor.lastrowid,)).fetchone()


def latest_yolo_record() -> sqlite3.Row | None:
    with connect_db() as conn:
        return conn.execute("SELECT * FROM detection_records ORDER BY id DESC LIMIT 1").fetchone()


def create_face_record(payload: dict[str, Any]) -> sqlite3.Row:
    image_path = payload.get("image_path")
    adapter_result: dict[str, Any] = {}

    if image_path and "matched" not in payload and "granted" not in payload and "result" not in payload:
        adapter_result = verify_face(str(image_path))

    merged = {**payload, **adapter_result}
    matched = merged.get("matched")
    if matched is None:
        matched = bool(merged.get("granted"))
    result = merged.get("result") or ("granted" if matched else "denied")
    user_id = merged.get("user_id")
    user_name = merged.get("user_name") or merged.get("name")

    with connect_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO access_logs
                (user_id, user_name, result, matched, score, threshold,
                 min_margin, score_margin, det_score, engine, model_pack,
                 bbox, landmarks_5, best_match, second_best_identity_match,
                 top_matches, skipped, source_detection_id, image_path, raw_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(user_id) if user_id is not None else None,
                user_name,
                result,
                int(bool(matched)),
                merged.get("score"),
                merged.get("threshold"),
                merged.get("min_margin"),
                merged.get("score_margin"),
                merged.get("det_score"),
                merged.get("engine"),
                merged.get("model_pack"),
                json.dumps(merged.get("bbox"), ensure_ascii=False) if merged.get("bbox") is not None else None,
                json.dumps(merged.get("landmarks_5"), ensure_ascii=False) if merged.get("landmarks_5") is not None else None,
                json.dumps(merged.get("best_match"), ensure_ascii=False) if merged.get("best_match") is not None else None,
                json.dumps(merged.get("second_best_identity_match"), ensure_ascii=False)
                if merged.get("second_best_identity_match") is not None
                else None,
                json.dumps(merged.get("top_matches"), ensure_ascii=False) if merged.get("top_matches") is not None else None,
                json.dumps(merged.get("skipped"), ensure_ascii=False) if merged.get("skipped") is not None else None,
                merged.get("source_detection_id"),
                image_path,
                json.dumps(merged, ensure_ascii=False),
                utc_now(),
            ),
        )
        conn.commit()
        return conn.execute("SELECT * FROM access_logs WHERE id = ?", (cursor.lastrowid,)).fetchone()


def sync_lock_state_from_face(face_record: sqlite3.Row | None) -> sqlite3.Row | None:
    if face_record is None:
        return None

    lock_open = int(bool(face_record["matched"]))
    with connect_db() as conn:
        conn.execute(
            """
            UPDATE device_states
            SET lock_open = ?, hardware_online = 1, updated_at = ?
            WHERE id = 1
            """,
            (lock_open, utc_now()),
        )
        conn.commit()
        return conn.execute("SELECT * FROM device_states WHERE id = 1").fetchone()


def camera_face_verify_enabled(payload: dict[str, Any]) -> bool:
    raw_value = payload.get("face_verify")
    if raw_value is None:
        raw_value = os.environ.get("CAMERA_UPLOAD_FACE_VERIFY", "0")
    parsed = parse_bool(raw_value)
    return parsed != 0


def make_identity(value: str) -> str:
    identity = re.sub(r"[^0-9A-Za-z_\-]+", "_", value.strip()).strip("_").lower()
    return identity or "user"


def unique_identity(conn: sqlite3.Connection, preferred: str) -> str:
    base = make_identity(preferred)
    identity = base
    index = 2
    while conn.execute("SELECT id FROM authorized_users WHERE identity = ?", (identity,)).fetchone():
        identity = f"{base}_{index}"
        index += 1
    return identity


def add_gallery_image(
    conn: sqlite3.Connection,
    user: sqlite3.Row,
    image_path: str,
    raw_payload: dict[str, Any],
    copy_to_gallery: bool = True,
) -> sqlite3.Row:
    source_path = Path(image_path)
    final_path = source_path
    copied = 0
    if copy_to_gallery and source_path.exists():
        identity = user["identity"] or f"user_{user['id']:03d}"
        target_dir = get_face_gallery_dir() / identity
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / source_path.name
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(source_path, target_path)
        final_path = target_path
        copied = 1

    cursor = conn.execute(
        """
        INSERT INTO face_gallery_images
            (user_id, image_path, original_image_path, copied, raw_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            str(final_path),
            image_path,
            copied,
            json.dumps(raw_payload, ensure_ascii=False),
            utc_now(),
        ),
    )
    conn.execute(
        """
        UPDATE authorized_users
        SET image_path = COALESCE(image_path, ?), updated_at = ?
        WHERE id = ?
        """,
        (str(final_path), utc_now(), user["id"]),
    )
    return conn.execute("SELECT * FROM face_gallery_images WHERE id = ?", (cursor.lastrowid,)).fetchone()


def create_app(uno_bridge_override: Any | None = None) -> Flask:
    app = Flask(__name__)
    def authorized_references():
        with closing(connect_db()) as conn:
            rows = conn.execute("""
                SELECT u.identity, u.name, i.image_path
                FROM authorized_users u JOIN face_gallery_images i ON i.user_id = u.id
                WHERE u.active = 1
            """).fetchall()
        return [(r["identity"], r["name"], Path(r["image_path"])) for r in rows]

    init_db()
    sidecar = SidecarForwarder.from_env()
    app.extensions["sidecar"] = sidecar
    sidecar.start()

    @app.get("/api/sidecar/status")
    def sidecar_status():
        # Snapshot only: never wait for the edge node on a browser request.
        return jsonify(sidecar.snapshot())
    uno_bridge = uno_bridge_override or get_uno_bridge()
    app.extensions["uno_serial"] = uno_bridge

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/next/")
    @app.get("/next/<path:asset>")
    def astryx_home(asset="index.html"):
        build_dir = BASE_DIR.parent / "frontend" / "dist"
        if not (build_dir / "index.html").is_file():
            return jsonify({"error": "Frontend preview is not built. Run npm ci and npm run build in frontend/."}), 503
        return send_from_directory(build_dir, asset)

    @app.get("/api")
    def index():
        return jsonify(
            {
                "service": "smart-home-backend",
                "branch": os.environ.get("APP_BRANCH", "feature/web-gui"),
                "hardware_profile": "/api/hardware/profile",
                "status": "/api/status",
                "health": "/api/health",
                "edge_nodes": "/api/edge/nodes",
                "edge_heartbeats": "/api/edge/heartbeats",
                "camera_upload": "/api/camera/upload",
                "yolo_detect": "/api/yolo/detect",
                "face_latest": "/api/face/latest",
                "face_verify": "/api/face/verify",
                "face_verify_latest": "/api/face/verify-latest",
            }
        )

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "time": utc_now(),
                "database": str(get_db_path()),
                "uno": uno_bridge.snapshot(),
            }
        )

    @app.get("/api/hardware/uno")
    def uno_status():
        return jsonify({"ok": True, "uno": uno_bridge.snapshot()})

    @app.get("/api/files/image")
    def image_file():
        image_path = resolve_image_path_for_response(request.args.get("path"))
        if image_path is None:
            return jsonify({"ok": False, "error": "image not found"}), 404
        return send_file(image_path)

    @app.get("/api/hardware/profile")
    def hardware_profile():
        with connect_db() as conn:
            row = conn.execute("SELECT * FROM hardware_profiles ORDER BY id LIMIT 1").fetchone()
        return jsonify(row_to_dict(row))

    @app.get("/api/status")
    def status():
        with connect_db() as conn:
            row = conn.execute("SELECT * FROM device_states WHERE id = 1").fetchone()
            commands = conn.execute("""
                SELECT * FROM device_commands
                WHERE id IN (
                    SELECT MAX(id) FROM device_commands
                    WHERE status = 'link_sent_no_ack'
                    GROUP BY lower(target)
                )
                ORDER BY id DESC
            """).fetchall()
        result = row_to_dict(row)
        expected = {}
        fields = {"door": "door_open", "fan": "fan_on", "light": "light_level"}
        now = datetime.now(timezone.utc)
        for command in commands:
            target = command["target"].lower()
            field = fields.get(target)
            if field is None or field in expected:
                continue
            action = command["action"].lower()
            value = (35 if target == "light" else True) if action in {"on", "open"} else 0
            closes_at = None
            if target == "door" and action == "open":
                closes_at = datetime.fromisoformat(command["ack_at"]) + timedelta(seconds=4)
                value = now < closes_at
            expected[field] = {
                "value": value, "confirmed": False,
                "source": "command_estimate", "command_id": command["id"],
                "auto_close_at": closes_at.isoformat() if closes_at else None,
            }
        result["expected_states"] = expected
        result["uno"] = uno_bridge.snapshot()
        return jsonify(result)

    @app.post("/api/sensor/update")
    def sensor_update():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "status": ingest_sensor(payload, datetime.now(timezone.utc).isoformat())})

    def ingest_sensor(payload, pc_received_at):
        now = utc_now()

        temperature = payload.get("temperature")
        light_level = parse_int(payload.get("light_level"), None)
        door_open = parse_bool(payload.get("door_open"))
        window_open = parse_bool(payload.get("window_open"))
        fan_on = parse_bool(payload.get("fan_on"))
        lock_open = parse_bool(payload.get("lock_open"))
        camera_online = parse_bool(payload.get("camera_online"))

        with closing(connect_db()) as conn, conn:
            current = conn.execute("SELECT * FROM device_states WHERE id = 1").fetchone()
            current_dict = row_to_dict(current) or {}
            next_values = {
                "temperature": temperature if temperature is not None else current_dict.get("temperature"),
                "door_open": door_open if door_open is not None else int(bool(current_dict.get("door_open"))),
                "window_open": window_open if window_open is not None else int(bool(current_dict.get("window_open"))),
                "light_level": light_level if light_level is not None else current_dict.get("light_level", 0),
                "fan_on": fan_on if fan_on is not None else int(bool(current_dict.get("fan_on"))),
                "lock_open": lock_open if lock_open is not None else int(bool(current_dict.get("lock_open"))),
                "camera_online": camera_online
                if camera_online is not None
                else int(bool(current_dict.get("camera_online"))),
            }

            conn.execute(
                """
                UPDATE device_states
                SET temperature = ?, door_open = ?, window_open = ?, light_level = ?,
                    fan_on = ?, lock_open = ?, camera_online = ?, hardware_online = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    next_values["temperature"],
                    next_values["door_open"],
                    next_values["window_open"],
                    next_values["light_level"],
                    next_values["fan_on"],
                    next_values["lock_open"],
                    next_values["camera_online"],
                    int(bool(current_dict.get("hardware_online")))
                    if payload.get("source") == "uno_usb_asr_d3_v1" else 1,
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
                    payload.get("source", "orange_pi_aipro"),
                    json.dumps(payload, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM device_states WHERE id = 1").fetchone()
        try:
            sidecar.submit(payload, pc_received_at)
        except Exception:
            app.logger.exception("Sidecar enqueue failed; primary sensor update was saved")
        return row_to_dict(updated)

    @app.post("/api/device/control")
    def device_control():
        payload = request.get_json(silent=True) or {}
        return dispatch_device_control(payload)

    def dispatch_device_control(payload):
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
            command_id = cursor.lastrowid

        uno_commands = {
            ("light", "on"): ("LO", "light_level", 35),
            ("light", "off"): ("LC", "light_level", 0),
            ("fan", "on"): ("FO", "fan_on", 1),
            ("fan", "off"): ("FC", "fan_on", 0),
            ("door", "open"): ("DO", "door_open", 1),
            ("door", "close"): ("DC", "door_open", 0),
        }
        uno_mapping = uno_commands.get((target.lower(), action.lower()))
        if uno_mapping is None:
            return jsonify({"ok": True, "command_id": command_id, "status": "pending"})
        uno_command, state_field, commanded_value = uno_mapping

        sent_at = utc_now()
        try:
            delivery = uno_bridge.send_command(uno_command)
        except (UnoBridgeUnavailable, UnoCommandRejected, UnoBridgeError) as exc:
            with connect_db() as conn:
                conn.execute(
                    "UPDATE device_commands SET status = 'failed', sent_at = ?, ack_at = ? WHERE id = ?",
                    (sent_at, utc_now(), command_id),
                )
                conn.commit()
            return (
                jsonify(
                    {
                        "ok": False,
                        "command_id": command_id,
                        "status": "failed",
                        "error": str(exc),
                        "uno": uno_bridge.snapshot(),
                    }
                ),
                503,
            )

        with connect_db() as conn:
            conn.execute(
                "UPDATE device_commands SET status = ?, sent_at = ?, ack_at = ? WHERE id = ?",
                (delivery.stage, sent_at, datetime.now(timezone.utc).isoformat(), command_id),
            )
            conn.commit()

        message = "命令已发往旧板（旧板无返回线）" if delivery.stage == "link_sent_no_ack" else "新板已接收命令"
        return jsonify(
            {
                "ok": True,
                "command_id": command_id,
                "status": delivery.stage,
                "message": message,
                "delivery": delivery.to_dict(),
                "uno": uno_bridge.snapshot(),
            }
        )

    def open_for_live_face(result):
        response = app.make_response(dispatch_device_control({
            "target": "door", "action": "open", "value": {"source": "live_face"}
        })).get_json()
        create_face_record({
            "matched": True, "user_id": result["identity"], "user_name": result["name"],
            "score": result["score"], "engine": "insightface", "trigger": "live_face",
            "command_id": response["command_id"], "delivery_status": response["status"]
        })
        return {"status": response["status"], "command_id": response["command_id"]}

    register_live_camera(app, os.environ.get("CAMERA_USB_PORT"), authorized_references, open_for_live_face)

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

    @app.post("/api/edge/register")
    def edge_register():
        payload = request.get_json(silent=True) or {}
        node_id = str(payload.get("node_id") or payload.get("hostname") or "").strip()
        if not node_id:
            return jsonify({"ok": False, "error": "node_id is required"}), 400

        now = utc_now()
        ip_addresses = normalize_string_list(payload.get("ip_addresses") or payload.get("ips"))
        values = {
            "node_id": node_id,
            "name": str(payload.get("name") or node_id).strip(),
            "role": str(payload.get("role") or "orange_pi_edge").strip(),
            "hostname": payload.get("hostname"),
            "os_name": payload.get("os_name"),
            "os_version": payload.get("os_version"),
            "kernel": payload.get("kernel"),
            "arch": payload.get("arch"),
            "python_version": payload.get("python_version"),
            "client_version": payload.get("client_version"),
            "ip_addresses": json_text(ip_addresses, []),
            "raw_json": json_text(payload, {}),
        }

        with connect_db() as conn:
            existing = conn.execute("SELECT id FROM edge_nodes WHERE node_id = ?", (node_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE edge_nodes
                    SET name = ?, role = ?, hostname = ?, os_name = ?, os_version = ?,
                        kernel = ?, arch = ?, python_version = ?, client_version = ?,
                        ip_addresses = ?, raw_json = ?, last_seen_at = ?, updated_at = ?
                    WHERE node_id = ?
                    """,
                    (
                        values["name"],
                        values["role"],
                        values["hostname"],
                        values["os_name"],
                        values["os_version"],
                        values["kernel"],
                        values["arch"],
                        values["python_version"],
                        values["client_version"],
                        values["ip_addresses"],
                        values["raw_json"],
                        now,
                        now,
                        node_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO edge_nodes
                        (node_id, name, role, hostname, os_name, os_version,
                         kernel, arch, python_version, client_version, ip_addresses,
                         raw_json, last_seen_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["node_id"],
                        values["name"],
                        values["role"],
                        values["hostname"],
                        values["os_name"],
                        values["os_version"],
                        values["kernel"],
                        values["arch"],
                        values["python_version"],
                        values["client_version"],
                        values["ip_addresses"],
                        values["raw_json"],
                        now,
                        now,
                        now,
                    ),
                )
            conn.commit()
            row = conn.execute("SELECT * FROM edge_nodes WHERE node_id = ?", (node_id,)).fetchone()
        return jsonify({"ok": True, "node": row_to_dict(row)})

    @app.post("/api/edge/heartbeat")
    def edge_heartbeat():
        payload = request.get_json(silent=True) or {}
        node_id = str(payload.get("node_id") or payload.get("hostname") or "").strip()
        if not node_id:
            return jsonify({"ok": False, "error": "node_id is required"}), 400

        now = utc_now()
        status_value = str(payload.get("status") or "online").strip() or "online"
        ip_addresses = normalize_string_list(payload.get("ip_addresses") or payload.get("ips"))
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}

        with connect_db() as conn:
            existing = conn.execute("SELECT id FROM edge_nodes WHERE node_id = ?", (node_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE edge_nodes
                    SET last_seen_at = ?, updated_at = ?,
                        ip_addresses = COALESCE(NULLIF(?, '[]'), ip_addresses),
                        client_version = COALESCE(?, client_version)
                    WHERE node_id = ?
                    """,
                    (
                        now,
                        now,
                        json_text(ip_addresses, []),
                        payload.get("client_version"),
                        node_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO edge_nodes
                        (node_id, name, role, hostname, client_version, ip_addresses,
                         raw_json, last_seen_at, created_at, updated_at)
                    VALUES (?, ?, 'orange_pi_edge', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_id,
                        str(payload.get("name") or node_id).strip(),
                        payload.get("hostname"),
                        payload.get("client_version"),
                        json_text(ip_addresses, []),
                        json_text(payload, {}),
                        now,
                        now,
                        now,
                    ),
                )

            cursor = conn.execute(
                """
                INSERT INTO edge_heartbeats
                    (node_id, status, ip_addresses, metrics_json, raw_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    status_value,
                    json_text(ip_addresses, []),
                    json_text(metrics, {}),
                    json_text(payload, {}),
                    now,
                ),
            )
            conn.commit()
            node = conn.execute("SELECT * FROM edge_nodes WHERE node_id = ?", (node_id,)).fetchone()
            heartbeat = conn.execute("SELECT * FROM edge_heartbeats WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "node": row_to_dict(node), "heartbeat": row_to_dict(heartbeat)})

    @app.get("/api/edge/nodes")
    def edge_nodes():
        with connect_db() as conn:
            rows = conn.execute(
                """
                SELECT
                    n.*,
                    h.status AS latest_status,
                    h.metrics_json AS latest_metrics_json,
                    h.created_at AS latest_heartbeat_at
                FROM edge_nodes n
                LEFT JOIN edge_heartbeats h ON h.id = (
                    SELECT id FROM edge_heartbeats
                    WHERE node_id = n.node_id
                    ORDER BY id DESC
                    LIMIT 1
                )
                ORDER BY COALESCE(n.last_seen_at, n.updated_at) DESC
                """
            ).fetchall()
        return jsonify({"ok": True, "nodes": [row_to_dict(row) for row in rows]})

    @app.get("/api/edge/heartbeats")
    def edge_heartbeats():
        limit = min(parse_int(request.args.get("limit"), 50) or 50, 200)
        node_id = request.args.get("node_id")
        with connect_db() as conn:
            if node_id:
                rows = conn.execute(
                    """
                    SELECT * FROM edge_heartbeats
                    WHERE node_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (node_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM edge_heartbeats ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return jsonify({"ok": True, "heartbeats": [row_to_dict(row) for row in rows]})

    @app.post("/api/camera/upload")
    def camera_upload():
        image_path, upload_payload, error = save_camera_upload()
        if error:
            return jsonify({"ok": False, "error": error}), 400

        payload = {
            **upload_payload,
            "image_path": image_path,
            "source": upload_payload.get("source") or "orange_pi_camera",
        }
        try:
            row = create_yolo_record(payload)
        except Exception as exc:
            return jsonify({"ok": False, "image_path": image_path, "error": str(exc)}), 500

        face_row = None
        face_error = None
        lock_status = None
        if image_path and camera_face_verify_enabled(upload_payload):
            try:
                face_row = create_face_record({**payload, "trigger": "camera_upload"})
                lock_status = sync_lock_state_from_face(face_row)
            except Exception as exc:
                face_error = str(exc)

        return jsonify(
            {
                "ok": True,
                "image_path": image_path,
                "yolo_record": row_to_dict(row),
                "face_record": row_to_dict(face_row),
                "face_error": face_error,
                "status": row_to_dict(lock_status),
            }
        )

    @app.post("/api/yolo/detect")
    def yolo_detect():
        payload = request.get_json(silent=True) or {}
        try:
            row = create_yolo_record(payload)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        return jsonify({"ok": True, "record": row_to_dict(row)})

    @app.get("/api/yolo/latest")
    def yolo_latest():
        row = latest_yolo_record()
        return jsonify({"ok": True, "record": row_to_dict(row)})

    @app.get("/api/yolo/history")
    def yolo_history():
        limit = min(parse_int(request.args.get("limit"), 50) or 50, 200)
        with connect_db() as conn:
            rows = conn.execute("SELECT * FROM detection_records ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return jsonify({"ok": True, "records": [row_to_dict(row) for row in rows]})

    @app.get("/api/face/users")
    def face_users():
        with connect_db() as conn:
            rows = conn.execute(
                """
                SELECT
                    u.*,
                    COUNT(i.id) AS image_count
                FROM authorized_users u
                LEFT JOIN face_gallery_images i ON i.user_id = u.id
                GROUP BY u.id
                ORDER BY u.id DESC
                """
            ).fetchall()
        return jsonify({"ok": True, "users": [row_to_dict(row) for row in rows]})

    @app.post("/api/face/users")
    def create_face_user():
        if request.files:
            payload = request.form.to_dict()
            try:
                uploaded_image_path = save_face_upload_file()
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
            if uploaded_image_path:
                payload["image_path"] = uploaded_image_path
        else:
            payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        if not name:
            return jsonify({"ok": False, "error": "name is required"}), 400

        with connect_db() as conn:
            identity = payload.get("identity")
            identity = make_identity(str(identity)) if identity else unique_identity(conn, name)
            existing = conn.execute("SELECT id FROM authorized_users WHERE identity = ?", (identity,)).fetchone()
            if existing is not None:
                return jsonify({"ok": False, "error": "identity already exists"}), 409
            now = utc_now()
            cursor = conn.execute(
                """
                INSERT INTO authorized_users
                    (identity, name, image_path, encoding_path, active, updated_at, created_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (identity, name, None, payload.get("encoding_path"), now, now),
            )
            user = conn.execute("SELECT * FROM authorized_users WHERE id = ?", (cursor.lastrowid,)).fetchone()
            image = None
            if payload.get("image_path"):
                image = add_gallery_image(
                    conn,
                    user,
                    str(payload["image_path"]),
                    payload,
                    copy_to_gallery=parse_bool(payload.get("copy_to_gallery")) != 0,
                )
            conn.commit()
            user = conn.execute("SELECT * FROM authorized_users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "user": row_to_dict(user), "image": row_to_dict(image)}), 201

    @app.get("/api/face/users/<int:user_id>")
    def face_user_detail(user_id: int):
        with connect_db() as conn:
            user = conn.execute("SELECT * FROM authorized_users WHERE id = ?", (user_id,)).fetchone()
            if user is None:
                return jsonify({"ok": False, "error": "user not found"}), 404
            images = conn.execute(
                "SELECT * FROM face_gallery_images WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
        return jsonify({"ok": True, "user": row_to_dict(user), "images": [row_to_dict(row) for row in images]})

    @app.patch("/api/face/users/<int:user_id>")
    def update_face_user(user_id: int):
        payload = request.get_json(silent=True) or {}
        with connect_db() as conn:
            user = conn.execute("SELECT * FROM authorized_users WHERE id = ?", (user_id,)).fetchone()
            if user is None:
                return jsonify({"ok": False, "error": "user not found"}), 404

            name = str(payload.get("name") if payload.get("name") is not None else user["name"]).strip()
            if not name:
                return jsonify({"ok": False, "error": "name is required"}), 400
            old_identity = user["identity"] or f"user_{user['id']:03d}"
            new_identity = payload.get("identity")
            new_identity = make_identity(str(new_identity)) if new_identity is not None else old_identity
            duplicate = conn.execute(
                "SELECT id FROM authorized_users WHERE identity = ? AND id != ?",
                (new_identity, user_id),
            ).fetchone()
            if duplicate is not None:
                return jsonify({"ok": False, "error": "identity already exists"}), 409

            gallery_dir = get_face_gallery_dir()
            old_dir = gallery_dir / old_identity
            new_dir = gallery_dir / new_identity
            if new_identity != old_identity and old_dir.exists():
                if new_dir.exists():
                    return jsonify({"ok": False, "error": "target gallery identity directory already exists"}), 409
                new_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_dir), str(new_dir))
                old_prefix = str(old_dir)
                new_prefix = str(new_dir)
                images = conn.execute("SELECT * FROM face_gallery_images WHERE user_id = ?", (user_id,)).fetchall()
                for image in images:
                    image_path = image["image_path"]
                    if image_path and str(image_path).startswith(old_prefix):
                        conn.execute(
                            "UPDATE face_gallery_images SET image_path = ? WHERE id = ?",
                            (str(image_path).replace(old_prefix, new_prefix, 1), image["id"]),
                        )
                if user["image_path"] and str(user["image_path"]).startswith(old_prefix):
                    conn.execute(
                        "UPDATE authorized_users SET image_path = ? WHERE id = ?",
                        (str(user["image_path"]).replace(old_prefix, new_prefix, 1), user_id),
                    )

            conn.execute(
                """
                UPDATE authorized_users
                SET identity = ?, name = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_identity, name, utc_now(), user_id),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM authorized_users WHERE id = ?", (user_id,)).fetchone()
        return jsonify({"ok": True, "user": row_to_dict(updated)})

    @app.delete("/api/face/users/<int:user_id>")
    def delete_face_user(user_id: int):
        with connect_db() as conn:
            user = conn.execute("SELECT * FROM authorized_users WHERE id = ?", (user_id,)).fetchone()
            if user is None:
                return jsonify({"ok": False, "error": "user not found"}), 404
            identity = user["identity"] or f"user_{user['id']:03d}"
            conn.execute("DELETE FROM face_gallery_images WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM authorized_users WHERE id = ?", (user_id,))
            conn.commit()

        gallery_dir = get_face_gallery_dir().resolve()
        user_gallery_dir = (gallery_dir / identity).resolve()
        if user_gallery_dir.exists() and (user_gallery_dir == gallery_dir or gallery_dir in user_gallery_dir.parents):
            if user_gallery_dir != gallery_dir:
                shutil.rmtree(user_gallery_dir)
        return jsonify({"ok": True, "deleted_user_id": user_id, "identity": identity})

    @app.post("/api/face/users/<int:user_id>/images")
    def add_face_user_image(user_id: int):
        payload = request.get_json(silent=True) or {}
        image_path = str(payload.get("image_path", "")).strip()
        if not image_path:
            return jsonify({"ok": False, "error": "image_path is required"}), 400

        with connect_db() as conn:
            user = conn.execute("SELECT * FROM authorized_users WHERE id = ?", (user_id,)).fetchone()
            if user is None:
                return jsonify({"ok": False, "error": "user not found"}), 404
            image = add_gallery_image(
                conn,
                user,
                image_path,
                payload,
                copy_to_gallery=parse_bool(payload.get("copy_to_gallery")) != 0,
            )
            conn.commit()
        return jsonify({"ok": True, "image": row_to_dict(image)}), 201

    @app.get("/api/face/gallery")
    def face_gallery():
        with connect_db() as conn:
            users = conn.execute(
                """
                SELECT
                    u.id,
                    u.identity,
                    u.name,
                    u.active,
                    COUNT(i.id) AS image_count
                FROM authorized_users u
                LEFT JOIN face_gallery_images i ON i.user_id = u.id
                GROUP BY u.id
                ORDER BY u.identity ASC
                """
            ).fetchall()
            images = conn.execute(
                """
                SELECT i.*, u.identity, u.name
                FROM face_gallery_images i
                JOIN authorized_users u ON u.id = i.user_id
                ORDER BY u.identity ASC, i.id ASC
                """
            ).fetchall()
        return jsonify(
            {
                "ok": True,
                "gallery_dir": str(get_face_gallery_dir()),
                "users": [row_to_dict(row) for row in users],
                "images": [row_to_dict(row) for row in images],
            }
        )

    @app.post("/api/face/access")
    @app.post("/api/face/verify")
    def face_access():
        payload = request.get_json(silent=True) or {}
        try:
            row = create_face_record(payload)
            status_row = sync_lock_state_from_face(row)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        return jsonify({"ok": True, "record": row_to_dict(row), "status": row_to_dict(status_row)})

    @app.post("/api/face/verify-latest")
    def face_verify_latest():
        payload = request.get_json(silent=True) or {}
        source_record = latest_yolo_record()
        if source_record is None:
            return jsonify({"ok": False, "error": "no camera frame available"}), 404

        image_path = str(payload.get("image_path") or source_record["image_path"] or "").strip()
        if not image_path:
            return jsonify({"ok": False, "error": "latest camera frame has no image_path"}), 404

        try:
            row = create_face_record(
                {
                    **payload,
                    "image_path": image_path,
                    "trigger": payload.get("trigger") or "manual_verify_latest",
                    "source_detection_id": source_record["id"],
                    "source_yolo_record_id": source_record["id"],
                }
            )
            status_row = sync_lock_state_from_face(row)
        except Exception as exc:
            return jsonify({"ok": False, "image_path": image_path, "error": str(exc)}), 500
        return jsonify(
            {
                "ok": True,
                "image_path": image_path,
                "record": row_to_dict(row),
                "yolo_record": row_to_dict(source_record),
                "source_yolo_record": row_to_dict(source_record),
                "status": row_to_dict(status_row),
            }
        )

    @app.get("/api/face/latest")
    def face_latest():
        with connect_db() as conn:
            row = conn.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT 1").fetchone()
        return jsonify({"ok": True, "record": row_to_dict(row)})

    @app.get("/api/face/history")
    def face_history():
        limit = min(parse_int(request.args.get("limit"), 50) or 50, 200)
        with connect_db() as conn:
            rows = conn.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return jsonify({"ok": True, "records": [row_to_dict(row) for row in rows]})

    app.extensions["ingest_sensor"] = ingest_sensor
    if hasattr(uno_bridge, "set_telemetry_handler"):
        uno_bridge.set_telemetry_handler(ingest_sensor)
    uno_bridge.start()
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
