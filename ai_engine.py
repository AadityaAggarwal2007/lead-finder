"""
LeadHunter Pro — AI Engine (Gemini Flash 2.5)
Scores and ranks leads for web design sales potential.
Batches leads to minimize token usage.
"""

import json
from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


def _build_lead_summary(lead: dict) -> dict:
    """Build a minimal summary of a lead for the AI prompt (saves tokens)."""
    summary = {
        "id": lead.get("_idx", 0),
        "name": lead.get("business_name", "")[:60],
        "cat": lead.get("category", "")[:40],
        "rating": lead.get("rating", 0),
        "reviews": lead.get("review_count", 0),
        "phone": "yes" if lead.get("phone") else "no",
        "has_website": "yes" if lead.get("website") else "NO",
        "addr": lead.get("address", "")[:80],
        "source": lead.get("source", ""),
    }

    # Add website analysis if available
    wa = lead.get("website_analysis")
    if wa and isinstance(wa, dict):
        summary["web"] = {
            "score": wa.get("overall_score", 0),
            "ssl": wa.get("has_ssl", False),
            "mobile": wa.get("is_mobile_friendly", False),
            "speed_ms": wa.get("load_time_ms", 0),
            "seo_title": wa.get("has_proper_title", False),
            "seo_desc": wa.get("has_meta_description", False),
            "tech": wa.get("technologies", []),
            "issues": wa.get("issues", [])[:5],
        }
    elif lead.get("website_score", 0) == -1:
        summary["web"] = "NO_WEBSITE"

    return summary


SYSTEM_PROMPT = """You are LeadHunter AI — a lead scoring engine for a web design & digital products agency in India.

YOUR JOB: Score each business lead on how likely they are to BUY web design services or digital products.

SCORING RULES (score 1-100):
- NO WEBSITE = Score 75-95 (they desperately need one! Higher if bigger business)
- BAD WEBSITE (slow, no SSL, not mobile-friendly, poor SEO) = Score 65-85
- MEDIOCRE WEBSITE (some issues) = Score 40-60
- GOOD WEBSITE = Score 15-35 (hard sell)
- GREAT WEBSITE (fast, modern, SEO-optimized) = Score 5-15 (skip)

MULTIPLIERS:
- More reviews/ratings = bigger business = higher score (can afford to pay)
- Running ads = already spends on digital = +10
- Category that benefits from web presence (restaurants, hotels, shops) = +5

OUTPUT FORMAT — respond with ONLY valid JSON array, no markdown:
[{
  "id": <lead_id>,
  "score": <1-100>,
  "size": "<micro|small|medium|large>",
  "verdict": "<HOT|WARM|COLD|SKIP>",
  "contact": <true|false>,
  "pitch": "<1 line pitch angle for this specific business>",
  "reason": "<1 line why this score>"
}]

Be concise. No explanations outside the JSON."""


async def score_leads_batch(leads: list) -> list:
    """
    Score a batch of leads using Gemini Flash 2.5.
    Processes in batches of 15 to balance token efficiency and reliability.
    Returns the leads with AI scores attached.
    """
    client = _get_client()
    batch_size = 15
    all_scores = {}

    for i in range(0, len(leads), batch_size):
        batch = leads[i:i + batch_size]

        # Build minimal summaries
        summaries = []
        for idx, lead in enumerate(batch):
            lead["_idx"] = i + idx
            summaries.append(_build_lead_summary(lead))

        prompt = f"Score these {len(summaries)} business leads:\n{json.dumps(summaries, separators=(',', ':'))}"

        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.1,  # Very low for strict JSON output
                    "max_output_tokens": 2000,
                    "response_mime_type": "application/json",
                },
            )

            # Parse response
            text = response.text.strip()
            # Remove markdown code blocks if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()

            # Try parsing JSON
            try:
                scores = json.loads(text)
            except json.JSONDecodeError:
                # Fallback: try to extract JSON array from the response
                import re
                match = re.search(r'\[.*\]', text, re.DOTALL)
                if match:
                    # Replace problematic characters
                    cleaned = match.group(0)
                    cleaned = cleaned.replace('\n', ' ').replace('\r', '')
                    scores = json.loads(cleaned)
                else:
                    raise ValueError(f"Could not extract JSON from AI response")

            for s in scores:
                all_scores[s["id"]] = s

        except Exception as e:
            print(f"[AI] Error scoring batch {i}-{i+batch_size}: {e}")
            # Fallback: assign default scores based on website presence
            for lead in batch:
                idx = lead["_idx"]
                has_site = bool(lead.get("website"))
                all_scores[idx] = {
                    "id": idx,
                    "score": 30 if has_site else 75,
                    "size": "unknown",
                    "verdict": "WARM" if not has_site else "COLD",
                    "contact": not has_site,
                    "pitch": "Needs website" if not has_site else "Has existing website",
                    "reason": "AI scoring failed — default score applied",
                }

    # Attach scores back to leads
    for lead in leads:
        idx = lead.get("_idx", -1)
        ai = all_scores.get(idx, {})
        lead["ai_ranking_score"] = ai.get("score", 50)
        lead["ai_analysis"] = json.dumps({
            "verdict": ai.get("verdict", "WARM"),
            "pitch": ai.get("pitch", ""),
            "reason": ai.get("reason", ""),
        })
        lead["worth_contacting"] = 1 if ai.get("contact", True) else 0
        lead["business_size"] = ai.get("size", "unknown")

        # Clean up temp field
        if "_idx" in lead:
            del lead["_idx"]

    return leads


async def generate_lead_report(lead: dict) -> str:
    """
    Generate a detailed AI report for a single lead.
    Used when user clicks on a specific lead for deep analysis.
    """
    client = _get_client()

    wa = lead.get("website_analysis", {})
    if isinstance(wa, str):
        try:
            wa = json.loads(wa)
        except Exception:
            wa = {}

    prompt = f"""Analyze this business as a potential web design client:

Business: {lead.get('business_name', 'Unknown')}
Category: {lead.get('category', 'Unknown')}
Location: {lead.get('address', 'Unknown')}
Rating: {lead.get('rating', 'N/A')} ({lead.get('review_count', 0)} reviews)
Website: {lead.get('website', 'NONE')}
Phone: {lead.get('phone', 'N/A')}
Source: {lead.get('source', 'N/A')}

Website Analysis: {json.dumps(wa, separators=(',', ':')) if wa else 'No website'}

Give me:
1. OPPORTUNITY SUMMARY (2 lines)
2. WEBSITE VERDICT (what's wrong, what they need)
3. SUGGESTED PITCH (exactly what to say when calling them)
4. ESTIMATED BUDGET RANGE (what they'd likely pay for web design in INR)
5. PRIORITY: HOT / WARM / COLD

Be direct and actionable. No fluff."""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": 0.4,
                "max_output_tokens": 500,
            },
        )
        return response.text
    except Exception as e:
        return f"AI report generation failed: {e}"
