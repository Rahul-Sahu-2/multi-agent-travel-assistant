import os
import certifi
from dotenv import load_dotenv

load_dotenv()
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from typing import Any, TypedDict, Annotated
import operator
import uuid
import datetime
import asyncio
import json
import psycopg
from psycopg.rows import dict_row
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command, interrupt
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_groq import ChatGroq


from mcp_client import (
    tavily_mcp_search,
    tavily_hotel_research,
    aviation_route_schedule,
    aviation_departures_to,
    aviation_mcp_call,
    extract_destination,
)

try:
    # Offline helper (airport database) - only used to turn "Tokyo" into "NRT".
    from tools.flight_tool import resolve_location_to_iata
except Exception as _exc:  # pragma: no cover
    print(f"IATA resolver unavailable: {_exc}", flush=True)
    resolve_location_to_iata = None

from tools.weather_tool import (
    get_current_weather,
    get_weather_forecast,
)


def get_database_url():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. "
            "Please add your Render PostgreSQL External Database URL to .env"
        )

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")

# =========================
# LLM - original model kept
# =========================
llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=GROQ_API_KEY,
    max_tokens=2500,          # caps output so input + output stays under Groq TPM limit
    reasoning_effort="low",   # fewer hidden reasoning tokens
    max_retries=1,
)

# =========================
# State - original fields kept, new control fields added
# =========================
class TravelState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str

    # Supervisor + guardrail state
    guardrail_allowed: bool
    guardrail_reason: str
    selected_agents: list[str]
    trip_constraints: dict[str, Any]
    supervisor_reasoning: str

    # Original specialist results
    flight_results: str
    hotel_results: str
    weather_results: str
    itinerary: str

    # New budget + HITL state
    budget_results: str
    budget_summary: str
    budget_total_inr: float
    budget_limit_inr: float
    approval_request: str
    approved: bool
    human_feedback: str
    final_response: str

    llm_calls: int


# =========================
# Shared helpers
# =========================
KNOWN_AGENTS = {
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
}

AGENT_ORDER = [
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
]



# =========================
# Token-saving helpers (Groq free tier: 8000 tokens/minute)
# =========================
import re
import time
from collections import Counter

MAX_FLIGHT_CHARS = 1600
MAX_HOTEL_CHARS = 2600
MAX_WEATHER_CHARS = 1400
MAX_BUDGET_CHARS = 1600
MAX_ITINERARY_CHARS = 3500


def _clip(value: Any, max_chars: int) -> str:
    """Convert anything to text and cut it to max_chars."""
    text = value if isinstance(value, str) else str(value or "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + " ...[trimmed]"


def _invoke(messages, retries: int = 4, max_tokens: int | None = None):
    """llm.invoke with automatic wait+retry when Groq's per-minute limit is hit."""
    for attempt in range(retries + 1):
        try:
            model = llm.bind(max_tokens=max_tokens) if max_tokens else llm
            return model.invoke(messages)
        except Exception as exc:
            text = str(exc)
            is_rate_limit = "429" in text or "rate_limit" in text.lower()
            too_large = "413" in text or "too large" in text.lower()

            if too_large or not is_rate_limit or attempt == retries:
                raise

            match = re.search(r"try again in ([0-9.]+)\s*(ms|s|m)", text)
            wait = 20.0
            if match:
                value = float(match.group(1))
                unit = match.group(2)
                wait = value / 1000 if unit == "ms" else value * 60 if unit == "m" else value
                wait += 1.5
            wait = min(max(wait, 5.0), 60.0)
            print(f"Groq rate limit hit, waiting {wait:.0f}s (retry {attempt + 1}/{retries})", flush=True)
            time.sleep(wait)


def _compact_hotels(raw: Any, max_chars: int = MAX_HOTEL_CHARS) -> str:
    """Shrink Tavily MCP output to title + url + short snippet for the top results."""
    try:
        data = raw
        if isinstance(data, list):
            # langchain-mcp-adapters may return [{"type": "text", "text": "..."}]
            parts = []
            for item in data:
                if isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
                else:
                    parts.append(str(item))
            data = "\n".join(parts)

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                return _clip(data, max_chars)

        results = data.get("results", []) if isinstance(data, dict) else []
        if not results:
            return _clip(data, max_chars)

        lines = []
        for i, r in enumerate(results[:5], 1):
            title = _clip(r.get("title", "Unknown"), 90)
            url = r.get("url", "")
            snippet = _clip(r.get("content", ""), 280)
            lines.append(f"{i}. {title} ({url}): {snippet}")
        return _clip("\n".join(lines), max_chars)
    except Exception:
        return _clip(raw, max_chars)


def _format_weather(current: dict, forecast: dict) -> str:
    """One short line for now + one line per forecast day (min/max/condition)."""
    lines = []

    if isinstance(current, dict):
        lines.append(
            f"Now in {current.get('city', '')}: {current.get('temperature')}C "
            f"(feels {current.get('feels_like')}C), {current.get('description', '')}, "
            f"humidity {current.get('humidity')}%, wind {current.get('wind_speed')} m/s."
        )

    days: dict[str, list] = {}
    for item in (forecast or {}).get("forecast", []):
        day = str(item.get("date_time", ""))[:10]
        days.setdefault(day, []).append(item)

    if days:
        lines.append("Forecast:")
    for day, items in days.items():
        temps = [i["temperature"] for i in items if i.get("temperature") is not None]
        cond = Counter(i.get("description", "") for i in items).most_common(1)[0][0]
        if temps:
            lines.append(f"- {day}: {min(temps):.0f}-{max(temps):.0f}C, {cond}")

    return "\n".join(lines)


# =========================
# Budget helpers - the arithmetic and the verdict are done in code, never by the LLM
# =========================
def _to_number(value: Any):
    """'₹ 1,20,000' / '34800' / 34800.0 -> float, else None."""
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d[\d,]*\.?\d*", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _inr(amount: float) -> str:
    """Format as ₹1,10,000 (Indian digit grouping)."""
    n = int(round(amount))
    digits = str(abs(n))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        digits = f"{head},{tail}"
    return f"{'-' if n < 0 else ''}₹{digits}"


_UNIT = {"k": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "crore": 1e7}


def _parse_budget_inr(budget_field: Any, query: str):
    """Return the user's total budget in INR, or None when it is not given / not in INR."""

    def to_inr(text: str, need_keyword: bool):
        t = str(text or "").lower().replace(",", "")
        if any(sym in t for sym in ("$", "usd", "€", "eur", "£", "gbp", "yen", "jpy")):
            return None  # other currencies are not converted here
        pattern = (
            r"budget[^0-9]{0,40}(\d+(?:\.\d+)?)\s*(lakhs?|lacs?|crore|k)?\b"
            if need_keyword
            else r"(\d+(?:\.\d+)?)\s*(lakhs?|lacs?|crore|k)?\b"
        )
        m = re.search(pattern, t)
        if not m:
            return None
        value = float(m.group(1)) * _UNIT.get(m.group(2) or "", 1)
        return value if value >= 1000 else None

    return to_inr(budget_field, False) or to_inr(query, True)


def _build_budget_summary(plan: dict, limit):
    """Turn the LLM's cost items into a table + verdict. Returns (markdown, total)."""
    rows = []
    for item in plan.get("items", []) if isinstance(plan, dict) else []:
        amount = _to_number(item.get("amount_inr"))
        if amount is None or amount < 0:
            continue
        basis = "Live search" if str(item.get("basis", "")).lower() == "search" else "Estimate"
        category = str(item.get("category", "Other"))[:40].replace("|", "/")
        note = str(item.get("note", ""))[:110].replace("|", "/").replace("\n", " ")
        rows.append((category, amount, basis, note))

    if not rows:
        return ("Budget total could not be calculated automatically. "
                "Please verify prices on booking websites."), None

    total = sum(r[1] for r in rows)
    live = sum(r[1] for r in rows if r[2] == "Live search")
    live_pct = round(100 * live / total) if total else 0
    biggest = max(rows, key=lambda r: r[1])

    lines = ["| Category | Cost | Basis | Note |", "|---|---:|---|---|"]
    for category, amount, basis, note in rows:
        lines.append(f"| {category} | {_inr(amount)} | {basis} | {note} |")
    lines.append(f"| **Total (all travellers)** | **{_inr(total)}** | | |")
    table = "\n".join(lines)

    if limit:
        if total <= limit:
            verdict = (
                f"✅ **This trip fits your budget.** Estimated total {_inr(total)} "
                f"vs your budget {_inr(limit)} (about {_inr(limit - total)} left)."
            )
        else:
            short = total - limit
            over_pct = round(100 * short / limit)
            verdict = (
                f"❌ **This trip is NOT possible within {_inr(limit)}.** "
                f"The estimated minimum total is **{_inr(total)}**, which is "
                f"{_inr(short)} ({over_pct}%) more than your budget."
            )
    else:
        verdict = f"Estimated total: **{_inr(total)}** (no budget was given)."

    parts = [verdict, "", table, "",
             f"Biggest cost: {biggest[0]} ({_inr(biggest[1])})."]

    if limit and total > limit:
        tips = [str(t)[:140] for t in plan.get("savings_tips", [])[:4] if t]
        if tips:
            parts += ["", "**How you could reduce the cost:**"] + [f"- {t}" for t in tips]
        parts.append(f"- Or raise the budget to at least {_inr(total)}.")

    assumptions = [str(a)[:140] for a in plan.get("assumptions", [])[:4] if a]
    if assumptions:
        parts += ["", "**Assumptions:**"] + [f"- {a}" for a in assumptions]

    parts += ["", f"_Only about {live_pct}% of this total comes from live search results; "
                  "the rest is an estimate. Prices are not an exact quote - "
                  "verify on the airline/hotel websites before booking._"]
    return "\n".join(parts), total


def _date_rule() -> str:
    today = datetime.date.today().strftime("%d %B %Y")
    return (
        f"Today is {today}. Any date before today is in the past: never tell the user "
        "to book or do anything by a past date. If the trip starts within about 2 months, "
        "tell the user to book flights immediately and that last-minute fares can be "
        "higher than the quoted price."
    )


def _trip_cities(state) -> list:
    """Cities chosen by the supervisor; falls back to the destination text."""
    constraints = state.get("trip_constraints", {}) or {}
    cities = [c for c in constraints.get("cities", []) if c]
    if cities:
        return cities[:3]
    destination = constraints.get("destination")
    return [destination] if destination else []


def _llm_text(system_prompt: str, user_prompt: str) -> str:
    response = _invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    return str(response.content)


def _json_from_llm(text: str) -> dict[str, Any]:
    """Extract the first complete JSON object returned by the model."""
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("The model did not return a JSON object.")

    return json.loads(text[start : end + 1])


def _empty_constraints() -> dict[str, Any]:
    return {
        "destination": "",
        "origin": "",
        "duration": "",
        "budget": "",
        "travel_style": "",
        "special_preferences": [],
        "cities": [],
    }


# =========================
# Supervisor Agent + Input Guardrail
# =========================
def supervisor_agent(state: TravelState):
    query = state["user_query"]
    llm_calls = state.get("llm_calls", 0)

    guardrail_prompt = f"""
Determine whether the following request belongs to travel planning or travel
information. Valid requests can include destinations, flights, hotels, weather,
budgets, visas, transportation, sightseeing, food, packing, or itineraries.

Block clearly unrelated requests and requests asking for harmful or illegal
instructions. Do not block a valid travel request merely because some details
are missing.

Return strict JSON only:
{{
  "allowed": true,
  "reason": ""
}}

User request:
{query}
"""

    # Fail open on parser/model errors so a temporary JSON-format issue does not
    # break the original travel-planning behavior.
    try:
        guardrail_raw = _llm_text(
            "You are the input guardrail for a travel-planning application. "
            "Return strict JSON only.",
            guardrail_prompt,
        )
        guardrail_result = _json_from_llm(guardrail_raw)
        allowed = bool(guardrail_result.get("allowed", True))
        guardrail_reason = str(guardrail_result.get("reason", "")).strip()
        llm_calls += 1
    except Exception as exc:
        print(f"Guardrail fallback used: {exc}")
        allowed = True
        guardrail_reason = "Guardrail validation fallback allowed the request."

    if not allowed:
        reason = guardrail_reason or (
            "TripMate AI can only help with travel-planning requests. "
            "Please ask about a destination, flight, hotel, weather, budget, "
            "or itinerary."
        )
        return {
            "guardrail_allowed": False,
            "guardrail_reason": reason,
            "selected_agents": [],
            "trip_constraints": _empty_constraints(),
            "supervisor_reasoning": reason,
            "final_response": reason,
            "messages": [AIMessage(content=f"Guardrail blocked request: {reason}")],
            "llm_calls": llm_calls,
        }

    supervisor_prompt = f"""
You are the supervisor of a multi-agent travel-planning system.
Choose only the specialist agents needed for the request.

Available agents:
- flight_agent: flights, airports, airlines, routes, airfare, or booking advice
- hotel_agent: hotels, accommodation, neighborhoods, or places to stay
- weather_agent: weather, climate, season, forecast, or packing advice
- budget_agent: cost, affordability, price limits, or budget feasibility
- itinerary_agent: creates the integrated travel plan and must always be included

"cities" = the 1-3 real cities where the traveller will actually stay, in visiting order.
If the destination is a whole country or region, choose the classic cities for that trip
length (for example India 7 days -> Delhi, Agra, Jaipur). Use real city names only.

Return strict JSON only using this schema:
{{
  "selected_agents": ["flight_agent", "hotel_agent", "weather_agent", "budget_agent", "itinerary_agent"],
  "trip_constraints": {{
    "destination": "",
    "origin": "",
    "duration": "",
    "budget": "",
    "travel_style": "",
    "special_preferences": [],
    "cities": []
  }},
  "reasoning": ""
}}

User request:
{query}
"""

    try:
        supervisor_raw = _llm_text(
            "You route work to travel specialist agents. Return strict JSON only.",
            supervisor_prompt,
        )
        parsed = _json_from_llm(supervisor_raw)
        requested_agents = parsed.get("selected_agents", [])
        selected_agents = [
            name for name in AGENT_ORDER
            if name in requested_agents and name in KNOWN_AGENTS
        ]

        # The itinerary agent integrates whichever specialist results were selected.
        if "itinerary_agent" not in selected_agents:
            selected_agents.append("itinerary_agent")

        # The total cost + budget verdict is always needed.
        if "budget_agent" not in selected_agents:
            selected_agents.append("budget_agent")
        selected_agents = [n for n in AGENT_ORDER if n in selected_agents]

        constraints = _empty_constraints()
        parsed_constraints = parsed.get("trip_constraints", {})
        if isinstance(parsed_constraints, dict):
            constraints.update(parsed_constraints)

        raw_cities = constraints.get("cities", [])
        if isinstance(raw_cities, str):
            raw_cities = [raw_cities]
        constraints["cities"] = [
            str(c).strip() for c in raw_cities if str(c).strip()
        ][:3] if isinstance(raw_cities, list) else []

        reasoning = str(parsed.get("reasoning", "")).strip()
        llm_calls += 1
    except Exception as exc:
        print(f"Supervisor fallback used: {exc}")
        # Original workflow behavior is preserved as the fallback.
        selected_agents = AGENT_ORDER.copy()
        constraints = _empty_constraints()
        reasoning = (
            "Supervisor parsing failed, so the original full travel workflow "
            "was selected as a safe fallback."
        )

    return {
        "guardrail_allowed": True,
        "guardrail_reason": guardrail_reason,
        "selected_agents": selected_agents,
        "trip_constraints": constraints,
        "supervisor_reasoning": reasoning,
        "messages": [AIMessage(content="Supervisor created the agent plan.")],
        "llm_calls": llm_calls,
    }


# =========================
# Guardrail blocked response
# =========================
def guardrail_blocked_agent(state: TravelState):
    reason = state.get("final_response") or state.get("guardrail_reason") or (
        "This request was blocked by the travel input guardrail."
    )
    return {
        "final_response": reason,
        "messages": [AIMessage(content=reason)],
    }


# =========================
# Flight Agent - original behavior kept
# =========================
FLIGHT_AGENT_PROMPT = """
You are a travel flight analyst. Today's date is {today}.

User Query:
{query}

Route (from the supervisor): {origin} -> {destination}   (airports: {dep_iata} -> {arr_iata})

SOURCE A - AviationStack live departure board (TODAY only, real schedule data):
{aviation_data}

SOURCE B - live web search (fares, airlines, durations):
{search_data}

Rules:
- Use ONLY facts that appear in Source A or Source B. Do not invent fares, airlines,
  flight numbers, times or sources.
- Flight numbers and times may come ONLY from Source A. Say they are from today's board
  and that the schedule on the travel date can differ.
- Source A lists a DIRECT option and VIA-hub options. If there is no direct flight, present the
  route as Origin -> Hub -> Destination with both legs and their flight numbers from Source A.
  Never claim a direct flight exists when Source A says there is none.
- A connection must be booked as one ticket; mention the hub city and the minimum connection time.
- Fares may come ONLY from Source B. Name the site/URL for every fare. If there is no
  price, write "price not found in search results".
- Do NOT claim to use Google Flights, Skyscanner or any tool that is not in the sources.
- {date_rule}
- If both sources are empty, say clearly: "No live flight data found", then give only a short,
  clearly labelled GENERAL ESTIMATE and tell the user to verify on an airline/OTA website.

Return concise guidance:
1. Departure and arrival airports
2. Flights/airlines found (with source A or B)
3. Typical duration (if found)
4. Fares found (with source) or "not found"
5. Booking advice
"""


def _is_failed_tool_output(raw: Any) -> bool:
    """MCP tools return {"ok": false, ...} instead of raising."""
    text = str(raw)
    return (
        '"ok": false' in text
        or "function_access_restricted" in text
        or "Access Restricted" in text
    )


def _guess_iata(place: str):
    """'Tokyo, Japan' -> 'NRT' using the offline airport helper; None if unknown."""
    if not place or resolve_location_to_iata is None:
        return None
    for candidate in (place.split(",")[0], place):
        try:
            code = resolve_location_to_iata(candidate)
        except Exception:
            code = None
        if code:
            return code
    return None


def _format_board(result: dict, dep: str, arr: str) -> str:
    if not result.get("ok"):
        return f"AviationStack data unavailable: {result.get('error', 'unknown error')}"

    matches = result.get("matches", [])
    if not matches:
        return (
            f"No flight from {dep} to {arr} on today's departure board "
            f"({result.get('scanned', 0)} departures checked). "
            "This only means no direct flight was listed today."
        )

    lines = [f"Direct flights {dep} -> {arr} on today's board:"]
    for f in matches:
        lines.append(
            f"- {f.get('airline')} {f.get('flight_number')}: departs "
            f"{f.get('departure_scheduled_time')}, arrives "
            f"{f.get('arrival_scheduled_time')} (terminal {f.get('departure_terminal') or 'n/a'})"
        )
    return "\n".join(lines)


# =========================
# Route planner: direct flight, or connection via Indian hub (Delhi / Mumbai)
# =========================
HUB_AIRPORTS = ["DEL", "BOM"]  # main Indian international gateways

US_CITY_AIRPORTS = {
    "new york": ["JFK", "EWR", "LGA"],
    "washington": ["IAD", "DCA", "BWI"],
}

try:
    import airportsdata as _airportsdata
    _AIRPORTS = _airportsdata.load("IATA")
except Exception as _exc:  # pragma: no cover
    print(f"airportsdata unavailable: {_exc}", flush=True)
    _AIRPORTS = {}


def _is_india_airport(code: str) -> bool:
    return bool(code) and _AIRPORTS.get(code, {}).get("country") == "IN"


def _airports_for_place(place: str) -> list:
    text = (place or "").lower()
    for key, codes in US_CITY_AIRPORTS.items():
        if key in text:
            return codes
    code = _guess_iata(place)
    return [code] if code else []


def _board_lines(result: dict, dep: str, arr: str) -> str:
    if not result.get("ok"):
        return f"AviationStack data unavailable: {result.get('error', 'unknown error')}"

    matches = result.get("matches", [])
    if not matches:
        return f"no {dep} -> {arr} flight on today's board ({result.get('scanned', 0)} departures checked)"

    lines = []
    for f in matches:
        lines.append(
            f"{f.get('airline')} {f.get('flight_number')}: {f.get('departure_airport_code', dep)} "
            f"{f.get('departure_scheduled_time')} -> {f.get('arrival_airport_code')} "
            f"{f.get('arrival_scheduled_time')}"
        )
    return f"{dep} -> {arr}: " + "; ".join(lines)


def _plan_route_options(origin_label: str, dep: str, dest_codes: list) -> str:
    """Direct options plus, for flights from India, connections via Delhi/Mumbai."""
    if not dep or not dest_codes:
        return "Airport codes could not be determined, so no live flight board was checked."

    dest_text = "/".join(dest_codes)
    lines = []

    direct = asyncio.run(aviation_departures_to(dep, dest_codes))
    lines.append(f"DIRECT option: {_board_lines(direct, dep, dest_text)}")

    if _is_india_airport(dep):
        for hub in HUB_AIRPORTS:
            if hub == dep:
                continue
            leg1 = asyncio.run(aviation_departures_to(dep, [hub]))
            leg2 = asyncio.run(aviation_departures_to(hub, dest_codes))
            lines.append(f"VIA {hub} option:")
            lines.append(f"  Leg 1 ({origin_label} to {hub}): {_board_lines(leg1, dep, hub)}")
            lines.append(f"  Leg 2 ({hub} to {dest_text}): {_board_lines(leg2, hub, dest_text)}")

    lines.append(
        "Note: these lists come from today's departure boards only, so they show "
        "which flights exist, not the flights on the travel date. A connection must be "
        "booked as one ticket, with at least 3 hours between the two flights."
    )
    return "\n".join(lines)


def flight_agent(state: TravelState):
    print("\nINSIDE FLIGHT AGENT\n")
    query = state["user_query"]
    constraints = state.get("trip_constraints", {}) or {}
    origin = constraints.get("origin") or "the origin city in the user query"
    destination = constraints.get("destination") or "the destination in the user query"
    today = datetime.date.today().strftime("%d %B %Y")

    cities = _trip_cities(state)
    arrival_city = cities[0] if cities else destination

    cities = _trip_cities(state)
    arrival_city = cities[0] if cities else destination
    dest_cities = cities or [destination]

    dep_codes = _airports_for_place(constraints.get("origin", ""))
    dep_iata = dep_codes[0] if dep_codes else None
    dest_codes = []
    for city in dest_cities:
        dest_codes += _airports_for_place(city)
    dest_codes = list(dict.fromkeys(dest_codes))
    arr_iata = dest_codes[0] if dest_codes else None

    # ---- Source A: AviationStack MCP route planner (direct + via Delhi/Mumbai) ----
    try:
        aviation_data = _plan_route_options(constraints.get("origin", ""), dep_iata, dest_codes)
    except Exception as exc:
        print(f"AVIATIONSTACK MCP ERROR: {type(exc).__name__}: {exc}", flush=True)
        aviation_data = f"AviationStack data unavailable: {type(exc).__name__}: {exc}"
    print("\nAVIATIONSTACK RESULT:", aviation_data[:600], flush=True)

    # ---- Source B: Tavily MCP (via mcp_client) ----
    via = " via Delhi or Mumbai" if _is_india_airport(dep_iata or "") else ""
    search_query = (
        f"flights from {origin} to {arrival_city}{via} airlines flight duration "
        f"round trip ticket price {constraints.get('duration', '')}"
    )
    try:
        raw = asyncio.run(tavily_mcp_search(search_query, max_results=5))
        search_data = _compact_hotels(raw, 1500)

        if _is_failed_tool_output(raw) or not search_data.strip():
            search_data = "No live flight search results found."
        print("\nFLIGHT SEARCH RESULTS:", search_data[:500], flush=True)
    except Exception as exc:
        print(f"FLIGHT AGENT MCP ERROR: {type(exc).__name__}: {exc}", flush=True)
        search_data = "No live flight search results (search service unavailable)."

    try:
        prompt = FLIGHT_AGENT_PROMPT.format(
            today=today,
            date_rule=_date_rule(),
            query=query,
            origin=origin,
            destination=destination,
            dep_iata=dep_iata or "?",
            arr_iata=arr_iata or "?",
            aviation_data=_clip(aviation_data, 900),
            search_data=_clip(search_data, 1500),
        )

        response = _invoke(
            [
                SystemMessage(content="You are a careful travel flight analyst who never invents data."),
                HumanMessage(content=prompt),
            ]
        )
        flight_data = response.content
    except Exception as exc:
        flight_data = f"Flight information unavailable: {exc}"

    return {
        "flight_results": flight_data,
        "messages": [AIMessage(content="Flight recommendations generated")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# =========================
# Hotel Agent - original behavior kept
# =========================
def hotel_agent(state: TravelState):
    constraints = state.get("trip_constraints", {}) or {}
    cities = _trip_cities(state) or [state["user_query"][:100]]
    extra = str(constraints.get("travel_style", "")).strip()  # not the total trip budget

    try:
        collected = asyncio.run(tavily_hotel_research(cities, extra))

        per_city = MAX_HOTEL_CHARS // max(len(collected), 1)
        sections = []
        for city, raw in collected:
            sections.append(f"### Hotels in {city}\n{_compact_hotels(raw, per_city)}")
        hotel_results = "\n\n".join(sections)
        print("\nHOTEL RESULTS:", hotel_results[:600], flush=True)

    except Exception as exc:
        print(
            f"HOTEL AGENT MCP ERROR: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

        hotel_results = (
            "Live hotel search is temporarily unavailable. "
            "Do not name any specific hotel; give only general area guidance "
            "and label it as non-live advice."
        )

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(
                content="Hotel information processed."
            )
        ],
        "llm_calls": (
            state.get("llm_calls", 0) + 1
        ),
    }


# =========================
# Weather Agent - original behavior kept
# =========================
def weather_agent(state: TravelState):
    cities = _trip_cities(state)

    if not cities:
        cities = [extract_destination(state["user_query"])]

    sections = []

    for city in cities[:3]:
        try:
            # weather comes from tools/weather_tool.py (OpenWeather), not MCP
            weather_data = get_current_weather(city)
            forecast_data = get_weather_forecast(city)
            sections.append(f"## {city}\n{_format_weather(weather_data, forecast_data)}")
        except Exception as exc:
            print(
                f"WEATHER API ERROR ({city}): {type(exc).__name__}: {exc}",
                flush=True,
            )

    if sections:
        weather_results = (
            "Live OpenWeather data: current weather + forecast for the next ~5 days "
            "(this is NOT the weather on the travel dates).\n\n" + "\n\n".join(sections)
        )
    else:
        weather_results = (
            f"Live weather information for {', '.join(cities)} is unavailable. "
            "Give general seasonal guidance, clearly labelled as general knowledge, "
            "and advise the traveler to verify the forecast before departure."
        )

    return {
        "weather_results": weather_results,
        "messages": [
            AIMessage(
                content="Weather information processed."
            )
        ],
    }


# =========================
# Budget Agent - new specialist
# =========================
def budget_agent(state: TravelState):
    constraints = state.get("trip_constraints", {}) or {}
    limit = _parse_budget_inr(constraints.get("budget", ""), state["user_query"])

    prompt = f"""
Estimate the REALISTIC MINIMUM total cost of this trip in Indian rupees (INR).
Today's date is {datetime.date.today().strftime("%d %B %Y")}.

User Query:
{state['user_query']}

Trip Constraints:
{constraints}

Flight Results (live web search):
{_clip(state.get('flight_results', ''), MAX_FLIGHT_CHARS)}

Hotel Results (live web search):
{_clip(state.get('hotel_results', ''), MAX_HOTEL_CHARS)}

Rules:
- Do NOT lower any number to make the trip fit the user's budget. Give honest, realistic minimum costs.
- Each amount is the cost for ALL travellers together for the WHOLE trip, in INR.
- Nights of stay = number of trip days - 1. Count travellers from the query (default 1 if unclear).
- "basis" = "search" ONLY when the number is stated in the Flight or Hotel results above
  (a fare "from $X" is usually per person: multiply by travellers). Otherwise "estimate".
- If the search result does not say whether a fare is one-way or round-trip, or per person
  or for the whole group, use the more expensive reading and say so in "assumptions".
- If you convert a currency, state the rate you used in "assumptions".
- Use exactly these categories: Flights, Accommodation, Local transport, Food,
  Entry fees & activities, Visa / insurance / SIM / misc.

Return strict JSON only:
{{
  "items": [
    {{"category": "Flights", "amount_inr": 0, "basis": "search or estimate", "note": "short reason"}}
  ],
  "savings_tips": ["short practical tip"],
  "assumptions": ["short assumption"]
}}
"""

    try:
        response = _invoke(
            [
                SystemMessage(content="You are an honest travel budget analyst. Return strict JSON only."),
                HumanMessage(content=prompt),
            ],
            max_tokens=1500,
        )
        plan = _json_from_llm(str(response.content))
        summary, total = _build_budget_summary(plan, limit)
    except Exception as exc:
        print(f"BUDGET AGENT ERROR: {type(exc).__name__}: {exc}", flush=True)
        summary, total = (
            "Budget total could not be calculated automatically. "
            "Please verify prices on booking websites.",
            None,
        )

    return {
        "budget_results": summary,
        "budget_summary": summary,
        "budget_total_inr": total or 0.0,
        "budget_limit_inr": limit or 0.0,
        "messages": [AIMessage(content="Budget assessment generated.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# =========================
# Itinerary Agent - original behavior extended with selected results
# =========================
def itinerary_agent(state: TravelState):
    prompt = f"""
Create a complete travel itinerary.

User Query:
{state['user_query']}

Trip Constraints:
{state.get('trip_constraints', {})}

Flight Results:
{_clip(state.get('flight_results', ''), MAX_FLIGHT_CHARS)}

Hotel Results:
{_clip(state.get('hotel_results', ''), MAX_HOTEL_CHARS)}

Weather Results:
{_clip(state.get('weather_results', ''), MAX_WEATHER_CHARS)}

Budget Results:
{_clip(state.get('budget_results', ''), MAX_BUDGET_CHARS)}

Make the itinerary practical, budget-aware, and easy to follow.
Create a clear draft that is ready for human review.

Strict rules:
- {_date_rule()}
- Do NOT invent flight numbers or flight times. Refer to "the flight" generally.
- Name a specific hotel ONLY if it appears in the Hotel Results above; otherwise say
  "hotel to be chosen (area: ...)". Never suggest hotel names from your own memory,
  not even as examples.
- Nights of stay = number of trip days - 1. Do not add extra nights.
- Mark entry fees and food costs as approximate and do not add up an overall trip total
  (the system adds the official budget summary).
- If the Budget Results say the trip is NOT possible within the budget, keep the plan lean
  and never claim that it fits.
"""

    response = _invoke(
        [
            SystemMessage(content="You are an expert travel planner."),
            HumanMessage(content=prompt),
        ]
    )

    approval_request = (
        "Please review the generated draft itinerary. Approve it to create the "
        "final polished plan, or provide feedback for revision."
    )

    return {
        "itinerary": response.content,
        "approval_request": approval_request,
        "messages": [AIMessage(content="Draft itinerary created for human review.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# =========================
# Human-in-the-Loop approval
# =========================
def human_approval_agent(state: TravelState):
    # Do not wrap interrupt() in try/except. LangGraph uses it to pause execution.
    review = interrupt(
        {
            "question": "Do you approve this itinerary?",
            "draft_itinerary": state.get("itinerary", ""),
            "approval_request": state.get("approval_request", ""),
            "selected_agents": state.get("selected_agents", []),
            "supervisor_reasoning": state.get("supervisor_reasoning", ""),
            "expected_response": {
                "approved": True,
                "feedback": "Optional revision feedback",
            },
        }
    )

    approved = bool(review.get("approved", False))
    human_feedback = str(review.get("feedback", "")).strip()

    return {
        "approved": approved,
        "human_feedback": human_feedback,
        "messages": [AIMessage(content="Human approval step completed.")],
    }


# =========================
# Final Response Agent - original format kept, HITL feedback added
# =========================
def final_agent(state: TravelState):
    if state.get("approved", False):
        review_instruction = (
            "The user approved the draft. Preserve its decisions while polishing it."
        )
    else:
        review_instruction = f"""
The user requested a revision. Apply this feedback carefully:
{state.get('human_feedback', '') or 'Improve the draft before finalizing it.'}
"""

    final_prompt = f"""
Generate the final travel response for the user.

Human Review:
{review_instruction}

User Request:
{state['user_query']}

Supervisor Constraints:
{state.get('trip_constraints', {})}

Flights:
{_clip(state.get('flight_results', ''), MAX_FLIGHT_CHARS)}

Hotels:
{_clip(state.get('hotel_results', ''), MAX_HOTEL_CHARS)}

Weather:
{_clip(state.get('weather_results', ''), MAX_WEATHER_CHARS)}

Budget Analysis:
{_clip(state.get('budget_results', ''), MAX_BUDGET_CHARS)}

Draft Itinerary:
{_clip(state.get('itinerary', ''), MAX_ITINERARY_CHARS)}

Format the final answer beautifully using these sections:
1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Day-by-Day Itinerary
6. Final Recommendations
7. Estimated Budget & Verdict  (write ONLY the exact text [[BUDGET_SUMMARY]] under this heading; the system fills it in)

Important:
- Be clear and practical.
- {_date_rule()}
- Use ONLY the Flights, Hotels and Weather sections above for facts. If a price, link or
  hotel detail is not there, write "not found in live search" instead of inventing it.
- Include the source links that appear in the Flights and Hotels sections.
- Clearly label any fare or price that is only an estimate, and tell the user to verify it before booking.
- Do NOT claim data from Google Flights, Skyscanner or any source not present above.
- Mention that live flight APIs may not provide ticket prices when pricing is unavailable.
- Include weather-based travel advice.
- Keep the response useful for real travel planning.
- Incorporate the human feedback when revision was requested.
- Do not write any overall trip total or budget verdict yourself; only the [[BUDGET_SUMMARY]] placeholder.
- Nights of stay = number of trip days - 1.
- Do not invent flight numbers/times or hotel names that are not in the sections above.
  Never suggest hotel names from your own memory, not even as examples.
- Hotels: for each city list up to 2 hotels that appear in the Hotels section, with the
  price if the section states it and the source link. If none, write "no specific hotel found in live search".
- Weather: show the live data from the Weather section. If the travel dates are beyond that
  forecast, add a short note labelled "typical seasonal climate (general knowledge)".
"""

    response = _invoke(
        [
            SystemMessage(
                content="You are a professional AI travel booking assistant."
            ),
            HumanMessage(content=final_prompt),
        ],
        max_tokens=4000,
    )

    final_text = str(response.content)
    budget_block = state.get("budget_summary") or "Budget estimate unavailable."

    if "[[BUDGET_SUMMARY]]" in final_text:
        final_text = final_text.replace("[[BUDGET_SUMMARY]]", budget_block)
    else:
        final_text += "\n\n## Estimated Budget & Verdict\n" + budget_block

    return {
        "final_response": final_text,
        "messages": [AIMessage(content=final_text)],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# =========================
# Dynamic Supervisor Routing
# =========================
ROUTE_MAP = {
    "guardrail_blocked": "guardrail_blocked",
    "flight_agent": "flight_agent",
    "hotel_agent": "hotel_agent",
    "weather_agent": "weather_agent",
    "budget_agent": "budget_agent",
    "itinerary_agent": "itinerary_agent",
}


def _selected_agents(state: TravelState) -> list[str]:
    selected = state.get("selected_agents", [])
    return [agent for agent in AGENT_ORDER if agent in selected]


def route_from_supervisor(state: TravelState) -> str:
    if not state.get("guardrail_allowed", True):
        return "guardrail_blocked"

    selected = _selected_agents(state)
    return selected[0] if selected else "itinerary_agent"


def route_after_agent(current_agent: str):
    def route(state: TravelState) -> str:
        selected = _selected_agents(state)
        current_index = AGENT_ORDER.index(current_agent)

        for next_agent in AGENT_ORDER[current_index + 1 :]:
            if next_agent in selected:
                return next_agent

        return "itinerary_agent"

    return route


# =========================
# Build Graph
# =========================
graph = StateGraph(TravelState)

graph.add_node("supervisor", supervisor_agent)
graph.add_node("guardrail_blocked", guardrail_blocked_agent)
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent", weather_agent)
graph.add_node("budget_agent", budget_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("human_approval", human_approval_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", route_from_supervisor, ROUTE_MAP)

graph.add_conditional_edges(
    "flight_agent", route_after_agent("flight_agent"), ROUTE_MAP
)
graph.add_conditional_edges(
    "hotel_agent", route_after_agent("hotel_agent"), ROUTE_MAP
)
graph.add_conditional_edges(
    "weather_agent", route_after_agent("weather_agent"), ROUTE_MAP
)
graph.add_conditional_edges(
    "budget_agent", route_after_agent("budget_agent"), ROUTE_MAP
)

graph.add_edge("itinerary_agent", "human_approval")
graph.add_edge("human_approval", "final_agent")
graph.add_edge("final_agent", END)
graph.add_edge("guardrail_blocked", END)

# =========================
# PostgreSQL Checkpointer - original persistence kept
# =========================
DATABASE_URL = get_database_url()
_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row,
)
checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)


# =========================
# FastAPI-facing helpers
# =========================
def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return None

    first_interrupt = interrupts[0]
    payload = getattr(first_interrupt, "value", first_interrupt)
    return payload if isinstance(payload, dict) else {"value": payload}


def _serialize_result(
    result: dict[str, Any],
    thread_id: str,
) -> dict[str, Any]:
    messages = result.get("messages", [])
    last_message = messages[-1].content if messages else ""
    answer = result.get("final_response") or last_message
    interrupt_payload = _interrupt_payload(result)

    if interrupt_payload:
        answer = interrupt_payload.get("draft_itinerary") or result.get(
            "itinerary", ""
        )
        if result.get("budget_summary"):
            answer = f"{answer}\n\n---\n\n## Budget check\n{result['budget_summary']}"

    return {
        "thread_id": thread_id,
        "answer": answer,
        "requires_approval": interrupt_payload is not None,
        "approval_request": (
            interrupt_payload.get("approval_request", "")
            if interrupt_payload
            else result.get("approval_request", "")
        ),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "budget_results": result.get("budget_results", ""),
        "itinerary": (
            interrupt_payload.get("draft_itinerary", "")
            if interrupt_payload
            else result.get("itinerary", "")
        ),
        "selected_agents": result.get("selected_agents", []),
        "trip_constraints": result.get("trip_constraints", {}),
        "supervisor_reasoning": result.get("supervisor_reasoning", ""),
        "guardrail_allowed": result.get("guardrail_allowed", True),
        "guardrail_reason": result.get("guardrail_reason", ""),
        "approved": result.get("approved"),
        "human_feedback": result.get("human_feedback", ""),
        "llm_calls": result.get("llm_calls", 0),
    }


def run_travel_agent(user_input: str, thread_id: str | None = None):
    """Start a new travel-planning run and pause at human approval."""
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {"configurable": {"thread_id": thread_id}}

    result = travel_graph.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "user_query": user_input,
            "guardrail_allowed": True,
            "guardrail_reason": "",
            "selected_agents": [],
            "trip_constraints": _empty_constraints(),
            "supervisor_reasoning": "",
            "flight_results": "",
            "hotel_results": "",
            "weather_results": "",
            "budget_results": "",
            "budget_summary": "",
            "budget_total_inr": 0.0,
            "budget_limit_inr": 0.0,
            "itinerary": "",
            "approval_request": "",
            "approved": False,
            "human_feedback": "",
            "final_response": "",
            "llm_calls": 0,
        },
        config=config,
    )

    return _serialize_result(result, thread_id)


def resume_travel_agent(
    thread_id: str,
    approved: bool,
    feedback: str = "",
):
    """Resume the paused LangGraph thread after human review."""
    if not thread_id:
        raise ValueError("thread_id is required to resume a travel plan.")

    config = {"configurable": {"thread_id": thread_id}}
    result = travel_graph.invoke(
        Command(
            resume={
                "approved": approved,
                "feedback": feedback.strip(),
            }
        ),
        config=config,
    )

    return _serialize_result(result, thread_id)
