import os
import json

import certifi
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq


# ==========================================
# Environment configuration
# ==========================================

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


AVIATION_ENV = os.environ.copy()
AVIATION_ENV["AVIATION_STACK_API_KEY"] = (
    AVIATION_STACK_API_KEY or ""
)


# ==========================================
# LLM
# ==========================================

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=GROQ_API_KEY
)


# ==========================================
# MCP client configuration
# ==========================================

client = MultiServerMCPClient(
    {
        "tavily": {
            "transport": "streamable_http",
            "url": (
                "https://mcp.tavily.com/mcp/"
                f"?tavilyApiKey={TAVILY_API_KEY}"
            )
        },

        "aviationstack": {
            "transport": "stdio",
            "command": "uvx",
            "args": [
                "aviationstack-mcp"
            ],
            "env": AVIATION_ENV
        }
    }
)


# ==========================================
# Diagnostic function
# ==========================================

async def get_all_tools():

    all_tools = []

    for server_name in (
        "tavily",
        "aviationstack"
    ):
        try:
            tools = await client.get_tools(
                server_name=server_name
            )

            all_tools.extend(tools)

            print(
                f"\nAvailable tools from "
                f"{server_name} MCP:\n"
            )

            for tool in tools:
                print(tool.name)

        except Exception as error:
            print(
                f"\nCould not connect to "
                f"{server_name} MCP:\n{error}\n"
            )

    return all_tools


# ==========================================
# Tavily MCP tool
# ==========================================

search_tool = None


async def initialize_mcp():

    global search_tool

    if search_tool is not None:
        return

    tools = await client.get_tools(
        server_name="tavily"
    )

    tools_by_name = {
        tool.name: tool
        for tool in tools
    }

    search_tool = tools_by_name.get(
        "tavily_search"
    )

    if search_tool is None:

        available_tools = ", ".join(
            tools_by_name.keys()
        )

        raise RuntimeError(
            "Tavily MCP connected, but the "
            "'tavily_search' tool was not found. "
            f"Available tools: "
            f"{available_tools or 'none'}"
        )


async def tavily_mcp_search(query: str, **options):
    """
    Run a Tavily MCP search. Optional tool options (e.g. max_results=5,
    search_depth="advanced") are tried first; if the server rejects them,
    the plain query is used so the search never breaks.
    """

    await initialize_mcp()

    payload = {"query": query}
    payload.update(options)

    try:
        return await search_tool.ainvoke(payload)
    except Exception as exc:
        if not options:
            raise

        print(
            f"Tavily options rejected ({type(exc).__name__}); "
            "retrying with plain query.",
            flush=True,
        )

        return await search_tool.ainvoke({"query": query})


async def tavily_hotel_research(places, extra: str = ""):
    """
    Hotel information from Tavily MCP, one search per city/place
    (a country-wide search returns only generic articles).

    places: a list of city names (or a single string).
    Returns a list of (city, raw_result). Raises only if every search fails.
    """

    if isinstance(places, str):
        places = [places]

    collected = []
    last_error = None

    for place in places:
        query = (
            f"best 3 star hotels in {place} price per night "
            f"booking reviews rating {extra}"
        ).strip()

        try:
            result = await tavily_mcp_search(query, max_results=4)
            collected.append((place, result))
        except Exception as exc:
            last_error = exc
            print(
                f"Tavily hotel search failed ({place}): "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

    if not collected:
        raise RuntimeError(f"All Tavily hotel searches failed: {last_error}")

    return collected


# ==========================================
# AviationStack MCP tools
# ==========================================

aviation_tools = {}


async def initialize_aviation_tools():

    global aviation_tools

    if aviation_tools:
        return

    tools = await client.get_tools(
        server_name="aviationstack"
    )

    aviation_tools = {
        tool.name: tool
        for tool in tools
    }

    if not aviation_tools:
        raise RuntimeError(
            "AviationStack MCP connected but "
            "returned no tools."
        )


async def aviation_mcp_call(
    tool_name: str,
    tool_args: dict = None
):

    await initialize_aviation_tools()

    tool = aviation_tools.get(tool_name)

    if tool is None:

        available_tools = ", ".join(
            sorted(aviation_tools.keys())
        )

        raise ValueError(
            f"AviationStack tool '{tool_name}' "
            "was not found. "
            f"Available tools: "
            f"{available_tools or 'none'}"
        )

    result = await tool.ainvoke(
        tool_args or {}
    )

    return result


def mcp_result_text(result) -> str:
    """Normalize an MCP tool result (str or list of content blocks) to plain text."""

    if isinstance(result, str):
        return result

    if isinstance(result, list):
        parts = []

        for item in result:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))

        return "\n".join(parts)

    return str(result)


async def aviation_route_schedule(
    dep_iata: str,
    arr_iata: str,
    limit: int = 100
):
    """
    Today's live departure board of dep_iata (AviationStack MCP tool
    'flight_arrival_departure_schedule'), filtered to flights that
    arrive at arr_iata.

    Always returns a dict:
      {"ok": True,  "scanned": N, "matches": [...]}
      {"ok": False, "error": "..."}   (for example plan restrictions)
    """

    raw = await aviation_mcp_call(
        "flight_arrival_departure_schedule",
        {
            "airport_iata_code": dep_iata,
            "schedule_type": "departure",
            "number_of_flights": limit
        }
    )

    text = mcp_result_text(raw)

    try:
        data = json.loads(text)
    except ValueError:
        return {"ok": False, "error": text[:300]}

    if not data.get("ok"):
        return {
            "ok": False,
            "error": str(data.get("error", "unknown error"))[:300]
        }

    board = data.get("data", []) or []

    matches = [
        flight
        for flight in board
        if str(flight.get("arrival_airport_code", "")).upper()
        == arr_iata.upper()
    ]

    return {
        "ok": True,
        "scanned": len(board),
        "matches": matches[:8]
    }


# ==========================================
# Destination extractor
# ==========================================

def extract_destination(query: str):

    prompt = f"""
    Extract only the destination city or country.

    Query:
    {query}

    Return only destination name.
    """

    response = llm.invoke(prompt)

    return response.content.strip()