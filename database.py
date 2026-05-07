"""
Database module for LeadHunter Pro
Handles all SQLite operations for storing leads and search history.
"""

import aiosqlite
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "leadhunter.db")


async def init_db():
    """Initialize the database with required tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                location TEXT NOT NULL,
                radius_km INTEGER DEFAULT 10,
                status TEXT DEFAULT 'pending',
                total_leads INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_id INTEGER NOT NULL,
                business_name TEXT,
                owner_name TEXT,
                phone TEXT,
                email TEXT,
                website TEXT,
                address TEXT,
                city TEXT,
                rating REAL,
                review_count INTEGER DEFAULT 0,
                category TEXT,
                source TEXT,
                website_score INTEGER,
                website_analysis TEXT,
                ai_ranking_score INTEGER,
                ai_analysis TEXT,
                worth_contacting INTEGER DEFAULT 1,
                business_size TEXT,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (search_id) REFERENCES searches(id)
            )
        """)
        # Migration: add call tracking columns (safe for existing DB)
        for col, typedef in [("call_status", "TEXT"), ("call_notes", "TEXT")]:
            try:
                await db.execute(f"ALTER TABLE leads ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # Column already exists
        await db.commit()


async def create_search(query: str, location: str, radius_km: int) -> int:
    """Create a new search record and return its ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO searches (query, location, radius_km, status) VALUES (?, ?, ?, 'running')",
            (query, location, radius_km),
        )
        await db.commit()
        return cursor.lastrowid


async def update_search_status(search_id: int, status: str, total_leads: int = 0):
    """Update search status."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE searches SET status = ?, total_leads = ? WHERE id = ?",
            (status, total_leads, search_id),
        )
        await db.commit()


async def insert_lead(search_id: int, lead_data: dict) -> int:
    """Insert a new lead into the database immediately."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO leads (
                search_id, business_name, owner_name, phone, email, website,
                address, city, rating, review_count, category, source,
                website_score, website_analysis, ai_ranking_score, ai_analysis,
                worth_contacting, business_size, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                search_id,
                lead_data.get("business_name", ""),
                lead_data.get("owner_name", ""),
                lead_data.get("phone", ""),
                lead_data.get("email", ""),
                lead_data.get("website", ""),
                lead_data.get("address", ""),
                lead_data.get("city", ""),
                lead_data.get("rating", 0),
                lead_data.get("review_count", 0),
                lead_data.get("category", ""),
                lead_data.get("source", ""),
                lead_data.get("website_score", -1),
                lead_data.get("website_analysis", ""),
                lead_data.get("ai_ranking_score", 0),
                lead_data.get("ai_analysis", ""),
                lead_data.get("worth_contacting", 1),
                lead_data.get("business_size", "unknown"),
                json.dumps({
                    "maps_url": lead_data.get("maps_url", ""),
                    "is_running_ads": lead_data.get("is_running_ads", False),
                }),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def update_lead_website(lead_id: int, website_score: int, website_analysis: str):
    """Update a lead's website analysis (incremental save)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE leads SET website_score = ?, website_analysis = ? WHERE id = ?",
            (website_score, website_analysis, lead_id),
        )
        await db.commit()


async def update_lead_ai(lead_id: int, ai_ranking_score: int, ai_analysis: str,
                         worth_contacting: int, business_size: str):
    """Update a lead's AI scoring (incremental save)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE leads SET ai_ranking_score = ?, ai_analysis = ?,
               worth_contacting = ?, business_size = ? WHERE id = ?""",
            (ai_ranking_score, ai_analysis, worth_contacting, business_size, lead_id),
        )
        await db.commit()


async def get_leads_by_search(search_id: int) -> list:
    """Get all leads for a specific search, ordered by AI ranking."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM leads WHERE search_id = ? ORDER BY ai_ranking_score DESC, review_count DESC",
            (search_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_unscored_leads(search_id: int) -> list:
    """Get leads that haven't been AI-scored yet."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM leads WHERE search_id = ? AND ai_ranking_score = 0",
            (search_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_unanalyzed_leads(search_id: int) -> list:
    """Get leads with websites that haven't been analyzed yet."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM leads WHERE search_id = ? AND website != '' AND website_score = -1",
            (search_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_lead_count(search_id: int) -> int:
    """Get count of leads for a search."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM leads WHERE search_id = ?", (search_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_all_searches() -> list:
    """Get all search history."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM searches ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_search_by_id(search_id: int) -> dict:
    """Get a specific search by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM searches WHERE id = ?", (search_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_search(search_id: int):
    """Delete a search and all its leads."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM leads WHERE search_id = ?", (search_id,))
        await db.execute("DELETE FROM searches WHERE id = ?", (search_id,))
        await db.commit()


async def delete_lead(lead_id: int):
    """Delete a single lead (used during dedup)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        await db.commit()


async def get_existing_identifiers(search_id: int) -> dict:
    """Get phones and business names already in DB for this search (for re-scan dedup)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT phone, business_name, raw_data FROM leads WHERE search_id = ?",
            (search_id,)
        )
        rows = await cursor.fetchall()

    phones = set()
    names = set()
    maps_urls = set()
    for row in rows:
        r = dict(row)
        if r.get("phone"):
            phones.add(r["phone"].replace(" ", "").replace("-", ""))
        if r.get("business_name"):
            names.add(r["business_name"].lower().strip())
        try:
            raw = json.loads(r.get("raw_data") or "{}")
            if raw.get("maps_url"):
                maps_urls.add(raw["maps_url"].split("?")[0])
        except Exception:
            pass

    return {"phones": phones, "names": names, "maps_urls": maps_urls}


# ─── Calling CRM Functions ────────────────────────────────

async def get_next_callable_lead(search_id: int, offset: int = 0):
    """Get next lead that hasn't been called yet, sorted by score (best first)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM leads
            WHERE search_id = ? AND (call_status IS NULL OR call_status = '')
            ORDER BY ai_ranking_score DESC, review_count DESC
            LIMIT 1 OFFSET ?
        """, (search_id, offset))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_call_stats(search_id: int):
    """Get call status counts for a search."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN call_status IS NULL OR call_status = '' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN call_status = 'hot' THEN 1 ELSE 0 END) as hot,
                SUM(CASE WHEN call_status = 'call_later' THEN 1 ELSE 0 END) as call_later,
                SUM(CASE WHEN call_status = 'not_happening' THEN 1 ELSE 0 END) as not_happening,
                SUM(CASE WHEN call_status = 'not_picked' THEN 1 ELSE 0 END) as not_picked,
                SUM(CASE WHEN call_status = 'transferred' THEN 1 ELSE 0 END) as transferred
            FROM leads WHERE search_id = ?
        """, (search_id,))
        row = await cursor.fetchone()
        return {
            "total": row[0] or 0, "pending": row[1] or 0,
            "hot": row[2] or 0, "call_later": row[3] or 0,
            "not_happening": row[4] or 0,
            "not_picked": row[5] or 0, "transferred": row[6] or 0,
        }


async def update_call_status(lead_id: int, status: str, notes: str = ""):
    """Update a lead's call status and notes. Preserves existing notes if none provided."""
    async with aiosqlite.connect(DB_PATH) as db:
        if notes:
            await db.execute(
                "UPDATE leads SET call_status = ?, call_notes = ? WHERE id = ?",
                (status, notes, lead_id),
            )
        else:
            await db.execute(
                "UPDATE leads SET call_status = ? WHERE id = ?",
                (status, lead_id),
            )
        await db.commit()


async def get_leads_by_call_status(search_id: int, status: str):
    """Get all leads with a specific call status."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM leads WHERE search_id = ? AND call_status = ? ORDER BY ai_ranking_score DESC, review_count DESC",
            (search_id, status),
        )
        return [dict(r) for r in await cursor.fetchall()]

