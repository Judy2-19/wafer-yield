"""本地 SQLite：连接配置、规格模板覆盖、审计日志。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .crypto_util import decrypt_text, encrypt_text

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "local.db"


def _conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS db_config (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              host TEXT NOT NULL,
              port INTEGER NOT NULL,
              database TEXT NOT NULL,
              user TEXT NOT NULL,
              password_enc TEXT NOT NULL,
              use_mock INTEGER NOT NULL DEFAULT 1,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS spec_templates (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              specs_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_name TEXT,
              action TEXT NOT NULL,
              detail TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS judge_results (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              wafer TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_config() -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM db_config WHERE id = 1").fetchone()
    if not row:
        return {
            "host": "127.0.0.1",
            "port": 3306,
            "database": "mg_nano",
            "user": "root",
            "password": "",
            "use_mock": True,
        }
    return {
        "host": row["host"],
        "port": row["port"],
        "database": row["database"],
        "user": row["user"],
        "password": decrypt_text(row["password_enc"]) if row["password_enc"] else "",
        "use_mock": bool(row["use_mock"]),
    }


def save_db_config(cfg: dict[str, Any]) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO db_config (id, host, port, database, user, password_enc, use_mock, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              host=excluded.host,
              port=excluded.port,
              database=excluded.database,
              user=excluded.user,
              password_enc=excluded.password_enc,
              use_mock=excluded.use_mock,
              updated_at=excluded.updated_at
            """,
            (
                cfg["host"],
                int(cfg["port"]),
                cfg["database"],
                cfg["user"],
                encrypt_text(cfg.get("password") or ""),
                1 if cfg.get("use_mock", True) else 0,
                now_iso(),
            ),
        )


def save_template(template_id: str, name: str, specs: list[dict[str, Any]]) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO spec_templates (id, name, specs_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              specs_json=excluded.specs_json,
              updated_at=excluded.updated_at
            """,
            (template_id, name, json.dumps(specs, ensure_ascii=False), now_iso()),
        )


def get_saved_template(template_id: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM spec_templates WHERE id = ?", (template_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "specs": json.loads(row["specs_json"]),
        "builtin": False,
    }


def list_saved_templates() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM spec_templates ORDER BY updated_at DESC").fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "specs": json.loads(r["specs_json"]),
            "builtin": False,
        }
        for r in rows
    ]


def delete_template(template_id: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM spec_templates WHERE id = ?", (template_id,))
        return cur.rowcount > 0


def add_audit(action: str, detail: dict[str, Any], user_name: str = "operator") -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO audit_logs (user_name, action, detail, created_at) VALUES (?, ?, ?, ?)",
            (user_name, action, json.dumps(detail, ensure_ascii=False), now_iso()),
        )


def list_audit(limit: int = 100) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        {
            "id": r["id"],
            "user_name": r["user_name"],
            "action": r["action"],
            "detail": json.loads(r["detail"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def save_judge_result(wafer: str, payload: dict[str, Any]) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO judge_results (wafer, payload_json, created_at) VALUES (?, ?, ?)",
            (wafer, json.dumps(payload, ensure_ascii=False), now_iso()),
        )
