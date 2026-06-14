import json
import sqlite3
from datetime import datetime
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
            background_base64 TEXT,
            exported INTEGER,
            export_target TEXT,
            export_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # 兼容旧表，补充字段
    for alter in [
        "ALTER TABLE drawings ADD COLUMN background_base64 TEXT",
        "ALTER TABLE drawings ADD COLUMN exported INTEGER",
        "ALTER TABLE drawings ADD COLUMN export_target TEXT",
        "ALTER TABLE drawings ADD COLUMN export_time TEXT",
    ]:
        try:
            conn.execute(alter)
        except sqlite3.OperationalError:
            pass
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
    background_base64: str | None = None
    exported: bool | None = None
    export_target: str | None = None
    export_time: str | None = None


class DrawingOut(BaseModel):
    id: int
    title: str | None
    commands: list[Command]
    asr_text: str | None
    reply_text: str | None
    width: int | None
    height: int | None
    background_base64: str | None
    created_at: str
    exported: bool | None = None
    export_target: str | None = None
    export_time: str | None = None


class DrawingUpdate(BaseModel):
    title: str | None = None
    commands: list[Command] | None = None
    asr_text: str | None = None
    reply_text: str | None = None
    width: int | None = None
    height: int | None = None
    background_base64: str | None = None
    exported: bool | None = None
    export_target: str | None = None
    export_time: str | None = None


async def _insert_drawing(payload: DrawingCreate) -> int:
    def _work() -> int:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO drawings (title, commands_json, asr_text, reply_text, width, height, background_base64, exported, export_target, export_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.title or "未命名",
                    json.dumps([c.model_dump() for c in payload.commands], ensure_ascii=False),
                    payload.asr_text,
                    payload.reply_text,
                    payload.width,
                    payload.height,
                    payload.background_base64,
                    1 if payload.exported else 0 if payload.exported is not None else None,
                    payload.export_target,
                    payload.export_time,
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
                background_base64=row["background_base64"] if "background_base64" in row.keys() else None,
                exported=bool(row["exported"]) if "exported" in row.keys() else None,
                export_target=row["export_target"] if "export_target" in row.keys() else None,
                export_time=row["export_time"] if "export_time" in row.keys() else None,
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
                        background_base64=row["background_base64"] if "background_base64" in row.keys() else None,
                        exported=bool(row["exported"]) if "exported" in row.keys() else None,
                        export_target=row["export_target"] if "export_target" in row.keys() else None,
                        export_time=row["export_time"] if "export_time" in row.keys() else None,
                        created_at=row["created_at"],
                    )
                )
            return result
        finally:
            conn.close()

    return await run_in_threadpool(_work)


async def _update_drawing(drawing_id: int, payload: DrawingUpdate) -> DrawingOut:
    def _work() -> DrawingOut:
        conn = _connect()
        try:
            cur = conn.execute("SELECT * FROM drawings WHERE id = ?", (drawing_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="绘图不存在")
            commands_json = row["commands_json"]
            bg = row["background_base64"] if "background_base64" in row.keys() else None
            if payload.commands is not None:
                commands_json = json.dumps([c.model_dump() for c in payload.commands], ensure_ascii=False)
            if payload.background_base64 is not None:
                bg = payload.background_base64
            conn.execute(
                """
                UPDATE drawings
                SET title = ?, commands_json = ?, asr_text = ?, reply_text = ?, width = ?, height = ?, background_base64 = ?, exported = ?, export_target = ?, export_time = ?
                WHERE id = ?
                """,
                (
                    payload.title if payload.title is not None else row["title"],
                    commands_json,
                    payload.asr_text if payload.asr_text is not None else row["asr_text"],
                    payload.reply_text if payload.reply_text is not None else row["reply_text"],
                    payload.width if payload.width is not None else row["width"],
                    payload.height if payload.height is not None else row["height"],
                    bg,
                    int(payload.exported) if payload.exported is not None else row["exported"] if "exported" in row.keys() else None,
                    payload.export_target if payload.export_target is not None else row["export_target"] if "export_target" in row.keys() else None,
                    payload.export_time if payload.export_time is not None else row["export_time"] if "export_time" in row.keys() else None,
                    drawing_id,
                ),
            )
            conn.commit()
            cur2 = conn.execute("SELECT * FROM drawings WHERE id = ?", (drawing_id,))
            updated = cur2.fetchone()
            commands = json.loads(updated["commands_json"])
            return DrawingOut(
                id=updated["id"],
                title=updated["title"],
                commands=[Command.model_validate(c) for c in commands],
                asr_text=updated["asr_text"],
                reply_text=updated["reply_text"],
                width=updated["width"],
                height=updated["height"],
                background_base64=updated["background_base64"] if "background_base64" in updated.keys() else None,
                created_at=updated["created_at"],
            )
        finally:
            conn.close()

    return await run_in_threadpool(_work)


async def _delete_drawing(drawing_id: int) -> None:
    def _work() -> None:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM drawings WHERE id = ?", (drawing_id,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="绘图不存在")
        finally:
            conn.close()

    return await run_in_threadpool(_work)


# 供内部调用的轻量创建（无需 Command 校验），如自动保存图片
async def create_drawing_from_payload(raw: dict[str, Any]) -> int:
    def _work() -> int:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO drawings (title, commands_json, asr_text, reply_text, width, height, background_base64, exported, export_target, export_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw.get("title") or "未命名",
                    json.dumps(raw.get("commands") or [], ensure_ascii=False),
                    raw.get("asr_text"),
                    raw.get("reply_text"),
                    raw.get("width"),
                    raw.get("height"),
                    raw.get("background_base64"),
                    1 if raw.get("exported") else 0 if raw.get("exported") is not None else None,
                    raw.get("export_target"),
                    raw.get("export_time"),
                ),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    return await run_in_threadpool(_work)


@router.post("", response_model=DrawingOut)
async def save_drawing(payload: DrawingCreate) -> DrawingOut:
    if not payload.commands and not payload.background_base64:
        raise HTTPException(status_code=400, detail="commands 不能为空")
    new_id = await _insert_drawing(payload)
    return await _fetch_one(new_id)


@router.post("/{drawing_id}/export", response_model=DrawingOut)
async def export_drawing(drawing_id: int, target: str = "desktop") -> DrawingOut:
    update = DrawingUpdate(exported=True, export_target=target, export_time=datetime.utcnow().isoformat())
    return await _update_drawing(drawing_id, update)


@router.post("/export", response_model=DrawingOut)
async def export_new(payload: DrawingCreate) -> DrawingOut:
    if not payload.background_base64:
        raise HTTPException(status_code=400, detail="缺少 background_base64")
    payload.exported = True
    payload.export_target = payload.export_target or "desktop"
    payload.export_time = payload.export_time or datetime.utcnow().isoformat()
    new_id = await _insert_drawing(payload)
    return await _fetch_one(new_id)


@router.get("", response_model=list[DrawingOut])
async def list_drawings(limit: int = 20) -> list[DrawingOut]:
    limit = max(1, min(limit, 100))
    return await _fetch_list(limit)


@router.get("/{drawing_id}", response_model=DrawingOut)
async def get_drawing(drawing_id: int) -> DrawingOut:
    return await _fetch_one(drawing_id)


@router.put("/{drawing_id}", response_model=DrawingOut)
async def update_drawing(drawing_id: int, payload: DrawingUpdate) -> DrawingOut:
    if (
        payload.commands is None
        and payload.title is None
        and payload.background_base64 is None
        and payload.asr_text is None
        and payload.reply_text is None
        and payload.width is None
        and payload.height is None
    ):
        raise HTTPException(status_code=400, detail="缺少可更新字段")
    return await _update_drawing(drawing_id, payload)


@router.delete("/{drawing_id}")
async def delete_drawing(drawing_id: int) -> dict[str, str]:
    await _delete_drawing(drawing_id)
    return {"detail": "deleted"}
