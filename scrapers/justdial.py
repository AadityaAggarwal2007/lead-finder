"""
LeadHunter Pro — JustDial Scraper
Extracts business listings from JustDial search results.
Note: JustDial has heavy anti-bot protection. Uses Playwright stealth.
"""

import asyncio
import random
import urllib.parse
from playwright.async_api import async_playwright
from config import USER_AGENTS, SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX, HEADLESS


async def _random_delay(min_s=None, max_s=None):
    mn = min_s or SCRAPE_DELAY_MIN
    mx = max_s or SCRAPE_DELAY_MAX
    await asyncio.sleep(random.uniform(mn, mx))


def _build_justdial_url(query: str, location: str) -> str:
    """Build JustDial search URL. JustDial uses Title-Case city and query."""
    city = location.strip().split(",")[0].strip().title().replace(" ", "-")
    q = query.strip().title().replace(" ", "-")
    # JustDial also accepts /nct-Delhi/ format for Delhi
    return f"https://www.justdial.com/{city}/{q}"


async def scrape_justdial(query: str, location: str, max_results: int = 40, progress_cb=None):
    """
    Scrape JustDial for business listings.
    Returns list of dicts with business data.
    """
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()

        # Stealth: override navigator properties
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        # Block heavy resources
        await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,mp4,webp}", lambda route: route.abort())

        try:
            url = _build_justdial_url(query, location)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _random_delay(3, 5)

            # Handle popups
            for sel in ['button:has-text("OK")', '.close-btn', '#best_deal_close', '.crossimg']:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        await _random_delay(0.5, 1)
                except Exception:
                    continue

            # Scroll to load more
            for _ in range(5):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await _random_delay(1.5, 2.5)

            if progress_cb:
                await progress_cb("justdial", 0, 0, "Extracting JustDial listings...")

            # Extract listings
            listings = await page.evaluate('''() => {
                const items = [];
                // JustDial listing cards - multiple selector patterns
                const cards = document.querySelectorAll(
                    '.resultbox_info, .store-details, .jsx-s, [class*="resultbox"], .jdgrid_col'
                );

                // Fallback: try generic approach
                const allCards = cards.length > 0 ? cards :
                    document.querySelectorAll('li.cntanr, .comp-info, [class*="listing"]');

                for (const card of allCards) {
                    const item = {};

                    // Business name
                    const nameEl = card.querySelector(
                        'h2, h3, .lng_cont_name, .store-name, [class*="title"], [class*="name"] span'
                    );
                    item.business_name = nameEl ? nameEl.innerText.trim() : '';
                    if (!item.business_name) continue;

                    // Rating
                    const ratingEl = card.querySelector(
                        '.green-box, .rating-count, [class*="rating"], .star_m'
                    );
                    if (ratingEl) {
                        const r = parseFloat(ratingEl.textContent);
                        item.rating = isNaN(r) ? 0 : r;
                    } else {
                        item.rating = 0;
                    }

                    // Review/vote count
                    const voteEl = card.querySelector(
                        '.rt_count, .votes-count, [class*="votes"], [class*="review"]'
                    );
                    if (voteEl) {
                        const m = voteEl.textContent.match(/([\\d,]+)/);
                        item.review_count = m ? parseInt(m[1].replace(/,/g, '')) : 0;
                    } else {
                        item.review_count = 0;
                    }

                    // Address
                    const addrEl = card.querySelector(
                        '.cont_sw_addr, .address-info, [class*="address"], .moreinfo'
                    );
                    item.address = addrEl ? addrEl.innerText.trim() : '';

                    // Category / tags
                    const catEl = card.querySelector('.cat-name, [class*="category"]');
                    item.category = catEl ? catEl.innerText.trim() : '';

                    // Phone - JustDial hides phone with CSS encoding
                    // Try to get from data attributes or contact section
                    const phoneEl = card.querySelector(
                        '.contact-info a[href^="tel:"], a[href^="tel:"], [class*="phone"]'
                    );
                    if (phoneEl) {
                        const href = phoneEl.getAttribute('href') || '';
                        item.phone = href.startsWith('tel:') ?
                            href.replace('tel:', '') : phoneEl.innerText.trim();
                    } else {
                        item.phone = '';
                    }

                    // Website
                    const webEl = card.querySelector(
                        'a[href*="http"][target="_blank"], a.website-btn, [class*="website"] a'
                    );
                    if (webEl) {
                        const href = webEl.getAttribute('href') || '';
                        if (href && !href.includes('justdial.com') && !href.includes('google.com')) {
                            item.website = href;
                        }
                    }

                    items.push(item);
                }
                return items;
            }''')

            for idx, item in enumerate(listings[:max_results]):
                item['source'] = 'justdial'
                item['city'] = location.strip().split(",")[0].strip()
                results.append(item)

                if progress_cb:
                    await progress_cb(
                        "justdial", idx + 1, min(len(listings), max_results),
                        f"Extracted: {item.get('business_name', 'Unknown')}"
                    )

        except Exception as e:
            print(f"[JustDial] Error: {e}")
        finally:
            await browser.close()

    return results
