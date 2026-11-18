import os 
import re 
import certifi
import airportsdata
import pycountry
import requests
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

API_KEY = os.getenv("AVIATIONSTACK_API_KEY")




BASE_URL = "https://api.aviationstack.com/v1/flights"


AIRPORTS = airportsdata.load("IATA")



COUNTRY_ALIASES = {
     # United States
    "usa": "US",
    "u.s.a": "US",
    "u.s.": "US",
    "america": "US",
    "united states": "US",
    "united states of america": "US",

    # United Kingdom
    "uk": "GB",
    "u.k.": "GB",
    "britain": "GB",
    "great britain": "GB",
    "england": "GB",

    # UAE
    "uae": "AE",
    "emirates": "AE",
    "dubai": "AE",

    # Korea
    "south korea": "KR",
    "korea": "KR",
    "north korea": "KP",

    # Europe
    "russia": "RU",
    "turkey": "TR",
    "turkiye": "TR",
    "holland": "NL",
    "czech republic": "CZ",
    "slovakia": "SK",
    "swiss": "CH",
    "switzerland": "CH",
    "greek": "GR",
    "greece": "GR",

    # Asia
    "india": "IN",
    "bharat": "IN",
    "japan": "JP",
    "china": "CN",
    "taiwan": "TW",
    "hong kong": "HK",
    "macau": "MO",
    "vietnam": "VN",
    "viet nam": "VN",
    "iran": "IR",
    "iraq": "IQ",
    "syria": "SY",
    "laos": "LA",
    "burma": "MM",
    "myanmar": "MM",
    "cambodia": "KH",
    "bhutan": "BT",
    "nepal": "NP",
    "maldives": "MV",
    "sri lanka": "LK",
    "east timor": "TL",
    "timor leste": "TL",
    "brunei": "BN",

    # Middle East
    "saudi arabia": "SA",
    "ksa": "SA",
    "israel": "IL",
    "palestine": "PS",
    "oman": "OM",
    "kuwait": "KW",
    "bahrain": "BH",

    # Africa
    "south africa": "ZA",
    "egypt": "EG",
    "morocco": "MA",
    "algeria": "DZ",
    "tunisia": "TN",
    "libya": "LY",
    "nigeria": "NG",
    "kenya": "KE",
    "ethiopia": "ET",
    "ghana": "GH",
    "uganda": "UG",
    "tanzania": "TZ",
    "zimbabwe": "ZW",
    "zambia": "ZM",
    "senegal": "SN",
    "cameroon": "CM",
    "angola": "AO",
    "botswana": "BW",
    "namibia": "NA",

    # North America
    "canada": "CA",
    "mexico": "MX",
    "costa rica": "CR",
    "panama": "PA",
    "jamaica": "JM",
    "cuba": "CU",
    "bahamas": "BS",
    "dominican republic": "DO",

    # South America
    "brazil": "BR",
    "argentina": "AR",
    "chile": "CL",
    "colombia": "CO",
    "peru": "PE",
    "venezuela": "VE",
    "ecuador": "EC",
    "uruguay": "UY",
    "paraguay": "PY",
    "bolivia": "BO",
    "guyana": "GY",
    "suriname": "SR",

    # Oceania
    "australia": "AU",
    "new zealand": "NZ",
    "fiji": "FJ",
    "papua new guinea": "PG",
    "samoa": "WS",
    "tonga": "TO",
    "vanuatu": "VU",
}


# Preferred main airport for country-level search

# Preferred main airport for country-level search
COUNTRY_MAIN_AIRPORT = {

    # Asia
    "BD": "DAC",  # Bangladesh
    "IN": "DEL",  # India
    "JP": "NRT",  # Japan
    "CN": "PEK",  # China
    "KR": "ICN",  # South Korea
    "KP": "FNJ",  # North Korea
    "NP": "KTM",  # Nepal
    "BT": "PBH",  # Bhutan
    "LK": "CMB",  # Sri Lanka
    "MV": "MLE",  # Maldives
    "PK": "KHI",  # Pakistan
    "AF": "KBL",  # Afghanistan
    "TH": "BKK",  # Thailand
    "VN": "SGN",  # Vietnam
    "MY": "KUL",  # Malaysia
    "SG": "SIN",  # Singapore
    "ID": "CGK",  # Indonesia
    "PH": "MNL",  # Philippines
    "KH": "PNH",  # Cambodia
    "LA": "VTE",  # Laos
    "MM": "RGN",  # Myanmar
    "BN": "BWN",  # Brunei
    "TW": "TPE",  # Taiwan
    "MN": "UBN",  # Mongolia
    "KZ": "ALA",  # Kazakhstan
    "UZ": "TAS",  # Uzbekistan
    "KG": "BSZ",  # Kyrgyzstan
    "TJ": "DYU",  # Tajikistan
    "TM": "ASB",  # Turkmenistan
    "AZ": "GYD",  # Azerbaijan
    "GE": "TBS",  # Georgia
    "AM": "EVN",  # Armenia

    # Middle East
    "AE": "DXB",  # UAE
    "SA": "JED",  # Saudi Arabia
    "QA": "DOH",  # Qatar
    "KW": "KWI",  # Kuwait
    "BH": "BAH",  # Bahrain
    "OM": "MCT",  # Oman
    "YE": "SAH",  # Yemen
    "IQ": "BGW",  # Iraq
    "IR": "IKA",  # Iran
    "IL": "TLV",  # Israel
    "JO": "AMM",  # Jordan
    "LB": "BEY",  # Lebanon
    "SY": "DAM",  # Syria
    "TR": "IST",  # Turkey

    # Europe
    "GB": "LHR",  # United Kingdom
    "FR": "CDG",  # France
    "DE": "FRA",  # Germany
    "IT": "FCO",  # Italy
    "ES": "MAD",  # Spain
    "PT": "LIS",  # Portugal
    "NL": "AMS",  # Netherlands
    "BE": "BRU",  # Belgium
    "CH": "ZRH",  # Switzerland
    "AT": "VIE",  # Austria
    "IE": "DUB",  # Ireland
    "GR": "ATH",  # Greece
    "PL": "WAW",  # Poland
    "CZ": "PRG",  # Czech Republic
    "SK": "BTS",  # Slovakia
    "HU": "BUD",  # Hungary
    "RO": "OTP",  # Romania
    "BG": "SOF",  # Bulgaria
    "HR": "ZAG",  # Croatia
    "SI": "LJU",  # Slovenia
    "RS": "BEG",  # Serbia
    "BA": "SJJ",  # Bosnia and Herzegovina
    "ME": "TGD",  # Montenegro
    "AL": "TIA",  # Albania
    "MK": "SKP",  # North Macedonia
    "XK": "PRN",  # Kosovo
    "SE": "ARN",  # Sweden
    "NO": "OSL",  # Norway
    "DK": "CPH",  # Denmark
    "FI": "HEL",  # Finland
    "IS": "KEF",  # Iceland
    "RU": "SVO",  # Russia
    "UA": "KBP",  # Ukraine
    "BY": "MSQ",  # Belarus
    "MD": "RMO",  # Moldova
    "CY": "LCA",  # Cyprus
    "MT": "MLA",  # Malta
    "LU": "LUX",  # Luxembourg
    "EE": "TLL",  # Estonia
    "LV": "RIX",  # Latvia
    "LT": "VNO",  # Lithuania

    # North America
    "US": "JFK",  # United States
    "CA": "YYZ",  # Canada
    "MX": "MEX",  # Mexico
    "GT": "GUA",  # Guatemala
    "BZ": "BZE",  # Belize
    "CR": "SJO",  # Costa Rica
    "PA": "PTY",  # Panama
    "SV": "SAL",  # El Salvador
    "HN": "SAP",  # Honduras
    "NI": "MGA",  # Nicaragua
    "CU": "HAV",  # Cuba
    "JM": "KIN",  # Jamaica
    "HT": "PAP",  # Haiti
    "DO": "SDQ",  # Dominican Republic
    "BS": "NAS",  # Bahamas
    "BB": "BGI",  # Barbados
    "TT": "POS",  # Trinidad and Tobago

    # South America
    "BR": "GRU",  # Brazil
    "AR": "EZE",  # Argentina
    "CL": "SCL",  # Chile
    "CO": "BOG",  # Colombia
    "PE": "LIM",  # Peru
    "VE": "CCS",  # Venezuela
    "EC": "UIO",  # Ecuador
    "BO": "VVI",  # Bolivia
    "PY": "ASU",  # Paraguay
    "UY": "MVD",  # Uruguay
    "GY": "GEO",  # Guyana
    "SR": "PBM",  # Suriname

    # Africa
    "ZA": "JNB",  # South Africa
    "EG": "CAI",  # Egypt
    "MA": "CMN",  # Morocco
    "DZ": "ALG",  # Algeria
    "TN": "TUN",  # Tunisia
    "LY": "MJI",  # Libya
    "NG": "LOS",  # Nigeria
    "KE": "NBO",  # Kenya
    "ET": "ADD",  # Ethiopia
    "GH": "ACC",  # Ghana
    "UG": "EBB",  # Uganda
    "TZ": "DAR",  # Tanzania
    "RW": "KGL",  # Rwanda
    "ZM": "LUN",  # Zambia
    "ZW": "HRE",  # Zimbabwe
    "BW": "GBE",  # Botswana
    "NA": "WDH",  # Namibia
    "AO": "LAD",  # Angola
    "SN": "DSS",  # Senegal
    "CI": "ABJ",  # Ivory Coast
    "CM": "DLA",  # Cameroon
    "MU": "MRU",  # Mauritius
    "MG": "TNR",  # Madagascar
    "MZ": "MPM",  # Mozambique
    "SD": "KRT",  # Sudan
    "SS": "JUB",  # South Sudan
    "ML": "BKO",  # Mali
    "BF": "OUA",  # Burkina Faso
    "NE": "NIM",  # Niger
    "TG": "LFW",  # Togo
    "BJ": "COO",  # Benin
    "GA": "LBV",  # Gabon
    "CD": "FIH",  # DR Congo
    "CG": "BZV",  # Republic of Congo

    # Oceania
    "AU": "SYD",  # Australia
    "NZ": "AKL",  # New Zealand
    "FJ": "NAN",  # Fiji
    "PG": "POM",  # Papua New Guinea
    "WS": "APW",  # Samoa
    "TO": "TBU",  # Tonga
    "VU": "VLI",  # Vanuatu
    "SB": "HIR",  # Solomon Islands
    "NC": "NOU",  # New Caledonia
    "PF": "PPT",  # French Polynesia
}






CITY_MAIN_AIRPORT = {

    # India
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "kolkata": "CCU",
    "chennai": "MAA",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "hyderabad": "HYD",
    "pune": "PNQ",
    "ahmedabad": "AMD",
    "jaipur": "JAI",
    "lucknow": "LKO",
    "bhopal": "BHO",
    "indore": "IDR",
    "patna": "PAT",
    "goa": "GOI",
    "kochi": "COK",
    "cochin": "COK",
    "thiruvananthapuram": "TRV",
    "chandigarh": "IXC",
    "varanasi": "VNS",
    "nagpur": "NAG",
    "surat": "STV",
    "amritsar": "ATQ",
    "guwahati": "GAU",
    "ranchi": "IXR",
    "bhubaneswar": "BBI",
    "visakhapatnam": "VTZ",
    "mangalore": "IXE",
    "dehradun": "DED",
    "srinagar": "SXR",
    "jodhpur": "JDH",
    "udaipur": "UDR",

    # Bangladesh
    "dhaka": "DAC",
    "chittagong": "CGP",
    "chattogram": "CGP",
    "sylhet": "ZYL",

    # Japan
    "tokyo": "NRT",
    "osaka": "KIX",
    "kyoto": "KIX",
    "nagoya": "NGO",
    "sapporo": "CTS",
    "fukuoka": "FUK",
    "hiroshima": "HIJ",
    "okinawa": "OKA",

    # China
    "beijing": "PEK",
    "shanghai": "PVG",
    "guangzhou": "CAN",
    "shenzhen": "SZX",
    "chengdu": "CTU",
    "hong kong": "HKG",
    "macau": "MFM",

    # South Korea
    "seoul": "ICN",
    "busan": "PUS",
    "jeju": "CJU",

    # Southeast Asia
    "singapore": "SIN",
    "kuala lumpur": "KUL",
    "penang": "PEN",
    "langkawi": "LGK",
    "bangkok": "BKK",
    "phuket": "HKT",
    "chiang mai": "CNX",
    "hanoi": "HAN",
    "ho chi minh city": "SGN",
    "saigon": "SGN",
    "da nang": "DAD",
    "jakarta": "CGK",
    "bali": "DPS",
    "denpasar": "DPS",
    "manila": "MNL",
    "cebu": "CEB",
    "phnom penh": "PNH",
    "siem reap": "SAI",
    "yangon": "RGN",
    "vientiane": "VTE",
    "bandar seri begawan": "BWN",

    # Nepal and Bhutan
    "kathmandu": "KTM",
    "pokhara": "PKR",
    "paro": "PBH",

    # Middle East
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "sharjah": "SHJ",
    "doha": "DOH",
    "riyadh": "RUH",
    "jeddah": "JED",
    "medina": "MED",
    "muscat": "MCT",
    "kuwait city": "KWI",
    "manama": "BAH",
    "tehran": "IKA",
    "baghdad": "BGW",
    "amman": "AMM",
    "beirut": "BEY",
    "tel aviv": "TLV",

    # Europe
    "london": "LHR",
    "paris": "CDG",
    "rome": "FCO",
    "madrid": "MAD",
    "barcelona": "BCN",
    "frankfurt": "FRA",
    "berlin": "BER",
    "munich": "MUC",
    "amsterdam": "AMS",
    "brussels": "BRU",
    "zurich": "ZRH",
    "geneva": "GVA",
    "vienna": "VIE",
    "prague": "PRG",
    "budapest": "BUD",
    "warsaw": "WAW",
    "lisbon": "LIS",
    "porto": "OPO",
    "athens": "ATH",
    "istanbul": "IST",
    "antalya": "AYT",
    "moscow": "SVO",
    "st petersburg": "LED",
    "copenhagen": "CPH",
    "stockholm": "ARN",
    "oslo": "OSL",
    "helsinki": "HEL",
    "dublin": "DUB",
    "edinburgh": "EDI",
    "manchester": "MAN",
    "nice": "NCE",
    "milan": "MXP",
    "venice": "VCE",
    "florence": "FLR",
    "naples": "NAP",
    "seville": "SVQ",
    "malaga": "AGP",
    "reykjavik": "KEF",
    "bucharest": "OTP",
    "sofia": "SOF",
    "zagreb": "ZAG",
    "belgrade": "BEG",
    "tallinn": "TLL",
    "riga": "RIX",
    "vilnius": "VNO",

    # North America
    "new york": "JFK",
    "los angeles": "LAX",
    "san francisco": "SFO",
    "chicago": "ORD",
    "washington": "IAD",
    "boston": "BOS",
    "miami": "MIA",
    "las vegas": "LAS",
    "orlando": "MCO",
    "seattle": "SEA",
    "houston": "IAH",
    "dallas": "DFW",
    "atlanta": "ATL",
    "denver": "DEN",
    "san diego": "SAN",
    "toronto": "YYZ",
    "vancouver": "YVR",
    "montreal": "YUL",
    "calgary": "YYC",
    "ottawa": "YOW",
    "mexico city": "MEX",
    "cancun": "CUN",
    "havana": "HAV",
    "panama city": "PTY",
    "san jose": "SJO",

    # South America
    "sao paulo": "GRU",
    "rio de janeiro": "GIG",
    "buenos aires": "EZE",
    "santiago": "SCL",
    "bogota": "BOG",
    "lima": "LIM",
    "quito": "UIO",
    "caracas": "CCS",
    "montevideo": "MVD",
    "la paz": "LPB",
    "asuncion": "ASU",

    # Africa
    "johannesburg": "JNB",
    "cape town": "CPT",
    "cairo": "CAI",
    "casablanca": "CMN",
    "marrakech": "RAK",
    "lagos": "LOS",
    "nairobi": "NBO",
    "addis ababa": "ADD",
    "accra": "ACC",
    "dar es salaam": "DAR",
    "kampala": "EBB",
    "kigali": "KGL",
    "tunis": "TUN",
    "algiers": "ALG",
    "dakar": "DSS",
    "mauritius": "MRU",
    "mahe": "SEZ",

    # Australia and Oceania
    "sydney": "SYD",
    "melbourne": "MEL",
    "brisbane": "BNE",
    "perth": "PER",
    "adelaide": "ADL",
    "canberra": "CBR",
    "gold coast": "OOL",
    "darwin": "DRW",
    "auckland": "AKL",
    "wellington": "WLG",
    "christchurch": "CHC",
    "fiji": "NAN",
    "suva": "SUV",
}



def clean_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    stop_words = [
        "flight", "flights", "ticket", "tickets", "trip", "travel",
        "plan", "complete", "days", "day", "including", "hotel",
        "hotels", "sightseeing", "under", "budget", "info", "information"
    ]
    words = [w for w in text.split() if w not in stop_words]
    return " ".join(words).strip()



def country_name_to_code(text: str):
    text = clean_text(text)

    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]

    try:
        country = pycountry.countries.lookup(text)
        return country.alpha_2
    except LookupError:
        pass

    # Detect country name inside longer text
    for country in pycountry.countries:
        country_name = country.name.lower()
        if country_name in text:
            return country.alpha_2

    for alias, code in COUNTRY_ALIASES.items():
        if alias in text:
            return code

    return None



def airport_country_matches(airport: dict, country_code: str) -> bool:
    airport_country = str(airport.get("country", "")).upper().strip()

    if airport_country == country_code:
        return True

    try:
        country = pycountry.countries.get(alpha_2=country_code)
        if country and airport_country.lower() == country.name.lower():
            return True
    except Exception:
        pass

    return False




def get_best_airport_for_country(country_code: str):
    preferred = COUNTRY_MAIN_AIRPORT.get(country_code)

    if preferred and preferred in AIRPORTS:
        return preferred

    candidates = []

    for iata, airport in AIRPORTS.items():
        if not iata:
            continue

        if airport_country_matches(airport, country_code):
            name = str(airport.get("name", "")).lower()
            city = str(airport.get("city", "")).lower()

            score = 0

            if "international" in name:
                score += 50
            if "intl" in name:
                score += 40
            if "capital" in name:
                score += 20
            if city:
                score += 5

            candidates.append((score, iata))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]




def resolve_location_to_iata(location: str):
    """
    Converts country/city/airport/IATA into IATA code.

    Examples:
    Bangladesh -> DAC
    Japan -> NRT
    Dhaka -> DAC
    Tokyo -> NRT
    DAC -> DAC
    """

    if not location:
        return None

    raw_location = location.strip()

    # Direct IATA code
    if re.fullmatch(r"[A-Za-z]{3}", raw_location):
        code = raw_location.upper()
        if code in AIRPORTS:
            return code

    location_clean = clean_text(raw_location)

    if not location_clean:
        return None

    # City preferred airport
    if location_clean in CITY_MAIN_AIRPORT:
        return CITY_MAIN_AIRPORT[location_clean]

    # Country preferred airport
    country_code = country_name_to_code(location_clean)
    if country_code:
        airport = get_best_airport_for_country(country_code)
        if airport:
            return airport

    # Exact city match from airport database
    city_matches = []

    for iata, airport in AIRPORTS.items():
        city = str(airport.get("city", "")).lower().strip()
        name = str(airport.get("name", "")).lower().strip()

        score = 0

        if city == location_clean:
            score += 100
        elif location_clean in city:
            score += 70

        if location_clean in name:
            score += 50

        if "international" in name:
            score += 10

        if score > 0:
            city_matches.append((score, iata))

    if city_matches:
        city_matches.sort(reverse=True)
        return city_matches[0][1]

    return None




def find_location_mentions(query: str):
    """
    Finds country or city names inside a natural language query.
    """

    q = query.lower()
    mentions = []

    # Country aliases
    for alias in COUNTRY_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", q):
            mentions.append(alias)

    # Country names from pycountry
    for country in pycountry.countries:
        name = country.name.lower()
        if len(name) >= 4 and re.search(rf"\b{re.escape(name)}\b", q):
            mentions.append(name)

    # City names from our preferred city map
    for city in CITY_MAIN_AIRPORT:
        if re.search(rf"\b{re.escape(city)}\b", q):
            mentions.append(city)

    # Remove duplicate while keeping order
    unique_mentions = []
    for item in mentions:
        if item not in unique_mentions:
            unique_mentions.append(item)

    return unique_mentions


def parse_route(query: str):
    """
    Returns:
    dep_iata, arr_iata

    Can return:
    None, None  -> global live flights
    DEL, DXB    -> filtered route
    DEL, None   -> all flights from DEL
    None, NRT   -> all flights to NRT
    """

    q = query.strip()
    q_lower = q.lower()

    # Global / all-country query
    global_keywords = [
        "all country",
        "all countries",
        "every country",
        "any country",
        "different countries",
        "multiple countries",
        "global flight",
        "global flights",
        "all flight",
        "all flights",
        "worldwide flight",
        "worldwide flights",
        "international flights",
        "international flight",
        "worldwide",
        "globally",
        "around the world",
        "across the world",
        "around the globe",
        "across the globe",
        "worldwide destinations",
        "global destinations",
        "anywhere in the world",
        "anywhere worldwide",
        "any destination",
        "any country in the world",
        "any place in the world",
        "explore the world",
        "travel the world",
        "visit the world",
        "world tour",
        "international travel",
        "international trip",
        "foreign countries",
        "overseas destinations",
        "flights everywhere",
        "flights around the world",
        "flights to anywhere",
        "flights to any country",
        "flights to different countries",
        "search worldwide flights",
        "search international flights",
    ]

    if any(keyword in q_lower for keyword in global_keywords):
        return None, None

    # Direct IATA code route: DEL to DXB
    codes = re.findall(r"\b[A-Z]{3}\b", q)

    if len(codes) >= 2:
        dep = codes[0].upper()
        arr = codes[1].upper()
        return dep, arr

    # Pattern: from X to Y
    match = re.search(
        r"\bfrom\s+(.+?)\s+\bto\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at)\b|[.!?]|$)",
        q_lower,
    )

    if match:
        origin_text = match.group(1)
        dest_text = match.group(2)

        dep_iata = resolve_location_to_iata(origin_text)
        arr_iata = resolve_location_to_iata(dest_text)

        return dep_iata, arr_iata

    # Pattern: to Y from X
    match = re.search(
        r"\bto\s+(.+?)\s+\bfrom\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at)\b|[.!?]|$)",
        q_lower,
    )

    if match:
        dest_text = match.group(1)
        origin_text = match.group(2)

        dep_iata = resolve_location_to_iata(origin_text)
        arr_iata = resolve_location_to_iata(dest_text)

        return dep_iata, arr_iata

    # Pattern: flights from X
    match = re.search(r"\bfrom\s+(.+?)(?:[.!?]|$)", q_lower)

    if match:
        origin_text = match.group(1)
        dep_iata = resolve_location_to_iata(origin_text)
        return dep_iata, None

    # Pattern: flights to X
    match = re.search(r"\bto\s+(.+?)(?:[.!?]|$)", q_lower)

    if match:
        dest_text = match.group(1)
        arr_iata = resolve_location_to_iata(dest_text)
        return None, arr_iata

    # Fallback: find country/city mentions
    mentions = find_location_mentions(q)

    if len(mentions) >= 2:
        dep_iata = resolve_location_to_iata(mentions[0])
        arr_iata = resolve_location_to_iata(mentions[1])
        return dep_iata, arr_iata

    if len(mentions) == 1:
        arr_iata = resolve_location_to_iata(mentions[0])
        return None, arr_iata

    return None, None

def format_flight(flight: dict):
    airline = flight.get("airline", {}).get("name") or "Unknown airline"
    flight_number = flight.get("flight", {}).get("iata") or "Unknown flight number"
    status = flight.get("flight_status") or "Unknown"

    dep = flight.get("departure", {}) or {}
    arr = flight.get("arrival", {}) or {}

    dep_airport = dep.get("airport") or "Unknown departure airport"
    dep_iata = dep.get("iata") or "Unknown"
    dep_terminal = dep.get("terminal") or "N/A"
    dep_gate = dep.get("gate") or "N/A"
    dep_scheduled = dep.get("scheduled") or "Unknown"
    dep_delay = dep.get("delay")
    dep_delay_text = f"{dep_delay} minutes" if dep_delay is not None else "N/A"

    arr_airport = arr.get("airport") or "Unknown arrival airport"
    arr_iata = arr.get("iata") or "Unknown"
    arr_terminal = arr.get("terminal") or "N/A"
    arr_gate = arr.get("gate") or "N/A"
    arr_scheduled = arr.get("scheduled") or "Unknown"
    arr_delay = arr.get("delay")
    arr_delay_text = f"{arr_delay} minutes" if arr_delay is not None else "N/A"

    return f"""
Airline: {airline}
Flight: {flight_number}
Status: {status}

Departure:
- Airport: {dep_airport}
- IATA: {dep_iata}
- Terminal: {dep_terminal}
- Gate: {dep_gate}
- Scheduled: {dep_scheduled}
- Delay: {dep_delay_text}

Arrival:
- Airport: {arr_airport}
- IATA: {arr_iata}
- Terminal: {arr_terminal}
- Gate: {arr_gate}
- Scheduled: {arr_scheduled}
- Delay: {arr_delay_text}
""".strip()


def search_flights(query: str, limit: int = 10):
    if not API_KEY:
        return (
            "Flight API error: AVIATIONSTACK_API_KEY is missing.\n"
            "Please add this in your .env file:\n"
            "AVIATIONSTACK_API_KEY=your_api_key_here"
        )

    dep_iata, arr_iata = parse_route(query)

    params = {
        "access_key": API_KEY,
        "limit": min(limit, 100),
    }

    if dep_iata:
        params["dep_iata"] = dep_iata

    if arr_iata:
        params["arr_iata"] = arr_iata

    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        data = response.json()
    except requests.exceptions.RequestException as e:
        return f"Flight API request failed: {e}"
    except ValueError:
        return "Flight API returned invalid JSON."

    if "error" in data:
        error = data["error"]
        return (
            "Flight API error:\n"
            f"Code: {error.get('code', 'Unknown')}\n"
            f"Message: {error.get('message', 'Unknown error')}"
        )

    flight_data = data.get("data", [])

    if not flight_data:
        route_text = ""

        if dep_iata and arr_iata:
            route_text = f" for route {dep_iata} to {arr_iata}"
        elif dep_iata:
            route_text = f" from {dep_iata}"
        elif arr_iata:
            route_text = f" to {arr_iata}"

        return (
            f"No live flight data found{route_text}.\n\n"
            "Note: AviationStack provides live/status flight data, not ticket prices. "
            "For actual fare prices, use a flight-pricing API such as Amadeus."
        )

    route_info = "Global live flights"

    if dep_iata and arr_iata:
        route_info = f"Live flights from {dep_iata} to {arr_iata}"
    elif dep_iata:
        route_info = f"Live flights from {dep_iata}"
    elif arr_iata:
        route_info = f"Live flights to {arr_iata}"

    formatted_flights = [format_flight(flight) for flight in flight_data[:limit]]

    return f"{route_info}\n\n" + "\n\n---\n\n".join(formatted_flights)


if __name__ == "__main__":
    print(search_flights("Plan a 7 days Japan trip from Bangladesh"))
    print("\n" + "=" * 80 + "\n")
    print(search_flights("all country flight info"))