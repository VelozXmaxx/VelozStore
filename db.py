import os
import asyncpg
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")  # e.g., postgres://user:pass@host:port/db
pool: asyncpg.Pool | None = None


async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as con:
        await con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            first_name TEXT,
            joined_at TIMESTAMPTZ
        );
        CREATE TABLE IF NOT EXISTS free_stuff (
            id SERIAL PRIMARY KEY,
            file_id TEXT NOT NULL,
            added_by BIGINT,
            added_at TIMESTAMPTZ DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS admins (
            user_id BIGINT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS required_channels (
            ident TEXT PRIMARY KEY  -- '@channel' or numeric id as text
        );
        """)


async def ensure_bootstrap_data(main_admin: int | None, secondary_admins: list[int], required_channels: list[str]):
    # Admins
    if main_admin:
        await add_admin(main_admin)
    for uid in secondary_admins:
        await add_admin(uid)
    # Channels
    existing = set(await list_channels())
    for ch in required_channels:
        if ch not in existing:
            await upsert_channel(ch)


# ---------- Users ----------
async def upsert_user(user_id: int, first_name: str, joined_at: datetime):
    async with pool.acquire() as con:
        await con.execute("""
            INSERT INTO users (user_id, first_name, joined_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET first_name = EXCLUDED.first_name;
        """, user_id, first_name, joined_at)


async def all_user_ids() -> list[int]:
    async with pool.acquire() as con:
        rows = await con.fetch("SELECT user_id FROM users")
        return [r["user_id"] for r in rows]


# ---------- Admins ----------
async def is_admin(user_id: int) -> bool:
    async with pool.acquire() as con:
        row = await con.fetchrow("SELECT 1 FROM admins WHERE user_id=$1", user_id)
        return row is not None


async def get_admin_ids() -> list[int]:
    async with pool.acquire() as con:
        rows = await con.fetch("SELECT user_id FROM admins")
        return [r["user_id"] for r in rows]


async def add_admin(user_id: int):
    async with pool.acquire() as con:
        await con.execute("""
            INSERT INTO admins (user_id) VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id)


async def remove_admin(user_id: int):
    async with pool.acquire() as con:
        await con.execute("DELETE FROM admins WHERE user_id=$1", user_id)


async def list_admins() -> list[int]:
    return await get_admin_ids()


# ---------- Free Stuff ----------
async def add_free_image(file_id: str, added_by: int | None):
    async with pool.acquire() as con:
        await con.execute("""
            INSERT INTO free_stuff (file_id, added_by) VALUES ($1, $2)
        """, file_id, added_by)


async def list_free_images() -> list[str]:
    async with pool.acquire() as con:
        rows = await con.fetch("SELECT file_id FROM free_stuff ORDER BY id ASC")
        return [r["file_id"] for r in rows]


# ---------- Channels ----------
async def list_channels() -> list[str]:
    async with pool.acquire() as con:
        rows = await con.fetch("SELECT ident FROM required_channels ORDER BY ident ASC")
        return [r["ident"] for r in rows]


async def upsert_channel(ident: str):
    ident = ident.strip()
    async with pool.acquire() as con:
        await con.execute("""
            INSERT INTO required_channels (ident) VALUES ($1)
            ON CONFLICT (ident) DO NOTHING
        """, ident)


async def delete_channel(ident: str):
    async with pool.acquire() as con:
        await con.execute("DELETE FROM required_channels WHERE ident=$1", ident)
