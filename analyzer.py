"""
LeadHunter Pro — Website Analyzer
Audits lead websites for quality, SEO, mobile-friendliness, SSL, speed.
Uses Google PageSpeed Insights API (free, no key needed) + direct crawl.
"""

import asyncio
import httpx
from config import PAGESPEED_API_URL


async def analyze_website(url: str) -> dict:
    """
    Analyze a website's quality. Returns a dict with scores and findings.
    Keeps API calls minimal — one PageSpeed call + one direct fetch.
    """
    analysis = {
        "url": url,
        "is_reachable": False,
        "has_ssl": url.startswith("https"),
        "pagespeed_mobile": 0,
        "pagespeed_desktop": 0,
        "is_mobile_friendly": False,
        "has_meta_description": False,
        "has_proper_title": False,
        "has_h1": False,
        "load_time_ms": 0,
        "content_length": 0,
        "technologies": [],
        "issues": [],
        "overall_score": 0,  # 0-100
    }

    # Normalize URL
    if not url.startswith("http"):
        url = "https://" + url
    analysis["url"] = url

    async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
        # 1. Direct fetch — check reachability, basic SEO, tech detection
        try:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })
            analysis["is_reachable"] = resp.status_code < 400
            analysis["load_time_ms"] = int(resp.elapsed.total_seconds() * 1000)
            analysis["has_ssl"] = str(resp.url).startswith("https")

            html = resp.text.lower()
            analysis["content_length"] = len(resp.text)

            # Basic SEO checks
            analysis["has_proper_title"] = "<title>" in html and "</title>" in html
            analysis["has_meta_description"] = 'name="description"' in html or "name='description'" in html
            analysis["has_h1"] = "<h1" in html

            # Mobile check
            analysis["is_mobile_friendly"] = 'name="viewport"' in html or "name='viewport'" in html

            # Tech detection (simple)
            techs = []
            if "wordpress" in html or "wp-content" in html:
                techs.append("WordPress")
            if "shopify" in html:
                techs.append("Shopify")
            if "wix.com" in html:
                techs.append("Wix")
            if "squarespace" in html:
                techs.append("Squarespace")
            if "react" in html or "reactdom" in html:
                techs.append("React")
            if "next.js" in html or "__next" in html:
                techs.append("Next.js")
            if "bootstrap" in html:
                techs.append("Bootstrap")
            if "tailwind" in html:
                techs.append("Tailwind CSS")
            if "jquery" in html:
                techs.append("jQuery")
            if "google-analytics" in html or "gtag" in html:
                techs.append("Google Analytics")
            if "facebook.com/tr" in html or "fbq(" in html:
                techs.append("Facebook Pixel")
            analysis["technologies"] = techs

            # Identify issues
            issues = []
            if not analysis["has_ssl"]:
                issues.append("No SSL/HTTPS — insecure website")
            if not analysis["is_mobile_friendly"]:
                issues.append("Not mobile-friendly — missing viewport meta tag")
            if not analysis["has_proper_title"]:
                issues.append("Missing or empty <title> tag — terrible for SEO")
            if not analysis["has_meta_description"]:
                issues.append("No meta description — hurts search rankings")
            if not analysis["has_h1"]:
                issues.append("No H1 heading — bad for SEO structure")
            if analysis["load_time_ms"] > 3000:
                issues.append(f"Slow load time ({analysis['load_time_ms']}ms) — users bounce after 3s")
            if len(techs) == 0:
                issues.append("Basic/custom HTML — likely outdated website")
            analysis["issues"] = issues

        except Exception as e:
            analysis["issues"].append(f"Website unreachable: {str(e)[:100]}")
            analysis["overall_score"] = 5  # Very bad = great lead!
            return analysis

        # 2. PageSpeed Insights (mobile only — saves an API call)
        try:
            ps_url = f"{PAGESPEED_API_URL}?url={url}&strategy=mobile&category=performance&category=seo"
            ps_resp = await client.get(ps_url, timeout=30)
            if ps_resp.status_code == 200:
                ps_data = ps_resp.json()
                categories = ps_data.get("lighthouseResult", {}).get("categories", {})
                perf = categories.get("performance", {}).get("score", 0)
                seo = categories.get("seo", {}).get("score", 0)
                analysis["pagespeed_mobile"] = int((perf or 0) * 100)

                if analysis["pagespeed_mobile"] < 50:
                    analysis["issues"].append(f"Poor mobile performance score: {analysis['pagespeed_mobile']}/100")
        except Exception:
            pass  # PageSpeed is optional enrichment

    # 3. Calculate overall website quality score (0-100, higher = better website)
    score = 50  # Base
    if not analysis["is_reachable"]:
        score = 5
    else:
        if analysis["has_ssl"]:
            score += 10
        else:
            score -= 15
        if analysis["is_mobile_friendly"]:
            score += 10
        else:
            score -= 10
        if analysis["has_proper_title"]:
            score += 5
        if analysis["has_meta_description"]:
            score += 5
        if analysis["has_h1"]:
            score += 5
        if analysis["pagespeed_mobile"] > 0:
            score += (analysis["pagespeed_mobile"] - 50) // 5  # +/- based on speed
        if analysis["load_time_ms"] > 5000:
            score -= 15
        elif analysis["load_time_ms"] > 3000:
            score -= 8

    analysis["overall_score"] = max(0, min(100, score))

    # ═══════════════════════════════════════════════
    # Generate pitch-ready detailed report
    # ═══════════════════════════════════════════════
    report = []
    recommendations = []
    
    if not analysis["is_reachable"]:
        report.append("🔴 CRITICAL: Website is DOWN or unreachable. Students searching for your coaching center online will see an error page and go to your competitor instead.")
        recommendations.append("Fix hosting immediately — every day your site is down, you lose potential students.")
    else:
        # SSL
        if not analysis["has_ssl"]:
            report.append("🔴 NO SSL/HTTPS: Your website shows 'Not Secure' warning in Chrome. Parents won't trust a site that Google marks as unsafe.")
            recommendations.append("Install SSL certificate (free via Let's Encrypt) — this is the #1 trust signal for parents.")
        else:
            report.append("✅ SSL/HTTPS: Website is secure.")

        # Mobile
        if not analysis["is_mobile_friendly"]:
            report.append("🔴 NOT MOBILE-FRIENDLY: 70% of parents search for coaching centers on their phone. Your website breaks on mobile devices.")
            recommendations.append("Make website responsive/mobile-friendly — you're losing 70% of potential leads.")
        else:
            report.append("✅ Mobile-friendly: Works on phones.")

        # Speed
        if analysis["load_time_ms"] > 5000:
            report.append(f"🔴 VERY SLOW: Takes {analysis['load_time_ms']/1000:.1f} seconds to load. Users leave after 3 seconds.")
            recommendations.append("Optimize images, enable caching, upgrade hosting — speed directly impacts admissions.")
        elif analysis["load_time_ms"] > 3000:
            report.append(f"🟡 SLOW: Takes {analysis['load_time_ms']/1000:.1f} seconds to load. Should be under 3 seconds.")
            recommendations.append("Optimize page speed — compress images and minify CSS/JS.")
        elif analysis["load_time_ms"] > 0:
            report.append(f"✅ Good speed: Loads in {analysis['load_time_ms']/1000:.1f} seconds.")

        # SEO - Title
        if not analysis["has_proper_title"]:
            report.append("🔴 NO PAGE TITLE: When someone searches 'Coaching Center in [area]' on Google, your site won't show up properly.")
            recommendations.append("Add a descriptive <title> tag like 'Best IIT Coaching in Pitampura | Your Name'.")
        else:
            report.append("✅ Has page title.")

        # SEO - Meta Description
        if not analysis["has_meta_description"]:
            report.append("🔴 NO META DESCRIPTION: Google shows a random snippet from your site instead of a compelling description. Competitors with descriptions get more clicks.")
            recommendations.append("Add meta description: 'Top-rated IIT/NEET coaching in [area]. 95% success rate. Enroll now!'")
        else:
            report.append("✅ Has meta description.")

        # SEO - H1
        if not analysis["has_h1"]:
            report.append("🟡 NO H1 HEADING: Missing main heading hurts your Google ranking.")
            recommendations.append("Add a clear H1 heading on your homepage.")
        
        # PageSpeed
        if analysis["pagespeed_mobile"] > 0 and analysis["pagespeed_mobile"] < 50:
            report.append(f"🔴 POOR GOOGLE SCORE: Google rates your mobile performance {analysis['pagespeed_mobile']}/100. This hurts your search ranking.")
            recommendations.append("Improve Google PageSpeed score — optimize images, reduce JavaScript.")
        elif analysis["pagespeed_mobile"] >= 50:
            report.append(f"✅ Google PageSpeed: {analysis['pagespeed_mobile']}/100.")

        # Tech
        if analysis["technologies"]:
            report.append(f"🔧 Built with: {', '.join(analysis['technologies'])}")
        else:
            report.append("🟡 Basic/custom HTML website — likely outdated technology.")
            recommendations.append("Upgrade to a modern platform (WordPress/React) for better performance and easier updates.")

    # Summary verdict
    score = analysis["overall_score"]
    if score <= 20:
        verdict = "Website is in CRITICAL condition — massive opportunity for improvement."
    elif score <= 40:
        verdict = "Website has MAJOR issues — needs significant work to attract students online."
    elif score <= 60:
        verdict = "Website is AVERAGE — several improvements can make it much more effective."
    elif score <= 80:
        verdict = "Website is DECENT — minor improvements possible."
    else:
        verdict = "Website is GOOD — limited scope for improvement."

    analysis["detailed_report"] = report
    analysis["recommendations"] = recommendations
    analysis["verdict"] = verdict
    analysis["recommendation_count"] = len(recommendations)

    return analysis


async def batch_analyze_websites(leads: list, progress_cb=None) -> list:
    """
    Analyze websites for all leads that have one.
    Returns leads with website_analysis populated.
    Runs 5 at a time (safe — these are HTTP requests to different websites, not Google).
    """
    semaphore = asyncio.Semaphore(20)
    total_with_website = sum(1 for l in leads if l.get("website"))
    analyzed = 0

    async def _analyze_one(lead):
        nonlocal analyzed
        if not lead.get("website"):
            lead["website_analysis"] = None
            lead["website_score"] = -1  # No website = flag for AI
            return lead

        async with semaphore:
            analysis = await analyze_website(lead["website"])
            lead["website_analysis"] = analysis
            lead["website_score"] = analysis["overall_score"]
            analyzed += 1
            if progress_cb:
                await progress_cb(
                    "website_analysis", analyzed, total_with_website,
                    f"Analyzed: {lead.get('business_name', '')}"
                )
            return lead

    tasks = [_analyze_one(lead) for lead in leads]
    results = await asyncio.gather(*tasks)
    return results
