"""
LeadHunter Pro — Main Application
FastAPI backend serving the dashboard and running scrape jobs.
"""

import asyncio
import json
import math
import urllib.parse
import aiosqlite
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database as db
from scrapers.google_maps import scrape_google_maps, retry_failed_urls
from analyzer import batch_analyze_websites
from ai_engine import generate_lead_report  # AI only for detailed per-lead reports

# Track active search progress
search_progress = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield

app = FastAPI(title="LeadHunter Pro", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ─── Pages ────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    searches = await db.get_all_searches()
    return templates.TemplateResponse("index.html", {"request": request, "searches": searches})


@app.get("/crm/{search_id}", response_class=HTMLResponse)
async def crm_page(search_id: int, request: Request):
    search = await db.get_search_by_id(search_id)
    stats = await db.get_call_stats(search_id)
    return templates.TemplateResponse("crm.html", {
        "request": request, "search": search,
        "search_id": search_id, "stats": stats,
    })


# ─── API Endpoints ────────────────────────────────────────

@app.post("/api/search")
async def start_search(request: Request, background_tasks: BackgroundTasks):
    """Start a new lead generation search."""
    data = await request.json()
    query = data.get("query", "").strip()
    location = data.get("location", "").strip()
    radius_km = data.get("radius_km", 10)
    sources = data.get("sources", ["google_maps"])

    if not query or not location:
        return JSONResponse({"error": "Query and location are required"}, status_code=400)

    search_id = await db.create_search(query, location, radius_km)
    search_progress[search_id] = {
        "status": "starting",
        "stage": "initializing",
        "progress": 0,
        "total": 0,
        "message": "Starting search...",
        "logs": [],
    }

    background_tasks.add_task(run_search_pipeline, search_id, query, location, radius_km, sources)
    return {"search_id": search_id, "status": "started"}


@app.get("/api/search/{search_id}/progress")
async def get_search_progress(search_id: int):
    """SSE endpoint for real-time progress updates."""
    async def event_stream():
        while True:
            prog = search_progress.get(search_id, {})
            yield f"data: {json.dumps(prog)}\n\n"
            if prog.get("status") in ("completed", "error"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/search/{search_id}/leads")
async def get_leads(search_id: int, limit: int = 100, offset: int = 0):
    """Get leads for a search, sorted by AI score — paginated."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Get total count
        cursor = await conn.execute("SELECT COUNT(*) FROM leads WHERE search_id = ?", (search_id,))
        total = (await cursor.fetchone())[0]
        # Get paginated leads
        cursor = await conn.execute(
            "SELECT * FROM leads WHERE search_id = ? ORDER BY ai_ranking_score DESC, review_count DESC LIMIT ? OFFSET ?",
            (search_id, limit, offset))
        leads = [dict(r) for r in await cursor.fetchall()]
    return {"leads": leads, "total": total, "has_more": offset + limit < total}


@app.get("/api/lead/{lead_id}/report")
async def get_lead_report(lead_id: int):
    """Generate detailed AI report for a specific lead."""
    # Fetch lead from DB
    lead = None
    async with __import__('aiosqlite').connect(db.DB_PATH) as conn:
        conn.row_factory = __import__('aiosqlite').Row
        cursor = await conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = await cursor.fetchone()
        if row:
            lead = dict(row)

    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    report = await generate_lead_report(lead)
    return {"report": report}


@app.delete("/api/search/{search_id}")
async def delete_search(search_id: int):
    await db.delete_search(search_id)
    return {"status": "deleted"}


@app.post("/api/search/{search_id}/resume")
async def resume_search(search_id: int, background_tasks: BackgroundTasks):
    """Resume an interrupted search — runs website analysis + AI scoring on unprocessed leads."""
    search = await db.get_search_by_id(search_id)
    if not search:
        return JSONResponse({"error": "Search not found"}, status_code=404)

    saved = await db.get_lead_count(search_id)
    if saved == 0:
        return JSONResponse({"error": "No saved leads to resume"}, status_code=400)

    search_progress[search_id] = {
        "status": "running", "stage": "resuming", "progress": 0, "total": saved,
        "message": f"Resuming — {saved} leads found in database...", "logs": [],
    }

    background_tasks.add_task(resume_search_pipeline, search_id)
    return {"search_id": search_id, "status": "resuming", "saved_leads": saved}


async def resume_search_pipeline(search_id: int):
    """Resume pipeline — only runs website analysis and AI scoring on unprocessed leads."""
    try:
        search = await db.get_search_by_id(search_id)
        search_location = search["location"] if search else ""
        # Get leads that need processing
        unanalyzed = await db.get_unanalyzed_leads(search_id)
        unscored = await db.get_unscored_leads(search_id)
        total = await db.get_lead_count(search_id)

        async def progress_cb(stage, current, total_count, message):
            search_progress[search_id] = {
                "status": "running", "stage": stage,
                "progress": current, "total": total_count,
                "message": message,
                "logs": search_progress.get(search_id, {}).get("logs", []),
            }
            search_progress[search_id]["logs"].append(f"[{stage}] {message}")
            search_progress[search_id]["logs"] = search_progress[search_id]["logs"][-50:]

        # Website analysis on unanalyzed leads
        if unanalyzed:
            await progress_cb("website_analysis", 0, len(unanalyzed),
                              f"Analyzing {len(unanalyzed)} websites...")
            analyzed = await batch_analyze_websites(unanalyzed, progress_cb=progress_cb)
            for lead in analyzed:
                wa = lead.get("website_analysis")
                if wa and lead.get("id"):
                    wa_str = json.dumps(wa) if isinstance(wa, dict) else str(wa or "")
                    score = wa.get("overall_score", 0) if isinstance(wa, dict) else -1
                    await db.update_lead_website(lead["id"], score, wa_str)
            await progress_cb("website_analysis", len(unanalyzed), len(unanalyzed),
                              f"✅ Website analysis done for {len(unanalyzed)} leads")

        # Formula scoring on unscored leads (FREE, instant)
        if unscored:
            await progress_cb("scoring", 0, len(unscored),
                              f"Scoring {len(unscored)} leads (formula-based)...")
            for idx, lead in enumerate(unscored):
                result = _score_lead_formula(lead, location=search_location)
                if lead.get("id"):
                    await db.update_lead_ai(
                        lead["id"],
                        result["score"],
                        json.dumps({"verdict": result["verdict"], "pitch": result["pitch"], "reason": result["reason"]}),
                        1 if result["contact"] else 0,
                        result["size"],
                    )
            await progress_cb("scoring", len(unscored), len(unscored),
                              f"✅ {len(unscored)} leads scored (₹0 cost)")

        await db.update_search_status(search_id, "completed", total)
        search_progress[search_id] = {
            "status": "completed", "stage": "done",
            "progress": total, "total": total,
            "message": f"Resume complete! {total} leads fully processed.",
            "logs": search_progress.get(search_id, {}).get("logs", []),
        }

    except Exception as e:
        saved = await db.get_lead_count(search_id)
        print(f"[Resume] Error: {e}")
        search_progress[search_id] = {
            "status": "error", "stage": "error",
            "progress": saved, "total": saved,
            "message": f"Resume error: {str(e)} — {saved} leads still safe",
            "logs": search_progress.get(search_id, {}).get("logs", []),
        }

@app.post("/api/retry-failed/{search_id}")
async def retry_failed(search_id: int, background_tasks: BackgroundTasks):
    """Retry all failed URLs from the last search."""
    import os
    fail_file = os.path.join(os.path.dirname(__file__), "failed_urls.json")
    if not os.path.exists(fail_file):
        return JSONResponse({"error": "No failed URLs to retry"}, status_code=400)
    with open(fail_file) as f:
        failed = json.load(f)
    if not failed:
        return JSONResponse({"error": "No failed URLs to retry"}, status_code=400)

    search_progress[search_id] = {
        "status": "running", "stage": "retry", "progress": 0, "total": len(failed),
        "message": f"Retrying {len(failed)} failed URLs...", "logs": [],
    }
    background_tasks.add_task(retry_failed_pipeline, search_id)
    return {"search_id": search_id, "status": "retrying", "failed_count": len(failed)}


async def retry_failed_pipeline(search_id: int):
    """Retry failed URLs, save recovered leads, score them."""
    try:
        async def progress_cb(stage, current, total, message):
            search_progress[search_id] = {
                "status": "running", "stage": stage,
                "progress": current, "total": total, "message": message,
                "logs": search_progress.get(search_id, {}).get("logs", []),
            }
            search_progress[search_id]["logs"].append(f"[{stage}] {message}")
            search_progress[search_id]["logs"] = search_progress[search_id]["logs"][-50:]

        recovered = await retry_failed_urls(progress_cb=progress_cb)

        if recovered:
            recovered = [l for l in recovered if (l.get("review_count") or 0) >= MIN_REVIEWS]
            await progress_cb("saving", 0, len(recovered), f"Saving {len(recovered)} recovered leads...")
            for lead in recovered:
                lead_id = await db.insert_lead(search_id, lead)
                result = _score_lead_formula(lead, location=location)
                await db.update_lead_ai(lead_id, result["score"],
                    json.dumps({"verdict": result["verdict"], "pitch": result["pitch"], "reason": result["reason"]}),
                    1 if result["contact"] else 0, result["size"])

            total = await db.get_lead_count(search_id)
            await db.update_search_status(search_id, "completed", total)
            search_progress[search_id] = {
                "status": "completed", "stage": "done",
                "progress": total, "total": total,
                "message": f"✅ Recovered {len(recovered)} leads! Total: {total}",
                "logs": search_progress.get(search_id, {}).get("logs", []),
            }
        else:
            search_progress[search_id] = {
                "status": "completed", "stage": "done", "progress": 0, "total": 0,
                "message": "No leads could be recovered. Network may still be down.",
                "logs": search_progress.get(search_id, {}).get("logs", []),
            }

    except Exception as e:
        print(f"[Retry] Error: {e}")
        search_progress[search_id] = {
            "status": "error", "stage": "error", "progress": 0, "total": 0,
            "message": f"Retry error: {str(e)}",
            "logs": search_progress.get(search_id, {}).get("logs", []),
        }


@app.post("/api/search/{search_id}/rescan")
async def rescan_search(search_id: int, background_tasks: BackgroundTasks):
    """Re-run the same search but skip everything already in DB."""
    search = await db.get_search_by_id(search_id)
    if not search:
        return JSONResponse({"error": "Search not found"}, status_code=404)

    existing = await db.get_existing_identifiers(search_id)
    existing_count = len(existing["names"])

    search_progress[search_id] = {
        "status": "running", "stage": "google_maps", "progress": 0, "total": 0,
        "message": f"Re-scanning — skipping {existing_count} already known businesses...",
        "logs": [],
    }
    background_tasks.add_task(
        rescan_pipeline, search_id, search["query"], search["location"],
        existing["maps_urls"]
    )
    return {"search_id": search_id, "status": "rescanning", "existing": existing_count}


async def rescan_pipeline(search_id: int, query: str, location: str, skip_urls: set):
    """Re-run search, skip known URLs, save only new leads."""
    try:
        async def progress_cb(stage, current, total, message):
            saved_count = await db.get_lead_count(search_id)
            search_progress[search_id] = {
                "status": "running", "stage": stage,
                "progress": current, "total": total, "message": message,
                "saved": saved_count,
                "logs": search_progress.get(search_id, {}).get("logs", []),
            }
            search_progress[search_id]["logs"].append(f"[{stage}] {message}")
            search_progress[search_id]["logs"] = search_progress[search_id]["logs"][-50:]

        queries = [q.strip() for q in query.split(",") if q.strip()]
        new_leads = []

        for q_idx, single_query in enumerate(queries):
            await progress_cb("google_maps", q_idx, len(queries),
                              f"🔄 Re-scan '{single_query}' ({q_idx+1}/{len(queries)}) — skipping {len(skip_urls)} known")
            gm_leads, scraped_urls = await scrape_google_maps(
                single_query, location, max_results=99999,
                progress_cb=progress_cb, skip_urls=skip_urls,
                min_reviews=MIN_REVIEWS
            )
            skip_urls.update(scraped_urls)

            for lead in gm_leads:
                # Phase 1 already filtered <MIN_REVIEWS, but safety net for edge cases
                if (lead.get("review_count") or 0) < MIN_REVIEWS:
                    continue
                lead_id = await db.insert_lead(search_id, lead)
                lead["_db_id"] = lead_id
                new_leads.append(lead)

        # Score new leads
        if new_leads:
            await progress_cb("scoring", 0, len(new_leads), f"Scoring {len(new_leads)} new leads...")
            for lead in new_leads:
                result = _score_lead_formula(lead, location=location)
                if lead.get("_db_id"):
                    await db.update_lead_ai(
                        lead["_db_id"], result["score"],
                        json.dumps({"verdict": result["verdict"], "pitch": result["pitch"], "reason": result["reason"]}),
                        1 if result["contact"] else 0, result["size"],
                    )

        total = await db.get_lead_count(search_id)
        await db.update_search_status(search_id, "completed", total)
        search_progress[search_id] = {
            "status": "completed", "stage": "done",
            "progress": total, "total": total,
            "message": f"✅ Re-scan done! {len(new_leads)} NEW leads added. Total: {total}",
            "logs": search_progress.get(search_id, {}).get("logs", []),
        }

    except Exception as e:
        saved = await db.get_lead_count(search_id)
        print(f"[Rescan] Error: {e}")
        search_progress[search_id] = {
            "status": "error", "stage": "error", "progress": saved, "total": saved,
            "message": f"Re-scan error: {str(e)} — {saved} leads still safe",
            "logs": search_progress.get(search_id, {}).get("logs", []),
        }


@app.get("/api/export/{search_id}")
async def export_csv(search_id: int):
    """Export leads as CSV."""
    leads = await db.get_leads_by_search(search_id)
    if not leads:
        return JSONResponse({"error": "No leads found"}, status_code=404)

    import csv
    import io
    output = io.StringIO()
    fields = [
        "business_name", "category", "phone", "email", "website", "address",
        "rating", "review_count", "source", "ai_ranking_score", "business_size",
        "worth_contacting", "website_score", "website_verdict",
        "recommendation_count", "google_business_url", "google_search_url",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        # Extract Google Business URL and website verdict from stored data
        try:
            raw = json.loads(lead.get("raw_data") or "{}")
            lead["google_business_url"] = raw.get("maps_url", "")
        except Exception:
            lead["google_business_url"] = ""
        # Google Search link (shows Knowledge Panel)
        bname = lead.get("business_name", "")
        addr = lead.get("address", "")
        lead["google_search_url"] = f"https://www.google.com/search?q={urllib.parse.quote(f'{bname} {addr}')}" if bname else ""
        # Website analysis verdict
        try:
            wa = json.loads(lead.get("website_analysis") or "{}")
            lead["website_verdict"] = wa.get("verdict", "")
            lead["recommendation_count"] = wa.get("recommendation_count", 0)
        except Exception:
            lead["website_verdict"] = ""
            lead["recommendation_count"] = 0
        writer.writerow(lead)

    output.seek(0)
    search = await db.get_search_by_id(search_id)
    # Sanitize filename — remove commas and special chars that break headers
    safe_query = search['query'].replace(",", "_").replace(" ", "_")[:50]
    safe_loc = search['location'].replace(",", "_").replace(" ", "_")
    filename = f"leads_{safe_query}_{safe_loc}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Calling CRM API ──────────────────────────────────────

@app.get("/api/search/{search_id}/next-call")
async def get_next_call(search_id: int):
    """Get the next lead to call (highest score first, uncalled only)."""
    lead = await db.get_next_callable_lead(search_id)
    stats = await db.get_call_stats(search_id)
    if not lead:
        return JSONResponse({"done": True, "stats": stats, "message": "All leads have been called! 🎉"})
    # Parse website analysis for display
    wa = {}
    try:
        wa = json.loads(lead.get("website_analysis") or "{}")
    except Exception:
        pass
    raw = {}
    try:
        raw = json.loads(lead.get("raw_data") or "{}")
    except Exception:
        pass
    return JSONResponse({
        "done": False, "stats": stats, "lead": lead,
        "website_report": wa, "maps_url": raw.get("maps_url", ""),
    })


@app.post("/api/lead/{lead_id}/call-status")
async def set_call_status(lead_id: int, request: Request):
    """Update a lead's call status and optional notes."""
    body = await request.json()
    status = body.get("status", "")
    notes = body.get("notes", "")
    if status not in ("", "hot", "not_happening", "not_picked", "transferred", "call_later"):
        return JSONResponse({"error": "Invalid status"}, status_code=400)
    await db.update_call_status(lead_id, status, notes)
    return JSONResponse({"ok": True})


@app.get("/api/search/{search_id}/call-stats")
async def get_call_stats(search_id: int):
    """Get calling stats for a search."""
    stats = await db.get_call_stats(search_id)
    return JSONResponse(stats)


@app.get("/api/search/{search_id}/leads-by-status")
async def get_leads_by_status(search_id: int, status: str = "all", limit: int = 100, offset: int = 0):
    """Get leads filtered by call status for CRM tabs — paginated."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if status == "all":
            cursor = await conn.execute(
                "SELECT * FROM leads WHERE search_id = ? ORDER BY ai_ranking_score DESC, review_count DESC LIMIT ? OFFSET ?",
                (search_id, limit, offset))
        elif status == "pending":
            cursor = await conn.execute(
                "SELECT * FROM leads WHERE search_id = ? AND (call_status IS NULL OR call_status = '') ORDER BY ai_ranking_score DESC, review_count DESC LIMIT ? OFFSET ?",
                (search_id, limit, offset))
        else:
            cursor = await conn.execute(
                "SELECT * FROM leads WHERE search_id = ? AND call_status = ? ORDER BY ai_ranking_score DESC, review_count DESC LIMIT ? OFFSET ?",
                (search_id, status, limit, offset))
        rows = await cursor.fetchall()
        leads = [dict(r) for r in rows]
    return JSONResponse({"leads": leads, "count": len(leads), "has_more": len(leads) == limit})


# ─── Search Pipeline (Crash-Safe) ─────────────────────────

MIN_REVIEWS = 20  # Skip businesses with fewer than this many Google reviews

async def run_search_pipeline(search_id: int, query: str, location: str, radius_km: int, sources: list):
    """
    Main pipeline with INCREMENTAL SAVING.
    Every lead is saved to DB immediately after scraping.
    Website analysis and AI scoring UPDATE existing records.
    If process crashes, all scraped leads are preserved.
    """
    all_leads = []  # in-memory copy with DB IDs

    async def progress_cb(stage, current, total, message):
        saved_count = await db.get_lead_count(search_id)
        search_progress[search_id] = {
            "status": "running",
            "stage": stage,
            "progress": current,
            "total": total,
            "message": message,
            "saved": saved_count,
            "logs": search_progress.get(search_id, {}).get("logs", []),
        }
        search_progress[search_id]["logs"].append(f"[{stage}] {message}")
        search_progress[search_id]["logs"] = search_progress[search_id]["logs"][-50:]

    try:
        # Split comma-separated queries
        queries = [q.strip() for q in query.split(",") if q.strip()]
        total_queries = len(queries)

        # ══════════════════════════════════════════════
        # Stage 1: Google Maps → SAVE IMMEDIATELY
        # ══════════════════════════════════════════════
        if "google_maps" in sources:
            known_urls = set()  # URLs already scraped by previous queries

            for q_idx, single_query in enumerate(queries):
                remaining_q = total_queries - q_idx
                await progress_cb("google_maps", q_idx, total_queries,
                                  f"🗺️ Query {q_idx+1}/{total_queries}: '{single_query}' ({remaining_q} queries left, {len(all_leads)} leads so far, skipping {len(known_urls)} already known)")

                # Pass known URLs so Phase 1 skips them entirely
                gm_leads, scraped_urls = await scrape_google_maps(
                    single_query, location, max_results=99999,
                    progress_cb=progress_cb, skip_urls=known_urls,
                    min_reviews=MIN_REVIEWS
                )

                # Merge Phase 1 URLs into known set (these match Phase 1 URLs of next query)
                known_urls.update(scraped_urls)

                # Phase 1 already filtered <MIN_REVIEWS at URL level — safety net re-check
                qualified = [l for l in gm_leads if (l.get("review_count") or 0) >= MIN_REVIEWS]
                skipped = len(gm_leads) - len(qualified)
                await progress_cb("saving", 0, len(qualified),
                                  f"Saving '{single_query}': {len(qualified)} qualified, {skipped} filtered in Phase 2 safety check...")
                for lead in qualified:
                    lead_id = await db.insert_lead(search_id, lead)
                    lead["_db_id"] = lead_id
                    all_leads.append(lead)

                await db.update_search_status(search_id, "running", len(all_leads))
                await progress_cb("saving", q_idx + 1, total_queries,
                                  f"✅ '{single_query}': +{len(qualified)} leads saved ({skipped} filtered), total: {len(all_leads)}")


        if not all_leads:
            await db.update_search_status(search_id, "completed", 0)
            search_progress[search_id] = {
                "status": "completed", "stage": "done", "progress": 0, "total": 0,
                "message": "No leads found. Try a different search query or location.",
                "logs": search_progress.get(search_id, {}).get("logs", []),
            }
            return

        # ══════════════════════════════════════════════
        # Stage 3: Deduplicate
        # ══════════════════════════════════════════════
        await progress_cb("dedup", 0, 0, "Removing duplicates...")
        before_count = len(all_leads)
        all_leads = _deduplicate_leads(all_leads)
        removed = before_count - len(all_leads)

        # Delete duplicate records from DB
        if removed > 0:
            kept_ids = {l["_db_id"] for l in all_leads if l.get("_db_id")}
            all_db_leads = await db.get_leads_by_search(search_id)
            for db_lead in all_db_leads:
                if db_lead["id"] not in kept_ids:
                    await db.delete_lead(db_lead["id"])

        await progress_cb("dedup", len(all_leads), len(all_leads),
                          f"{len(all_leads)} unique leads ({removed} duplicates removed)")

        # ══════════════════════════════════════════════
        # Stage 4: Website Analysis → UPDATE DB records
        # ══════════════════════════════════════════════
        leads_with_sites = [l for l in all_leads if l.get("website")]
        if leads_with_sites:
            await progress_cb("website_analysis", 0, len(leads_with_sites), "Analyzing websites...")
            all_leads = await batch_analyze_websites(all_leads, progress_cb=progress_cb)

            for lead in all_leads:
                if lead.get("_db_id") and lead.get("website_analysis"):
                    wa = lead["website_analysis"]
                    wa_str = json.dumps(wa) if isinstance(wa, dict) else str(wa or "")
                    score = wa.get("overall_score", 0) if isinstance(wa, dict) else lead.get("website_score", -1)
                    await db.update_lead_website(lead["_db_id"], score, wa_str)

            await progress_cb("website_analysis", len(leads_with_sites), len(leads_with_sites),
                              f"✅ Website analysis SAVED for {len(leads_with_sites)} leads")

        # ══════════════════════════════════════════════
        # Stage 5: Formula Scoring (FREE — no AI tokens!)
        # ══════════════════════════════════════════════
        await progress_cb("scoring", 0, len(all_leads), "Scoring leads (formula-based, instant)...")

        for idx, lead in enumerate(all_leads):
            result = _score_lead_formula(lead, location=location)
            lead["ai_ranking_score"] = result["score"]
            lead["ai_analysis"] = json.dumps({
                "verdict": result["verdict"],
                "pitch": result["pitch"],
                "reason": result["reason"],
            })
            lead["worth_contacting"] = 1 if result["contact"] else 0
            lead["business_size"] = result["size"]

            # Update DB
            if lead.get("_db_id"):
                await db.update_lead_ai(
                    lead["_db_id"],
                    result["score"],
                    lead["ai_analysis"],
                    lead["worth_contacting"],
                    result["size"],
                )

        await progress_cb("scoring", len(all_leads), len(all_leads),
                          f"✅ {len(all_leads)} leads scored (zero AI cost!)")

        # ══════════════════════════════════════════════
        # Done
        # ══════════════════════════════════════════════
        await db.update_search_status(search_id, "completed", len(all_leads))
        search_progress[search_id] = {
            "status": "completed", "stage": "done",
            "progress": len(all_leads), "total": len(all_leads),
            "message": f"Done! {len(all_leads)} leads scored and SAVED. (₹0 AI cost)",
            "logs": search_progress.get(search_id, {}).get("logs", []),
        }

    except Exception as e:
        saved = await db.get_lead_count(search_id)
        print(f"[Pipeline] Error: {e} — {saved} leads were already saved")
        await db.update_search_status(search_id, "error", saved)
        search_progress[search_id] = {
            "status": "error", "stage": "error", "progress": saved, "total": saved,
            "message": f"Error: {str(e)} — but {saved} leads were already saved!",
            "logs": search_progress.get(search_id, {}).get("logs", []),
        }


def _deduplicate_leads(leads: list) -> list:
    """Remove duplicate leads based on phone or business name similarity."""
    seen_phones = set()
    seen_names = set()
    unique = []

    for lead in leads:
        phone = (lead.get("phone") or "").replace(" ", "").replace("-", "")
        name = (lead.get("business_name") or "").lower().strip()

        if phone and phone in seen_phones:
            continue
        if name and name in seen_names:
            continue

        if phone:
            seen_phones.add(phone)
        if name:
            seen_names.add(name)
        unique.append(lead)

    return unique


# ── Scoring Constants (module-level for performance) ───────

_HIGH_VALUE_CATEGORIES = frozenset([
    "dentist", "doctor", "clinic", "hospital", "dermatolog", "orthoped", "pediatr",
    "salon", "spa", "beauty", "bridal", "makeup", "nail",
    "restaurant", "cafe", "bakery", "catering", "sweet", "ice cream",
    "lawyer", "advocate", "chartered accountant", "consultant", "tax",
    "interior", "architect", "real estate", "builder", "construction",
    "gym", "fitness", "yoga", "zumba", "martial art",
    "hotel", "resort", "boutique", "banquet",
    "jewel", "optical", "photography", "studio",
    "school", "coaching", "academy", "institute",
    "car wash", "car service", "auto",
])

_FREE_WEBSITE_MARKERS = (
    "wix.com", "wixsite.com", "wordpress.com", "weebly.com",
    "godaddy.com", "sites.google.com", "google.com/site",
    "blogspot.com", "squarespace.com", "jimdo.com",
    "facebook.com", "fb.com", "instagram.com",
    "justdial.com", "indiamart.com", "sulekha.com",
    "practo.com", "lybrate.com", "zomato.com", "swiggy.com",
)

_NAME_PREMIUM_KEYWORDS = (
    "dr ", "dr.", "hospital", "clinic", "dental", "ortho",
    "luxury", "premium", "international", "global",
    "the ", "studio", "academy", "institute",
)

# Cache for area tier lookups (city → {area_lower: tier})
_area_tier_cache = {}

def _build_area_cache(location: str):
    """Build a flat lookup dict for O(1) area tier matching."""
    from area_data import CITY_AREAS
    loc = location.lower().strip()
    if loc in _area_tier_cache:
        return
    cache = {}
    for city_key, tiers in CITY_AREAS.items():
        if city_key in loc or loc in city_key:
            for tier, areas in tiers.items():
                for area in areas:
                    cache[area.lower()] = tier
            break
    _area_tier_cache[loc] = cache


def _get_area_tier_fast(location: str, address: str) -> int:
    """O(1) area tier lookup using cached flat dict."""
    loc = location.lower().strip()
    if loc not in _area_tier_cache:
        _build_area_cache(location)
    cache = _area_tier_cache.get(loc, {})
    if not cache:
        return 0
    addr_lower = address.lower()
    # Check each cached area against the address
    for area_name, tier in cache.items():
        if area_name in addr_lower:
            return tier
    return 0


def _detect_website_type(website: str) -> str:
    """Classify website quality by URL alone."""
    if not website:
        return "none"
    w = website.lower()
    for marker in _FREE_WEBSITE_MARKERS:
        if marker in w:
            return "free_or_listing"  # Free builder or directory listing
    return "custom"  # Likely a real custom domain


def _score_lead_formula(lead: dict, location: str = "") -> dict:
    """
    LeadHunter Pro — Comprehensive Lead Scoring Algorithm v3
    
    7 Scoring Pillars:
      1. Website Opportunity    (0-35 pts) — No site / free site / bad site = gold
      2. Business Credibility   (0-20 pts) — Reviews (logarithmic), rating
      3. Area Affluence         (0-20 pts) — Tier 1 posh area = high buyer intent
      4. Conversion Signals     (0-15 pts) — Ads, claimed listing, photos, phone
      5. Category Match         (0-5 pts)  — High-value service categories
      6. Business Name Intel    (0-5 pts)  — "Dr.", "Hospital" = premium client
      7. Penalties              (up to -20) — Closed, ghost, unreachable
    
    Max theoretical: 100 | Min: 5 | Sweet spot: 70-95 = call immediately
    """

    website = lead.get("website", "") or ""
    has_website = bool(website)
    website_type = _detect_website_type(website)
    website_score = lead.get("website_score", -1)
    reviews = lead.get("review_count", 0) or 0
    rating = lead.get("rating", 0) or 0
    phone = lead.get("phone", "")
    address = lead.get("address", "") or ""
    category = lead.get("category", "") or ""
    name = lead.get("business_name", "") or ""
    is_running_ads = lead.get("is_running_ads", False)
    is_claimed = lead.get("is_claimed", False)
    photo_count = lead.get("photo_count", 0) or 0
    is_closed = lead.get("is_permanently_closed", False)

    points = 0

    # ══════════════════════════════════════════════
    # 1. WEBSITE OPPORTUNITY (0-35 pts)
    # Free/listing sites count as "almost no website"
    # ══════════════════════════════════════════════
    if not has_website:
        points += 35  # No website = maximum opportunity
    elif website_type == "free_or_listing":
        # Wix/WordPress.com/Facebook/Practo = not a real website
        points += 30  # Almost as good as no website — easy "upgrade to real site" pitch
    elif website_score >= 0:
        if website_score < 20:
            points += 32  # Terrible custom website
        elif website_score < 35:
            points += 27  # Bad website — easy redesign sell
        elif website_score < 50:
            points += 20  # Below average
        elif website_score < 65:
            points += 12  # Average
        elif website_score < 80:
            points += 5   # Good website — hard sell
        else:
            points += 0   # Great website — skip
    else:
        points += 28  # Has website but couldn't analyze — likely broken

    # ══════════════════════════════════════════════
    # 2. BUSINESS CREDIBILITY (0-20 pts)
    # Logarithmic scaling — diminishing returns above 500 reviews
    # 20 reviews → 6pts, 100 → 12pts, 500 → 16pts, 1000 → 18pts
    # ══════════════════════════════════════════════
    if reviews >= 20:
        review_pts = min(18, int(4 * math.log2(reviews / 5)))
        points += review_pts
    else:
        points += 2  # Under minimum, almost no credibility signal

    if reviews >= 1000: size = "enterprise"
    elif reviews >= 500: size = "large"
    elif reviews >= 200: size = "medium_large"
    elif reviews >= 100: size = "medium"
    elif reviews >= 50:  size = "small_medium"
    elif reviews >= 20:  size = "small"
    else: size = "micro"

    # Rating quality (combined with reviews for reliability)
    if rating >= 4.5 and reviews >= 100:
        points += 5   # Premium business — verified by volume
    elif rating >= 4.3 and reviews >= 50:
        points += 4
    elif rating >= 4.0 and reviews >= 30:
        points += 3
    elif rating >= 4.0:
        points += 2
    elif rating >= 3.5:
        points += 1
    elif 0 < rating < 3.0:
        points -= 5   # Low rated — risky client, bigger problems than website

    # ══════════════════════════════════════════════
    # 3. AREA AFFLUENCE (0-20 pts) — cached O(1) lookup
    # ══════════════════════════════════════════════
    area_tier = _get_area_tier_fast(location, address) if location else 0

    if area_tier == 1:
        area_pts = 20
    elif area_tier == 2:
        area_pts = 13
    elif area_tier == 3:
        area_pts = 6
    else:
        area_pts = 9

    # Cap area bonus if business already has a great website
    # (Premium area + great site = they don't need us, area shouldn't inflate score)
    if website_score >= 75:
        area_pts = min(area_pts, 5)  # Max +5 from area if site is already good

    points += area_pts

    # ══════════════════════════════════════════════
    # 4. CONVERSION SIGNALS (0-15 pts)
    # ══════════════════════════════════════════════
    if phone:
        points += 4   # Reachable

    if is_running_ads:
        points += 8   # HUGE signal — already spending on digital marketing

    if is_claimed:
        points += 2   # Actively manages their listing = digitally aware

    if photo_count >= 50:
        points += 3   # Very engaged with their listing
    elif photo_count >= 20:
        points += 2
    elif photo_count >= 5:
        points += 1

    # ══════════════════════════════════════════════
    # 5. CATEGORY MATCH (0-5 pts)
    # ══════════════════════════════════════════════
    cat_lower = category.lower()
    name_lower = name.lower()

    if any(kw in cat_lower for kw in _HIGH_VALUE_CATEGORIES):
        points += 5

    # Low-value categories — these businesses rarely buy websites
    low_value = ["grocery", "kirana", "general store", "pan shop", "paan",
                 "stationery", "hardware", "scrap", "laundry", "dhob",
                 "tailor", "cobbler", "plumber", "electrician", "mechanic"]
    if any(kw in cat_lower for kw in low_value) or any(kw in name_lower for kw in low_value):
        points -= 12  # These businesses have ₹0 website budget

    # ══════════════════════════════════════════════
    # 6. BUSINESS NAME INTELLIGENCE (0-5 pts)
    # ══════════════════════════════════════════════
    if any(kw in name_lower for kw in _NAME_PREMIUM_KEYWORDS):
        points += 3  # Premium-sounding business

    # Multi-location chains have budget
    if any(w in name_lower for w in ("chain", "group", "& sons", "pvt", "ltd", "llp")):
        points += 2

    # ══════════════════════════════════════════════
    # 7. PENALTIES
    # ══════════════════════════════════════════════
    if is_closed:
        points -= 50  # Permanently closed — absolute skip

    if not phone and not has_website:
        points -= 5   # Unreachable

    if reviews < 5 and rating == 0:
        points -= 10  # Ghost listing

    # ══════════════════════════════════════════════
    # FINAL SCORE
    # ══════════════════════════════════════════════
    score = max(5, min(98, points))

    # Verdict thresholds
    if score >= 75:
        verdict = "HOT"
    elif score >= 55:
        verdict = "WARM"
    elif score >= 35:
        verdict = "COLD"
    else:
        verdict = "SKIP"

    # Smart contextual pitch
    tier_label = {1: "premium", 2: "good", 3: "mid-tier"}.get(area_tier, "")
    area_note = f" in {tier_label} area" if tier_label else ""
    ads_note = " + running Google Ads" if is_running_ads else ""

    if is_closed:
        pitch = "⛔ Permanently closed — skip."
    elif not has_website or website_type == "free_or_listing":
        site_note = "No website" if not has_website else f"Only {website_type.replace('_', ' ')} site"
        if reviews >= 200:
            pitch = f"{site_note}{area_note}{ads_note} — {reviews} reviews, established business. Easiest close."
        elif reviews >= 50:
            pitch = f"{site_note} + {reviews} reviews{area_note}{ads_note} — ready for a real website."
        else:
            pitch = f"{site_note}{area_note} — pitch starter package."
    elif website_score < 35:
        pitch = f"Poor website ({website_score}/100){area_note}{ads_note} — redesign opportunity."
    elif website_score < 60:
        pitch = f"Average website ({website_score}/100){area_note} — upgrade potential."
    else:
        pitch = f"Decent website ({website_score}/100){area_note} — focus on specific improvements."

    contact = score >= 45

    return {
        "score": score,
        "size": size,
        "verdict": verdict,
        "contact": contact,
        "pitch": pitch,
        "area_tier": area_tier,
        "reason": f"web={'none' if not has_website else website_type}({website_score}), "
                  f"rev={reviews}, rat={rating}, tier={area_tier}, "
                  f"ads={'Y' if is_running_ads else 'N'}, photos={photo_count}",
    }


# ─── Run ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
