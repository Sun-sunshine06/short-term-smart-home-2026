from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "smart_home.db"
DEFAULT_UPLOAD_DIR = BACKEND_DIR / "data" / "uploads" / "camera"
DEFAULT_RESULTS_DIR = BACKEND_DIR / "static" / "results"
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def connect_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def cutoff_id(conn: sqlite3.Connection, table: str, keep: int) -> int | None:
    if keep <= 0 or not table_exists(conn, table):
        return None
    row = conn.execute(
        f"SELECT id FROM {table} ORDER BY id DESC LIMIT 1 OFFSET ?",
        (keep - 1,),
    ).fetchone()
    return int(row["id"]) if row else None


def count_before(conn: sqlite3.Connection, table: str, cutoff: int | None) -> int:
    if cutoff is None or not table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE id < ?", (cutoff,)).fetchone()["c"])


def delete_before(conn: sqlite3.Connection, table: str, cutoff: int | None) -> int:
    if cutoff is None or not table_exists(conn, table):
        return 0
    cursor = conn.execute(f"DELETE FROM {table} WHERE id < ?", (cutoff,))
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def iter_candidate_detection_paths(conn: sqlite3.Connection, cutoff: int | None) -> Iterable[str]:
    if cutoff is None or not table_exists(conn, "detection_records"):
        return []
    rows = conn.execute(
        """
        SELECT image_path, result_image_path
        FROM detection_records
        WHERE id < ?
        """,
        (cutoff,),
    ).fetchall()
    values: list[str] = []
    for row in rows:
        for key in ("image_path", "result_image_path"):
            value = row[key]
            if value:
                values.append(str(value))
    return values


def iter_protected_image_paths(conn: sqlite3.Connection, detection_cutoff: int | None) -> set[Path]:
    protected: set[Path] = set()
    queries = []
    if table_exists(conn, "detection_records"):
        if detection_cutoff is None:
            queries.append(("SELECT image_path, result_image_path FROM detection_records", ()))
        else:
            queries.append(
                (
                    "SELECT image_path, result_image_path FROM detection_records WHERE id >= ?",
                    (detection_cutoff,),
                )
            )
    if table_exists(conn, "access_logs"):
        queries.append(("SELECT image_path FROM access_logs", ()))
    if table_exists(conn, "face_gallery_images"):
        queries.append(("SELECT image_path, original_image_path FROM face_gallery_images", ()))
    if table_exists(conn, "authorized_users"):
        queries.append(("SELECT image_path FROM authorized_users", ()))

    for sql, params in queries:
        for row in conn.execute(sql, params).fetchall():
            for value in row:
                resolved = resolve_managed_image_path(value)
                if resolved:
                    protected.add(resolved)
    return protected


def managed_roots() -> list[Path]:
    roots = [
        Path(os.environ.get("CAMERA_UPLOAD_DIR", DEFAULT_UPLOAD_DIR)),
        DEFAULT_RESULTS_DIR,
        PROJECT_ROOT / "local" / "runtime",
    ]
    return [root.resolve() for root in roots if root.exists() or root.parent.exists()]


def resolve_managed_image_path(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None
    if resolved.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        return None
    roots = managed_roots()
    if not any(resolved == root or root in resolved.parents for root in roots):
        return None
    return resolved


def remove_file(path: Path, apply: bool) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if apply:
        path.unlink()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely prune old SQLite rows and managed camera/result images.")
    parser.add_argument("--db", default=os.environ.get("SMART_HOME_DB", str(DEFAULT_DB_PATH)), help="SQLite database path.")
    parser.add_argument("--keep-detections", type=int, default=1000, help="Keep the newest N YOLO records.")
    parser.add_argument("--keep-sensors", type=int, default=2000, help="Keep the newest N sensor records.")
    parser.add_argument("--keep-heartbeats", type=int, default=2000, help="Keep the newest N heartbeat records.")
    parser.add_argument("--keep-access-logs", type=int, default=500, help="Keep the newest N access log records.")
    parser.add_argument("--delete-files", action="store_true", help="Also delete image files only referenced by pruned YOLO records.")
    parser.add_argument("--apply", action="store_true", help="Actually delete rows/files. Without this flag the script is dry-run.")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"database not found: {db_path}")

    with connect_db(db_path) as conn:
        detection_cutoff = cutoff_id(conn, "detection_records", args.keep_detections)
        plans = {
            "detection_records": (detection_cutoff, count_before(conn, "detection_records", detection_cutoff)),
            "sensor_records": (
                cutoff_id(conn, "sensor_records", args.keep_sensors),
                0,
            ),
            "edge_heartbeats": (
                cutoff_id(conn, "edge_heartbeats", args.keep_heartbeats),
                0,
            ),
            "access_logs": (
                cutoff_id(conn, "access_logs", args.keep_access_logs),
                0,
            ),
        }
        plans["sensor_records"] = (plans["sensor_records"][0], count_before(conn, "sensor_records", plans["sensor_records"][0]))
        plans["edge_heartbeats"] = (
            plans["edge_heartbeats"][0],
            count_before(conn, "edge_heartbeats", plans["edge_heartbeats"][0]),
        )
        plans["access_logs"] = (plans["access_logs"][0], count_before(conn, "access_logs", plans["access_logs"][0]))

        candidate_paths = [resolve_managed_image_path(value) for value in iter_candidate_detection_paths(conn, detection_cutoff)]
        protected_paths = iter_protected_image_paths(conn, detection_cutoff)
        files_to_remove = sorted(
            {
                path
                for path in candidate_paths
                if path is not None and path not in protected_paths and path.exists() and path.is_file()
            }
        )

        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"cleanup mode: {mode}")
        print(f"database: {db_path}")
        for table, (cutoff, count) in plans.items():
            print(f"{table}: delete {count} rows before id {cutoff}")
        print(f"managed image files: delete {len(files_to_remove)} files")

        if not args.apply:
            print("dry-run only; add --apply to perform cleanup")
            return

        if args.delete_files:
            removed_files = sum(1 for path in files_to_remove if remove_file(path, apply=True))
        else:
            removed_files = 0

        removed_rows = {table: delete_before(conn, table, cutoff) for table, (cutoff, _) in plans.items()}
        conn.commit()
        print(f"removed rows: {removed_rows}")
        print(f"removed files: {removed_files}")


if __name__ == "__main__":
    main()
