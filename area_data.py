"""
LeadHunter Pro — Area Intelligence Engine
Comprehensive area/locality data ranked by affluence tiers.

Tier 1: Premium/Posh — Businesses here WILL buy websites (high income, brand-conscious)
Tier 2: Upper-Middle — Good prospects, established businesses
Tier 3: Middle — Some potential, volume play
Tier 4: Budget — Skip (businesses won't invest in websites)

The scraper processes Tier 1 → Tier 2 → Tier 3 in order.
Tier 4 is never scraped unless explicitly requested.
"""

# ─── Area Rankings by City ─────────────────────────────────

CITY_AREAS = {
    "delhi": {
        1: [
            # Premium South Delhi + Lutyens
            "Greater Kailash 1", "Greater Kailash 2", "Defence Colony", "Hauz Khas",
            "Green Park", "Safdarjung Enclave", "Vasant Vihar", "Vasant Kunj",
            "Saket", "Chanakyapuri", "Golf Links", "Jor Bagh",
            "Lajpat Nagar", "South Extension", "Khan Market", "Connaught Place",
            "Nehru Place", "Kalkaji", "CR Park", "Panchsheel Park",
            "New Friends Colony", "Maharani Bagh", "Sundar Nagar", "Gulmohar Park",
        ],
        2: [
            # Upper-middle residential + commercial
            "Rajouri Garden", "Punjabi Bagh", "Kirti Nagar", "Janakpuri",
            "Dwarka Sector 6", "Dwarka Sector 10", "Dwarka Sector 12", "Dwarka Sector 21",
            "Model Town", "Pitampura", "Shalimar Bagh", "Paschim Vihar",
            "Rohini Sector 7", "Rohini Sector 9", "Rohini Sector 14", "Rohini Sector 24",
            "Vikaspuri", "Tilak Nagar", "Karol Bagh", "Patel Nagar",
            "Preet Vihar", "Laxmi Nagar", "Mayur Vihar Phase 1", "Mayur Vihar Phase 3",
            "Indirapuram", "Vaishali", "Kaushambi",  # Ghaziabad (NCR)
        ],
        3: [
            # Middle-class, volume areas
            "Shahdara", "Ashok Nagar", "Krishna Nagar", "Vivek Vihar",
            "GTB Nagar", "Mukherjee Nagar", "Kamla Nagar", "Shakti Nagar",
            "Naraina", "Moti Nagar", "Subhash Nagar", "Tagore Garden",
            "Uttam Nagar", "Nawada", "Najafgarh", "Palam",
            "Mehrauli", "Chattarpur", "Sangam Vihar", "Badarpur",
        ],
    },

    "mumbai": {
        1: [
            # South Mumbai + Premium West
            "Bandra West", "Juhu", "Andheri West", "Powai",
            "Lower Parel", "Worli", "Colaba", "Nariman Point",
            "Marine Drive", "Churchgate", "Fort", "Kala Ghoda",
            "Bandra Kurla Complex", "Versova", "Lokhandwala", "Santacruz West",
            "Kemps Corner", "Breach Candy", "Malabar Hill", "Pedder Road",
            "Goregaon West", "Malad West", "Kandivali West", "Borivali West",
        ],
        2: [
            "Andheri East", "Goregaon East", "Malad East", "Kandivali East",
            "Thane West", "Thane East", "Ghatkopar West", "Ghatkopar East",
            "Chembur", "Mulund West", "Mulund East", "Bhandup West",
            "Vikhroli", "Kanjurmarg", "Dadar West", "Dadar East",
            "Prabhadevi", "Mahim", "Matunga", "Sion",
            "Vashi", "Nerul", "Belapur", "Kharghar",  # Navi Mumbai
        ],
        3: [
            "Borivali East", "Dahisar", "Mira Road", "Bhayandar",
            "Vasai", "Virar", "Panvel", "Kalyan",
            "Dombivli", "Ambernath", "Badlapur", "Ulhasnagar",
            "Airoli", "Kopar Khairane", "Turbhe", "Sanpada",
        ],
    },

    "bangalore": {
        1: [
            "Koramangala", "Indiranagar", "MG Road", "Brigade Road",
            "Whitefield", "HSR Layout", "Jayanagar", "JP Nagar",
            "Rajajinagar", "Malleshwaram", "Sadashivanagar", "Ulsoor",
            "Lavelle Road", "Richmond Town", "Frazer Town", "Cox Town",
            "Sankey Road", "Palace Road", "Vasanth Nagar", "Cunningham Road",
            "Bellandur", "Sarjapur Road", "Marathahalli", "Brookefield",
        ],
        2: [
            "BTM Layout", "Electronic City", "Banashankari", "Basavanagudi",
            "Vijayanagar", "Nagarbhavi", "Bannerghatta Road", "Kanakapura Road",
            "Hennur", "Hebbal", "Yelahanka", "Thanisandra",
            "RT Nagar", "HBR Layout", "Kalyan Nagar", "Kammanahalli",
            "Mahadevapura", "KR Puram", "Hoodi", "Kadugodi",
        ],
        3: [
            "Peenya", "Dasarahalli", "Vidyaranyapura", "Jakkur",
            "Bommanahalli", "Begur", "Hulimavu", "Arekere",
            "Rajarajeshwari Nagar", "Kengeri", "Uttarahalli", "Kumaraswamy Layout",
        ],
    },

    "hyderabad": {
        1: [
            "Jubilee Hills", "Banjara Hills", "Madhapur", "Gachibowli",
            "HITEC City", "Kondapur", "Kukatpally", "Begumpet",
            "Secunderabad", "Ameerpet", "Somajiguda", "Panjagutta",
            "Film Nagar", "Shaikpet", "Nanakramguda", "Financial District",
            "Himayatnagar", "Nampally", "Abids", "Basheerbagh",
        ],
        2: [
            "Miyapur", "Chandanagar", "Manikonda", "Tolichowki",
            "Attapur", "Mehdipatnam", "Masab Tank", "Lakdi Ka Pul",
            "AS Rao Nagar", "Tarnaka", "Habsiguda", "Uppal",
            "Kompally", "Alwal", "Malkajgiri", "Sainikpuri",
            "LB Nagar", "Dilsukhnagar", "Nagole", "Nacharam",
        ],
        3: [
            "Hayathnagar", "Vanasthalipuram", "Saidabad", "Malakpet",
            "Charminar", "Moosapet", "Balanagar", "Jeedimetla",
            "Medchal", "Shamirpet", "Ghatkesar", "Pocharam",
        ],
    },

    "pune": {
        1: [
            "Koregaon Park", "Kalyani Nagar", "Viman Nagar", "Baner",
            "Aundh", "Kothrud", "Deccan", "Shivajinagar",
            "Magarpatta", "Kharadi", "Hinjewadi Phase 1", "Hinjewadi Phase 2",
            "Boat Club Road", "MG Road Pune", "FC Road", "JM Road",
            "Erandwane", "Prabhat Road", "Law College Road", "Bund Garden Road",
            "Wakad", "Balewadi", "Pashan", "SB Road",
        ],
        2: [
            "Hadapsar", "Kondhwa", "NIBM", "Undri",
            "Swargate", "Salisbury Park", "Bibwewadi", "Katraj",
            "Warje", "Karve Nagar", "Bavdhan", "Sus Road",
            "Pimple Saudagar", "Pimple Nilakh", "Ravet", "Tathawade",
            "Vishrantwadi", "Dhanori", "Lohegaon", "Yerawada",
        ],
        3: [
            "Hadapsar Industrial", "Mundhwa", "Manjri", "Fursungi",
            "Chakan", "Talegaon", "Alandi", "Dehu Road",
            "Bhosari", "Chinchwad", "Akurdi", "Nigdi",
        ],
    },

    "chennai": {
        1: [
            "T Nagar", "Nungambakkam", "Anna Nagar", "Alwarpet",
            "Mylapore", "Adyar", "Besant Nagar", "Velachery",
            "ECR", "Thiruvanmiyur", "Kotturpuram", "RA Puram",
            "Boat Club Area", "Cenotaph Road", "Cathedral Road", "Haddows Road",
            "Kilpauk", "Chetpet", "Egmore", "Thousand Lights",
            "OMR Sholinganallur", "OMR Perungudi", "Guindy", "Ashok Nagar",
        ],
        2: [
            "Porur", "Vadapalani", "Kodambakkam", "West Mambalam",
            "Saidapet", "Teynampet", "Royapettah", "Triplicane",
            "Chromepet", "Pallavaram", "Tambaram", "Medavakkam",
            "Mogappair", "Ambattur", "Avadi", "Poonamallee",
            "Perambur", "Kolathur", "Villivakkam", "Korattur",
        ],
        3: [
            "Madhavaram", "Manali", "Tiruvottiyur", "Ennore",
            "Kundrathur", "Mangadu", "Pammal", "Anakaputhur",
            "Sholavaram", "Red Hills", "Puzhal", "Madhuravoyal",
        ],
    },

    "kolkata": {
        1: [
            "Park Street", "Camac Street", "Ballygunge", "Alipore",
            "Bhowanipore", "Gariahat", "Southern Avenue", "Lake Gardens",
            "Salt Lake Sector 1", "Salt Lake Sector 3", "Salt Lake Sector 5",
            "New Town", "Rajarhat", "Golf Green", "Jodhpur Park",
            "Shakespeare Sarani", "Theatre Road", "Loudon Street", "Elgin Road",
        ],
        2: [
            "Tollygunge", "Jadavpur", "Garia", "Kasba",
            "EM Bypass", "Ruby", "Behala", "Thakurpukur",
            "Dum Dum", "Baranagar", "Belgharia", "Lake Town",
            "Ultadanga", "Phool Bagan", "Sealdah", "Esplanade",
            "Howrah", "Shibpur", "Belur", "Liluah",
        ],
        3: [
            "Barrackpore", "Titagarh", "Khardah", "Sodepur",
            "Naihati", "Bhatpara", "Kalyani", "Chandannagar",
            "Serampore", "Rishra", "Uttarpara", "Hooghly",
        ],
    },

    "ahmedabad": {
        1: [
            "Vastrapur", "Bodakdev", "Satellite", "Prahlad Nagar",
            "SG Highway", "Thaltej", "Ambli", "Jodhpur Cross Roads",
            "CG Road", "Ashram Road", "Law Garden", "Paldi",
            "Navrangpura", "Ellis Bridge", "Stadium Road", "Income Tax",
            "Gulbai Tekra", "University Area", "Drive In Road", "Memnagar",
        ],
        2: [
            "Bopal", "South Bopal", "Ghuma", "Shilaj",
            "Maninagar", "Ghodasar", "Isanpur", "Narol",
            "Chandkheda", "Motera", "Sabarmati", "Ranip",
            "Gota", "New CG Road", "Sola", "Science City",
            "Nikol", "Naroda", "Vastral", "Odhav",
        ],
    },

    "jaipur": {
        1: [
            "C Scheme", "Malviya Nagar", "Vaishali Nagar", "Tonk Road",
            "MI Road", "Ashok Nagar", "Civil Lines", "Raja Park",
            "Mansarovar", "Pratap Nagar", "Jawahar Nagar", "Tilak Nagar",
            "Bani Park", "Adarsh Nagar", "Shyam Nagar", "Durgapura",
        ],
        2: [
            "Sodala", "Gopalpura", "Sanganer", "Sitapura",
            "Jagatpura", "Ajmer Road", "Sikar Road", "Nirman Nagar",
            "Vidhyadhar Nagar", "Jhotwara", "Murlipura", "Amer Road",
        ],
    },
}

# Aliases
CITY_AREAS["new delhi"] = CITY_AREAS["delhi"]
CITY_AREAS["bengaluru"] = CITY_AREAS["bangalore"]
CITY_AREAS["calcutta"] = CITY_AREAS["kolkata"]
CITY_AREAS["bombay"] = CITY_AREAS["mumbai"]
CITY_AREAS["noida"] = {
    1: ["Sector 18", "Sector 62", "Sector 15", "Sector 16",
        "Sector 44", "Sector 50", "Sector 104", "Sector 137"],
    2: ["Sector 63", "Sector 135", "Sector 76", "Sector 78",
        "Greater Noida West", "Greater Noida Pari Chowk", "Knowledge Park"],
}
CITY_AREAS["gurgaon"] = CITY_AREAS.get("gurugram", {
    1: ["DLF Phase 1", "DLF Phase 2", "DLF Phase 3", "DLF Phase 5",
        "Golf Course Road", "MG Road Gurgaon", "Sushant Lok", "South City 1",
        "Sector 14", "Sector 29", "Sector 43", "Sector 44",
        "Udyog Vihar", "Cyber City", "Cyber Hub", "Huda City Centre"],
    2: ["Sector 56", "Sector 57", "Sector 82", "Sector 83",
        "Sector 84", "Sector 90", "Palam Vihar", "Sohna Road",
        "New Gurgaon", "Manesar", "Dwarka Expressway", "SPR Road"],
})
CITY_AREAS["gurugram"] = CITY_AREAS["gurgaon"]


def get_ranked_areas(location: str, max_tier: int = 2) -> list:
    """
    Get areas for a city, ranked by affluence.
    Returns areas from Tier 1 through max_tier.
    
    Args:
        location: City name (e.g. "Delhi", "Mumbai")
        max_tier: Maximum tier to include (1=premium only, 2=premium+upper, 3=all)
    
    Returns:
        List of area names, ordered premium-first
    """
    loc = location.lower().strip()
    
    # Find matching city
    matched_city = None
    for city_key in CITY_AREAS:
        if city_key in loc or loc in city_key:
            matched_city = city_key
            break
    
    if not matched_city:
        return []
    
    city_data = CITY_AREAS[matched_city]
    areas = []
    for tier in range(1, max_tier + 1):
        if tier in city_data:
            areas.extend(city_data[tier])
    
    return areas


def get_area_tier(location: str, area: str) -> int:
    """Get the tier of a specific area. Returns 0 if not found."""
    loc = location.lower().strip()
    for city_key in CITY_AREAS:
        if city_key in loc or loc in city_key:
            city_data = CITY_AREAS[city_key]
            for tier, areas in city_data.items():
                if area in areas:
                    return tier
            return 0
    return 0


def get_supported_cities() -> list:
    """Return list of cities with area intelligence."""
    seen = set()
    cities = []
    for key in CITY_AREAS:
        # Skip aliases
        if CITY_AREAS[key] is CITY_AREAS.get("delhi") and key not in ("delhi",):
            continue
        if CITY_AREAS[key] is CITY_AREAS.get("mumbai") and key not in ("mumbai",):
            continue
        if CITY_AREAS[key] is CITY_AREAS.get("bangalore") and key not in ("bangalore",):
            continue
        if CITY_AREAS[key] is CITY_AREAS.get("kolkata") and key not in ("kolkata",):
            continue
        if CITY_AREAS[key] is CITY_AREAS.get("gurgaon") and key not in ("gurgaon",):
            continue
        if key not in seen:
            seen.add(key)
            total = sum(len(v) for v in CITY_AREAS[key].values())
            cities.append({"name": key.title(), "areas": total})
    return cities
