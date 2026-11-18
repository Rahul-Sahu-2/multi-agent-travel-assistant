from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights 
from backend import run_travel_agent

# res = search_flights("Plan a 7 days japan trip from india")
# print(res)

user_input  = input("enter travel request: ")
response = run_travel_agent(
    user_input=user_input,
    thread_id="test_user"
)

print(response['answer'])

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