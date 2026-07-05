"""
database.py
-----------
SQLite persistence layer (async, via aiosqlite).

Two tables:
  - users : the single/multi user "memory" profile (name, email, phone, address, resume)
  - tasks  : every agent run, so status survives a server restart
"""

import json
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "app_data.db"
LEGACY_PROFILE_JSON = Path(__file__).parent.parent / "user_profile.json"

CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    phone TEXT,
    address TEXT,
    resume_text TEXT,
    updated_at TEXT
);
"""

CREATE_TASKS_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    status TEXT NOT NULL,           -- queued | running | completed | failed
    steps TEXT NOT NULL DEFAULT '[]', -- JSON list of step logs
    result TEXT,                    -- JSON result payload (nullable)
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS_SQL)
        await db.execute(CREATE_TASKS_SQL)
        await db.commit()
    await _migrate_legacy_profile_if_needed()


async def _migrate_legacy_profile_if_needed():
    """One-time import of Week 4's user_profile.json into SQLite, so you
    don't lose the profile you already set up. Only runs if the users
    table is empty and the legacy file exists."""
    if not LEGACY_PROFILE_JSON.exists():
        return
    existing = await get_profile()
    if existing:
        return
    with open(LEGACY_PROFILE_JSON, "r") as f:
        legacy = json.load(f)
    await upsert_profile(
        name=legacy.get("name"),
        email=legacy.get("email"),
        phone=legacy.get("phone"),
        address=legacy.get("address"),
        # Week 4 stored a resume file path; Week 5 wants resume TEXT.
        # We seed resume_text with the path as a placeholder — replace it
        # with the actual extracted resume text via POST /user/profile.
        resume_text=legacy.get("resume_path", ""),
    )
    print(f"Migrated profile from {LEGACY_PROFILE_JSON.name} into SQLite.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- users ---

async def get_profile() -> dict | None:
    """Returns the single stored user profile (this app assumes one local user,
    like a personal browser-agent memory). Extend with a user_id if you need
    multi-user support later."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users ORDER BY id LIMIT 1")
        row = await cursor.fetchone()
        return dict(row) if row else None


async def upsert_profile(name, email, phone, address, resume_text) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        existing = await (await db.execute("SELECT id FROM users ORDER BY id LIMIT 1")).fetchone()
        now = _now()
        if existing:
            await db.execute(
                """UPDATE users SET name=?, email=?, phone=?, address=?,
                   resume_text=?, updated_at=? WHERE id=?""",
                (name, email, phone, address, resume_text, now, existing["id"]),
            )
        else:
            await db.execute(
                """INSERT INTO users (name, email, phone, address, resume_text, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, email, phone, address, resume_text, now),
            )
        await db.commit()
        cursor = await db.execute("SELECT * FROM users ORDER BY id LIMIT 1")
        row = await cursor.fetchone()
        return dict(row)


# ---------------------------------------------------------------- tasks ---

async def create_task(task_id: str, command: str):
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO tasks (task_id, command, status, steps, result, error, created_at, updated_at)
               VALUES (?, ?, 'queued', '[]', NULL, NULL, ?, ?)""",
            (task_id, command, now, now),
        )
        await db.commit()


async def update_task_status(task_id: str, status: str, result: dict | None = None, error: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tasks SET status=?, result=?, error=?, updated_at=? WHERE task_id=?",
            (status, json.dumps(result) if result is not None else None, error, _now(), task_id),
        )
        await db.commit()


async def append_task_step(task_id: str, step: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT steps FROM tasks WHERE task_id=?", (task_id,))
        row = await cursor.fetchone()
        steps = json.loads(row["steps"]) if row else []
        steps.append(step)
        await db.execute(
            "UPDATE tasks SET steps=?, updated_at=? WHERE task_id=?",
            (json.dumps(steps), _now(), task_id),
        )
        await db.commit()


async def get_task(task_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["steps"] = json.loads(d["steps"])
        d["result"] = json.loads(d["result"]) if d["result"] else None
        return d
