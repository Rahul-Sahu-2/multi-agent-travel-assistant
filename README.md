# ✈️ Travel Agent – Your Personal AI Travel Planner

An AI-powered multi-agent travel planning assistant that transforms natural-language travel requests into structured travel recommendations, including flight information, hotel suggestions, estimated budgets, and day-by-day itineraries.

Built using **LangGraph, LangChain, Groq, FastAPI, PostgreSQL, AviationStack, and Tavily**, this project demonstrates how multiple AI agents can collaborate to simplify travel planning.

## 🌍 About the Project

Planning a trip involves researching flights, finding hotels, comparing travel costs, and organizing daily activities.

**Travel Agent** brings these tasks together through an AI-powered multi-agent workflow.

Users can describe their travel requirements in natural language, including destination, travel dates, budget, and preferences. The system processes the request through specialized agents and generates a structured travel plan.

## ✨ Features

- ✈️ **Flight Research:** Retrieves flight information using the AviationStack API.
- 🏨 **Hotel Research:** Searches for hotel recommendations using Tavily.
- 🤖 **Multi-Agent Architecture:** Coordinates specialized AI agents using LangGraph.
- 🧠 **AI Itinerary Generation:** Creates personalized day-by-day travel plans.
- 💰 **Budget Estimation:** Organizes estimated travel expenses.
- 🌐 **Web Interface:** Interactive frontend built with HTML, CSS, and JavaScript.
- ⚡ **FastAPI Backend:** Handles user requests and connects the frontend with the AI workflow.
- 💾 **Conversation Persistence:** Uses PostgreSQL and LangGraph checkpointing to maintain conversation state.
- 📄 **Structured Travel Recommendations:** Presents travel information in an organized format.

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| Python 3.10+ | Core programming language |
| LangGraph | Multi-agent workflow orchestration |
| LangChain | LLM integration |
| Groq | Large Language Model inference |
| FastAPI | Backend API development |
| PostgreSQL | Conversation state persistence |
| AviationStack | Flight information |
| Tavily | Web search and hotel research |
| HTML5 | Frontend structure |
| CSS3 | Frontend styling |
| JavaScript | Frontend interactions |
| Jinja2 | HTML templating |

## 📁 Project Structure

```text
Travel-Agent/
│
├── app.py
├── backend.py
│
├── tools/
│   ├── flight_tool.py
│   └── tavily_tool.py
│
├── templates/
│   └── index.html
│
├── static/
│   ├── style.css
│   └── script.js
│
├── requirements.txt
├── .env
└── README.md
```

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Opens the travel planner interface |
| GET | `/health` | Checks backend health |
| POST | `/api/travel` | Processes a travel planning request |

### Example API Request

```json
{
    "message": "Plan an 8-day trip to Japan with a budget of ₹200000, including Tokyo, Kyoto and Osaka."
}
```

## 💡 Example User Request

```text
Plan a 7-day trip from Delhi to Dubai.

Travel dates: 10 December to 17 December 2026.

Budget: ₹150000 per person.

Preferences:
- Comfortable hotels
- Cultural attractions
- Local food experiences
- Practical transportation
- Day-by-day itinerary
```

The multi-agent workflow processes the request and generates a structured travel recommendation.

## 🔮 Future Enhancements

- Real-time flight price comparison.
- Verified hotel availability and pricing.
- Improved travel budget calculations.
- Visa information based on passport nationality.
- Weather information and forecasts.
- Interactive maps and route planning.
- Additional specialized AI agents.
- Improved date and timezone handling.
- PDF itinerary export.
- Cloud deployment and scalability improvements.

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository.
2. Create a new branch.
3. Make your changes.
4. Commit your changes.
5. Submit a pull request.

---

⭐ If you find this project useful, consider giving this repository a star!
