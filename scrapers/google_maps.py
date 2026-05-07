"""
LeadHunter Pro — Google Maps Scraper (v5 — Ranked Areas + CAPTCHA Protection)
Phase 1: Collect all place URLs across ranked areas (premium first)
Phase 2: Visit each place to extract full details (reliable)
"""

import asyncio
import json
import os
import random
import urllib.parse
from playwright.async_api import async_playwright
from config import USER_AGENTS, HEADLESS
from area_data import get_ranked_areas

FAILED_URLS_FILE = os.path.join(os.path.dirname(__file__), "..", "failed_urls.json")


def _get_sub_areas(location: str, max_tier: int = 2) -> list:
    """Get areas ranked by affluence — premium first."""
    areas = get_ranked_areas(location, max_tier=max_tier)
    if areas:
        return areas
    # Fallback: treat the location itself as the only area
    return [location]


PARALLEL_WORKERS = 8  # 32GB RAM PC — 8 pages at once

CAPTCHA_CHECK_JS = '''() => {
    const body = document.body ? document.body.innerText : '';
    const url = window.location.href;
    if (url.includes('sorry/index') || url.includes('recaptcha') ||
        body.includes('unusual traffic') || body.includes('automated queries') ||
        body.includes('not a robot') || document.querySelector('iframe[src*="recaptcha"]') ||
        document.querySelector('#captcha-form') || document.querySelector('.g-recaptcha'))
        return true;
    return false;
}'''


# ── Shared JS for extracting place data ────────────────────
EXTRACT_PLACE_JS = '''() => {
    const r = {business_name:'', address:'', phone:'', website:'',
               rating:0, review_count:0, category:'',
               maps_url: window.location.href,
               is_running_ads: false, is_claimed: false,
               photo_count: 0, is_permanently_closed: false};

    const h1 = document.querySelector('h1');
    r.business_name = h1 ? h1.innerText.trim() : '';

    const rat = document.querySelector('div.F7nice span[aria-hidden="true"]');
    if (rat) r.rating = parseFloat(rat.textContent) || 0;

    const revs = document.querySelectorAll('div.F7nice span');
    for (const s of revs) {
        const m = s.textContent.match(/\(([\d,]+)\)/);
        if (m) { r.review_count = parseInt(m[1].replace(/,/g,'')) || 0; break; }
    }

    const cat = document.querySelector('button.DkEaL');
    if (cat) r.category = cat.textContent.trim();

    const btns = document.querySelectorAll('button[data-item-id]');
    for (const btn of btns) {
        const did = btn.getAttribute('data-item-id') || '';
        const el = btn.querySelector('.Io6YTe');
        const txt = el ? el.textContent.trim() : '';
        if (!txt) continue;
        if (did.startsWith('address') || did.startsWith('oloc')) r.address = txt;
        else if (did.startsWith('phone:')) r.phone = txt;
    }

    const web = document.querySelector('a[data-item-id="authority"]');
    if (web) r.website = web.href;

    // New signals for scoring v3
    r.is_running_ads = !!document.querySelector('[data-ads-creative-id]');
    r.is_claimed = !!document.querySelector('[data-attrid="kc:/local:claimed"]') ||
                   !!document.querySelector('.Qty3Ue') ||
                   document.body.innerText.includes('Claimed');
    r.is_permanently_closed = document.body.innerText.includes('Permanently closed');

    // Photo count (engagement signal)
    const photoBtn = document.querySelector('button[aria-label*="photo"]');
    if (photoBtn) {
        const pm = photoBtn.getAttribute('aria-label').match(/([\d,]+)/);
        if (pm) r.photo_count = parseInt(pm[1].replace(/,/g,'')) || 0;
    }

    return r;
}'''


async def scrape_google_maps(query: str, location: str, max_results: int = 200, progress_cb=None, skip_urls: set = None):
    all_results = []
    seen_urls = set(skip_urls or set())
    all_place_urls = []
    failed_urls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)

        try:
            sub_areas = _get_sub_areas(location)
            searches = [f"{area}, {location}" for area in sub_areas] if sub_areas else [location]

            # ═══════════════════════════════════════════════
            # PHASE 1: Parallel URL collection (3 workers)
            # ═══════════════════════════════════════════════
            if progress_cb:
                await progress_cb("google_maps", 0, len(searches),
                                  f"Phase 1: Scanning {len(searches)} areas with {PARALLEL_WORKERS} workers for '{query}'...")

            # Split areas into chunks for parallel processing
            area_chunks = [[] for _ in range(PARALLEL_WORKERS)]
            for i, s in enumerate(searches):
                area_chunks[i % PARALLEL_WORKERS].append((i, s))

            phase1_progress = {"done": 0, "total": len(searches), "urls_found": 0}

            async def phase1_worker(worker_id, area_list):
                """One worker scanning its assigned areas."""
                context = await browser.new_context(
                    user_agent=USER_AGENTS[worker_id % len(USER_AGENTS)],
                    viewport={"width": 1280 + worker_id * 40, "height": 720 + worker_id * 20},
                    locale="en-IN", timezone_id="Asia/Kolkata",
                )
                page = await context.new_page()
                await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,mp4,webp}",
                                 lambda route: route.abort())
                worker_urls = []
                consent_handled = False

                for area_idx, search_loc in area_list:
                    search_term = f"{query} in {search_loc}"
                    url = f"https://www.google.com/maps/search/{urllib.parse.quote(search_term)}"

                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        await asyncio.sleep(random.uniform(2.0 + worker_id * 0.3, 3.5 + worker_id * 0.3))

                        # Handle consent popup once per worker
                        if not consent_handled:
                            for sel in ['button:has-text("Accept all")', 'button[aria-label="Accept all"]',
                                        'button:has-text("Accept")', 'form[action*="consent"] button']:
                                try:
                                    btn = await page.query_selector(sel)
                                    if btn:
                                        await btn.click()
                                        await asyncio.sleep(1.5)
                                        consent_handled = True
                                        break
                                except Exception:
                                    continue

                        # CAPTCHA detection — pause & retry
                        if await page.evaluate(CAPTCHA_CHECK_JS):
                            print(f"[GoogleMaps] ⚠️ CAPTCHA detected on W{worker_id+1} at {search_loc}! Pausing 30s...")
                            if progress_cb:
                                await progress_cb("google_maps", phase1_progress["done"], phase1_progress["total"],
                                    f"⚠️ W{worker_id+1}: CAPTCHA! Pausing 30s then retrying...")
                            await asyncio.sleep(30)
                            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                            await asyncio.sleep(3)
                            if await page.evaluate(CAPTCHA_CHECK_JS):
                                print(f"[GoogleMaps] ❌ CAPTCHA still present on W{worker_id+1}, skipping {search_loc}")
                                phase1_progress["done"] += 1
                                continue

                        try:
                            await page.wait_for_selector('div[role="feed"]', timeout=10000)
                        except Exception:
                            phase1_progress["done"] += 1
                            continue

                        # Scroll the feed
                        prev_count = 0
                        for scroll in range(12):
                            await page.evaluate('''() => {
                                const f = document.querySelector('div[role="feed"]');
                                if (f) f.scrollTop = f.scrollHeight;
                            }''')
                            await asyncio.sleep(random.uniform(1.0, 1.8))
                            curr_count = await page.evaluate('''() => {
                                return document.querySelectorAll('div[role="feed"] a[href*="/maps/place/"]').length;
                            }''')
                            if curr_count == prev_count and scroll > 2:
                                break
                            prev_count = curr_count

                        # Collect URLs
                        urls = await page.evaluate('''() => {
                            const anchors = document.querySelectorAll('div[role="feed"] a[href*="/maps/place/"]');
                            const links = [];
                            for (const a of anchors) links.push(a.href);
                            return links;
                        }''')

                        new_count = 0
                        for u in urls:
                            clean_url = u.split('?')[0]
                            if clean_url not in seen_urls:
                                seen_urls.add(clean_url)
                                worker_urls.append(u)
                                new_count += 1

                        phase1_progress["done"] += 1
                        phase1_progress["urls_found"] = len(seen_urls) - len(skip_urls or set())

                        if progress_cb and phase1_progress["done"] % 2 == 0:
                            await progress_cb("google_maps", phase1_progress["done"], phase1_progress["total"],
                                f"🔍 [{phase1_progress['done']}/{phase1_progress['total']}] W{worker_id+1}: +{new_count} from {search_loc} ({phase1_progress['urls_found']} total)")

                    except Exception as e:
                        phase1_progress["done"] += 1
                        print(f"[GoogleMaps] W{worker_id+1} Error: {search_loc}: {e}")
                        continue

                await context.close()
                return worker_urls

            # Run all Phase 1 workers in parallel
            chunk_results = await asyncio.gather(*[
                phase1_worker(i, area_chunks[i]) for i in range(PARALLEL_WORKERS)
            ])
            for chunk_urls in chunk_results:
                all_place_urls.extend(chunk_urls)

            if progress_cb:
                await progress_cb("google_maps", len(searches), len(searches),
                    f"✅ Phase 1 done: {len(all_place_urls)} unique places found across {len(searches)} areas")

            # ═══════════════════════════════════════════════
            # PHASE 2: Parallel data extraction (3 workers)
            # ═══════════════════════════════════════════════
            total_places = min(len(all_place_urls), max_results)
            urls_to_visit = all_place_urls[:max_results]
            skipped_existing = len(skip_urls or set())

            if progress_cb:
                msg = f"Phase 2: Visiting {total_places} businesses with {PARALLEL_WORKERS} workers"
                if skipped_existing > 0:
                    msg += f" (skipped {skipped_existing} already in DB)"
                await progress_cb("google_maps", 0, total_places, msg)

            # Shared queue for Phase 2
            url_queue = asyncio.Queue()
            for idx, url in enumerate(urls_to_visit):
                url_queue.put_nowait((idx, url))

            phase2_progress = {"done": 0, "total": total_places}

            async def phase2_worker(worker_id):
                """One worker visiting places from the shared queue."""
                context = await browser.new_context(
                    user_agent=USER_AGENTS[(worker_id + 3) % len(USER_AGENTS)],
                    viewport={"width": 1300 + worker_id * 50, "height": 750 + worker_id * 15},
                    locale="en-IN", timezone_id="Asia/Kolkata",
                )
                page = await context.new_page()
                await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,mp4,webp}",
                                 lambda route: route.abort())
                worker_results = []
                worker_failed = []

                while not url_queue.empty():
                    try:
                        idx, place_url = url_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    try:
                        await page.goto(place_url, wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(random.uniform(1.2 + worker_id * 0.2, 2.2 + worker_id * 0.2))

                        # CAPTCHA detection
                        if await page.evaluate(CAPTCHA_CHECK_JS):
                            print(f"[GoogleMaps] ⚠️ CAPTCHA on W{worker_id+1} Phase 2! Pausing 30s...")
                            if progress_cb:
                                await progress_cb("google_maps", phase2_progress["done"], total_places,
                                    f"⚠️ W{worker_id+1}: CAPTCHA! Pausing 30s...")
                            await asyncio.sleep(30)
                            await page.goto(place_url, wait_until="domcontentloaded", timeout=15000)
                            await asyncio.sleep(3)
                            if await page.evaluate(CAPTCHA_CHECK_JS):
                                print(f"[GoogleMaps] ❌ CAPTCHA still on W{worker_id+1}, adding to failed")
                                worker_failed.append(place_url)
                                phase2_progress["done"] += 1
                                continue

                        data = await page.evaluate(EXTRACT_PLACE_JS)

                        if data.get('website') and 'google.com' in data['website']:
                            data['website'] = ''

                        if data.get('business_name'):
                            data['source'] = 'google_maps'
                            worker_results.append(data)

                        phase2_progress["done"] += 1
                        if progress_cb and phase2_progress["done"] % 5 == 0:
                            pct = round(phase2_progress["done"] / total_places * 100)
                            remaining = total_places - phase2_progress["done"]
                            await progress_cb("google_maps", phase2_progress["done"], total_places,
                                f"📋 [{phase2_progress['done']}/{total_places}] W{worker_id+1}: {data.get('business_name', '?')} — {pct}% done, {remaining} left")

                    except Exception as e:
                        worker_failed.append(place_url)
                        phase2_progress["done"] += 1
                        print(f"[GoogleMaps] W{worker_id+1} Error place: {e}")
                        if progress_cb and phase2_progress["done"] % 10 == 0:
                            pct = round(phase2_progress["done"] / total_places * 100)
                            await progress_cb("google_maps", phase2_progress["done"], total_places,
                                f"⚠️ [{phase2_progress['done']}/{total_places}] W{worker_id+1}: FAILED — {pct}% done, {len(worker_failed)} failed")
                        continue

                await context.close()
                return worker_results, worker_failed

            # Run all Phase 2 workers in parallel
            phase2_results = await asyncio.gather(*[
                phase2_worker(i) for i in range(PARALLEL_WORKERS)
            ])
            for worker_results, worker_failed in phase2_results:
                all_results.extend(worker_results)
                failed_urls.extend(worker_failed)

            if progress_cb:
                await progress_cb("google_maps", total_places, total_places,
                    f"✅ Phase 2 done: {len(all_results)} extracted, {len(failed_urls)} failed")

        except Exception as e:
            print(f"[GoogleMaps] Fatal: {e}")
        finally:
            await browser.close()

    # Save failed URLs for retry
    if failed_urls:
        _save_failed_urls(failed_urls, query, location)
        print(f"[GoogleMaps] {len(failed_urls)} failed URLs saved for retry")

    # Return results AND seen_urls (Phase 1 URLs for accurate cross-query skip)
    return all_results, seen_urls


def _save_failed_urls(urls, query, location):
    """Append failed URLs to JSON file for later retry."""
    existing = []
    if os.path.exists(FAILED_URLS_FILE):
        try:
            with open(FAILED_URLS_FILE, "r") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    seen = {e["url"] for e in existing}
    for url in urls:
        if url not in seen:
            existing.append({"url": url, "query": query, "location": location})
    with open(FAILED_URLS_FILE, "w") as f:
        json.dump(existing, f)


async def retry_failed_urls(progress_cb=None):
    """Retry previously failed URLs and return recovered leads."""
    if not os.path.exists(FAILED_URLS_FILE):
        return []
    with open(FAILED_URLS_FILE, "r") as f:
        failed = json.load(f)
    if not failed:
        return []

    results = []
    still_failed = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            locale="en-IN", timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,mp4,webp}",
                         lambda route: route.abort())

        for idx, item in enumerate(failed):
            try:
                if progress_cb:
                    await progress_cb("retry", idx, len(failed),
                                      f"🔄 Retrying [{idx+1}/{len(failed)}]...")
                await page.goto(item["url"], wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(random.uniform(1.2, 2.2))

                data = await page.evaluate('''() => {
                    const r = {business_name:'', address:'', phone:'', website:'',
                               rating:0, review_count:0, category:'', maps_url: window.location.href};
                    const h1 = document.querySelector('h1');
                    r.business_name = h1 ? h1.innerText.trim() : '';
                    const rat = document.querySelector('div.F7nice span[aria-hidden="true"]');
                    if (rat) r.rating = parseFloat(rat.textContent) || 0;
                    const revs = document.querySelectorAll('div.F7nice span');
                    for (const s of revs) {
                        const m = s.textContent.match(/\(([\d,]+)\)/);
                        if (m) { r.review_count = parseInt(m[1].replace(/,/g,'')) || 0; break; }
                    }
                    const btns = document.querySelectorAll('button[data-item-id]');
                    for (const b of btns) {
                        const id = b.getAttribute('data-item-id');
                        if (id && id.startsWith('phone:')) r.phone = id.replace('phone:tel:', '').replace('phone:', '');
                        if (id === 'authority') { r.website = (b.querySelector('a') || b).getAttribute('href') || ''; }
                    }
                    const addr = document.querySelector('button[data-item-id="address"]');
                    if (addr) r.address = (addr.getAttribute('aria-label') || '').replace('Address: ', '');
                    const cat = document.querySelector('button[jsaction*="category"]');
                    if (cat) r.category = cat.textContent.trim();
                    return r;
                }''')

                if data.get('website') and 'google.com' in data['website']:
                    data['website'] = ''
                if data.get('business_name'):
                    data['source'] = 'google_maps'
                    results.append(data)
            except Exception:
                still_failed.append(item)
                continue

        await browser.close()

    with open(FAILED_URLS_FILE, "w") as f:
        json.dump(still_failed, f)

    if progress_cb:
        await progress_cb("retry", len(failed), len(failed),
                          f"✅ Retry: {len(results)} recovered, {len(still_failed)} still failing")
    return results
