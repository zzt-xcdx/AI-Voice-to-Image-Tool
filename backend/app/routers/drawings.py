import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.config import settings
from app.paths import DATA_DIR
from app.routers.voice import Command


router = APIRouter(prefix="/api/drawings", tags=["drawings"])


def _ensure_db() -> Path:
    """
    初始化 SQLite 数据库和表结构。
    """
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drawings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            commands_json TEXT NOT NULL,
            asr_text TEXT,
            reply_text TEXT,
            width INTEGER,
            height INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()
    return db_path


DB_PATH = _ensure_db()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class DrawingCreate(BaseModel):
    title: str | None = None
    commands: list[Command]
    asr_text: str | None = None
    reply_text: str | None = None
    width: int | None = None
    height: int | None = None


class DrawingOut(BaseModel):
    id: int
    title: str | None
    commands: list[Command]
    asr_text: str | None
    reply_text: str | None
    width: int | None
    height: int | None
    created_at: str


async def _insert_drawing(payload: DrawingCreate) -> int:
    def _work() -> int:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO drawings (title, commands_json, asr_text, reply_text, width, height)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.title or "未命名",
                    json.dumps([c.model_dump() for c in payload.commands], ensure_ascii=False),
                    payload.asr_text,
                    payload.reply_text,
                    payload.width,
                    payload.height,
                ),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    return await run_in_threadpool(_work)


async def _fetch_one(drawing_id: int) -> DrawingOut:
    def _work() -> DrawingOut:
        conn = _connect()
        try:
            cur = conn.execute("SELECT * FROM drawings WHERE id = ?", (drawing_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="绘图不存在")
            commands = json.loads(row["commands_json"])
            return DrawingOut(
                id=row["id"],
                title=row["title"],
                commands=[Command.model_validate(c) for c in commands],
                asr_text=row["asr_text"],
                reply_text=row["reply_text"],
                width=row["width"],
                height=row["height"],
                created_at=row["created_at"],
            )
        finally:
            conn.close()

    return await run_in_threadpool(_work)


async def _fetch_list(limit: int = 20) -> list[DrawingOut]:
    def _work() -> list[DrawingOut]:
        conn = _connect()
        try:
            cur = conn.execute(
                "SELECT * FROM drawings ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            result: list[DrawingOut] = []
            for row in rows:
                commands = json.loads(row["commands_json"])
                result.append(
                    DrawingOut(
                        id=row["id"],
                        title=row["title"],
                        commands=[Command.model_validate(c) for c in commands],
                        asr_text=row["asr_text"],
                        reply_text=row["reply_text"],
                        width=row["width"],
                        height=row["height"],
                        created_at=row["created_at"],
                    )
                )
            return result
        finally:
            conn.close()

    return await run_in_threadpool(_work)


@router.post("", response_model=DrawingOut)
async def save_drawing(payload: DrawingCreate) -> DrawingOut:
    if not payload.commands:
        raise HTTPException(status_code=400, detail="commands 不能为空")
    new_id = await _insert_drawing(payload)
    return await _fetch_one(new_id)


@router.get("", response_model=list[DrawingOut])
async def list_drawings(limit: int = 20) -> list[DrawingOut]:
    limit = max(1, min(limit, 100))
    return await _fetch_list(limit)


@router.get("/{drawing_id}", response_model=DrawingOut)
async def get_drawing(drawing_id: int) -> DrawingOut:
    return await _fetch_one(drawing_id)
