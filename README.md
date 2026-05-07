# 🎯 LeadHunter Pro

**AI-powered lead generation CRM that scrapes Google Maps, ranks businesses by buyer intent, and helps you close website sales faster.**

Built for selling websites/digital services to local Indian businesses. Scrapes → Analyzes → Scores → Prioritizes → You call the best leads first.

---

## ⚡ Quick Start

```bash
# 1. Clone
git clone https://github.com/AadityaAggarwal2007/lead-finder.git
cd lead-finder

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install browser engine (one-time)
playwright install chromium

# 4. Set your Gemini API key
export GEMINI_API_KEY=your_key_here
# Or create a .env file:
echo "GEMINI_API_KEY=your_key_here" > .env

# 5. Run
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** → Search → Start Calling 🚀

---

## 🏗️ How It Works

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
│  Google Maps │───▶│  Extract     │───▶│  Score &    │───▶│  CRM     │
│  Scraper     │    │  Details     │    │  Rank       │    │  Dashboard│
│  (8 workers) │    │  (Phase 2)   │    │  (v3 Algo)  │    │  + Call  │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────┘
       │                  │                   │
  Ranked areas      Reviews, phone,     7-pillar scoring
  premium first     website, ads        with area intelligence
```

### Pipeline Steps

1. **Search** — You enter "Dentist" + "Delhi"
2. **Area Expansion** — System expands into 51 ranked sub-areas (GK first, Shahdara last)
3. **Phase 1** — Scrolls Google Maps in each area, collects all business URLs
4. **Phase 2** — Visits each URL with 8 parallel workers, extracts full details
5. **Filter** — Skips businesses with <20 Google reviews (configurable)
6. **Website Analysis** — Checks each business's website quality (20 concurrent)
7. **Scoring** — Runs the v3 algorithm (219K leads/sec) on every lead
8. **CRM** — Sorted by score, premium-area leads on top, ready to call

---

## 🧠 Scoring Algorithm v3

Every lead gets a score from 5-98 based on **7 pillars**:

| Pillar | Points | What It Measures |
|--------|--------|-----------------|
| 🌐 Website Opportunity | 0-35 | No site = 35pts, Wix/Facebook = 30pts, bad site = 27pts |
| ⭐ Business Credibility | 0-20 | Reviews (logarithmic) + rating quality |
| 📍 Area Affluence | 0-20 | GK/Bandra = 20pts, Shahdara = 6pts |
| 📡 Conversion Signals | 0-15 | Google Ads (+8), claimed listing (+2), photos, phone |
| 🏷️ Category Match | 0-5 | Dentist/Salon/Restaurant = +5pts |
| 🏢 Name Intelligence | 0-5 | "Dr.", "Pvt Ltd", "Hospital" = premium client |
| ⚠️ Penalties | -50 to 0 | Closed (-50), ghost (-10), unreachable (-5) |

### Score Examples

| Business | Score | Verdict | Why |
|----------|-------|---------|-----|
| GK Dentist, no website, 400 reviews, running ads | **98** | 🔥 HOT | Dream lead — money + intent + no site |
| Bandra Salon with Wix site, 200 reviews | **89** | 🔥 HOT | Free site = upgrade pitch |
| Practo-listed doctor, Jubilee Hills | **81** | 🔥 HOT | Practo ≠ real website |
| Good website (78/100), Koramangala | **64** | 🟡 WARM | Already has decent site |
| Kirana store, Shahdara, 25 reviews | **43** | 🔵 COLD | Grocery = ₹0 website budget |
| Permanently closed restaurant | **21** | ⛔ SKIP | Dead business |

### Smart Features

- **Free site detection** — Wix, WordPress.com, Facebook, Practo, Zomato links treated as "no real website"
- **Low-value category penalty** — Grocery, plumber, tailor, mechanic = auto-deprioritized
- **Area bonus cap** — Great website (75+) doesn't benefit from premium area boost
- **Logarithmic reviews** — Going 20→100 reviews matters more than 500→1000

---

## 📍 Area Intelligence

517 areas across 11 Indian cities, ranked by affluence:

| City | Tier 1 (Premium) | Tier 2 (Upper-Mid) | Tier 3 (Middle) | Total |
|------|-------------------|--------------------|-----------------| ------|
| Delhi | GK, Defence Colony, Hauz Khas... | Rajouri Garden, Dwarka... | Shahdara, Uttam Nagar... | 71 |
| Mumbai | Bandra, Juhu, Powai... | Andheri East, Thane... | Mira Road, Virar... | 64 |
| Bangalore | Koramangala, Indiranagar... | BTM Layout, Electronic City... | Peenya, Kengeri... | 56 |
| Hyderabad | Jubilee Hills, Madhapur... | Miyapur, LB Nagar... | Hayathnagar... | 52 |
| Pune | Koregaon Park, Baner... | Hadapsar, NIBM... | Chakan, Alandi... | 56 |
| + 6 more | Chennai, Kolkata, Ahmedabad, Jaipur, Noida, Gurgaon | | | |

**How it helps:** Scraper hits GK/Bandra/Koramangala FIRST. When you open CRM to call, premium-area businesses are on top.

---

## 📞 CRM Dashboard

Access at **http://localhost:8000/crm/{search_id}**

### Features
- **Status Categories** — Hot 🔥, Call Later 🕐, Not Picked 📵, Transferred ↗️, Not Happening ❌
- **Pagination** — Loads 100 leads at a time (handles 26K+ without lag)
- **Notes** — Add notes per lead that persist across status changes
- **Start Calling** — One-click calling flow with categorization buttons
- **Live Stats** — Real-time count of each status category

---

## ⚙️ Configuration

| Setting | Value | File |
|---------|-------|------|
| Parallel scraping workers | 8 | `scrapers/google_maps.py` |
| Website analyzer concurrency | 20 | `analyzer.py` |
| Minimum reviews filter | 20 | `main.py` (MIN_REVIEWS) |
| Area tier depth | Tier 1+2 | `scrapers/google_maps.py` |
| Headless browser | True | `config.py` |

---

## 📁 Project Structure

```
lead-finder/
├── main.py              # FastAPI app + scoring algorithm v3
├── database.py          # SQLite operations
├── analyzer.py          # Website quality analyzer
├── ai_engine.py         # Gemini AI for detailed reports
├── area_data.py         # 517 areas ranked by affluence
├── config.py            # User agents, headless mode
├── requirements.txt     # Python dependencies
├── run.sh               # Launch script
├── scrapers/
│   ├── __init__.py
│   ├── google_maps.py   # Google Maps scraper (v5)
│   └── justdial.py      # JustDial scraper (legacy, unused)
├── static/
│   ├── app.js           # Frontend logic + pagination
│   └── style.css        # Dashboard styling
└── templates/
    ├── index.html        # Search dashboard
    └── crm.html          # CRM calling interface
```

---

## 🖥️ System Requirements

| Spec | Minimum | Recommended |
|------|---------|-------------|
| RAM | 8 GB | 32 GB |
| Python | 3.9+ | 3.12+ |
| OS | macOS / Windows / Linux | Any |
| Internet | Required | Stable connection |

---

## 📜 License

Private project. Not for redistribution.
