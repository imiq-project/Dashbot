"""
Tool definitions for LLM function calling. Defines available tools (search_knowledge, get_mobility, get_building, etc.) with their parameters and schemas.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search project documentation, city information, team members, and general knowledge about Magdeburg and OVGU.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_campus_sensors",
            "description": "Get CURRENT weather, parking, traffic, air quality, or room data from sensors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "enum": ["WeatherObserved", "ParkingSpot", "Traffic", "Room", "AirQuality"],
                        "description": "Type of sensor data"
                    },
                    "location": {"type": "string", "description": "Location name (optional)"}
                },
                "required": ["entity_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_forecast",
            "description": "Get FUTURE weather forecast (1-7 days ahead).",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 3, "description": "Number of days (1-7)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_mobility",
            "description": "Get ALL travel options between two locations: distance, walking/cycling/driving time, AND public transit routes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Starting point"},
                    "destination": {"type": "string", "description": "End point"},
                    "modes": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["walking", "cycling", "driving", "transit"]},
                        "description": "Transport modes (default: all)"
                    }
                },
                "required": ["origin", "destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_building",
            "description": """Get campus building information. USE THIS for ANY question about buildings, towers, facilities, or campus locations.

This tool searches ALL building properties including:
- Building names and IDs
- Functions (what the building is used for)
- Types (dormitory, academic, administration)
- Aliases (reception, tower, library, mensa, etc.)
- Departments, institutes, facilities inside

Examples of when to use this:
- "What is the tower near university?" -> search for "tower"
- "Where is reception?" -> search for "reception"
- "What is building 29?" -> info for building_id "29"
- "Student housing on campus" -> search for "student housing" or "dormitory"
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["info", "search", "nearby"],
                        "description": "info=get specific building, search=find by description/function, nearby=buildings near another"
                    },
                    "building_id": {
                        "type": "string",
                        "description": "Building ID (01-30, campus_tower) or name (library, mensa, tower)"
                    },
                    "search_query": {
                        "type": "string",
                        "description": "Search term for finding buildings (e.g., 'tower', 'reception', 'student housing', 'computer science')"
                    }
                },
                "required": ["query_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_transit_info",
            "description": "Get transit system information: stop details, line info, transfer hubs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {"type": "string", "enum": ["stop", "line", "transfers", "nearest_from_building", "transfer_hubs"]},
                    "stop_name": {"type": "string"},
                    "line_name": {"type": "string"},
                    "line1": {"type": "string"},
                    "line2": {"type": "string"},
                    "building_id": {"type": "string"}
                },
                "required": ["query_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_landmark_info",
            "description": "Get info about campus landmarks and points of interest.",
            "parameters": {
                "type": "object",
                "properties": {
                    "landmark_name": {"type": "string", "description": "Name of the landmark"}
                },
                "required": ["landmark_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_places",
            "description": "Find restaurants, cafes, supermarkets, mensa, and other places to eat or shop. Can search by cuisine, location, or type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["search", "near_building", "near_stop", "by_cuisine", "mensa_menu"],
                        "description": "Type of search"
                    },
                    "place_type": {
                        "type": "string",
                        "enum": ["Restaurant", "Cafe", "Supermarket", "Mensa", "Kiosk", "all"],
                        "description": "Type of place (default: all)"
                    },
                    "cuisine": {
                        "type": "string",
                        "description": "Cuisine type (e.g., italian, asian, greek, pizza)"
                    },
                    "building_id": {
                        "type": "string",
                        "description": "Building ID for near_building search"
                    },
                    "stop_name": {
                        "type": "string",
                        "description": "Stop name for near_stop search"
                    },
                    "search_term": {
                        "type": "string",
                        "description": "General search term"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 5)"
                    }
                },
                "required": ["query_type"]
            }
        }
    }
]


SYSTEM_PROMPT = """You are IMIQ, a friendly and helpful AI assistant for Magdeburg city and OVGU campus.

## CRITICAL RULES - YOU MUST FOLLOW THESE:

### Rule 1: ALWAYS USE TOOLS BEFORE ANSWERING
For ANY question about locations, buildings, directions, weather, or campus info:
1. FIRST call the appropriate tool
2. WAIT for the tool response
3. ONLY THEN answer using the data returned

DO NOT answer from memory. DO NOT guess. ALWAYS use tools first.

### Rule 2: NEVER MAKE UP INFORMATION
If a tool returns no results or an error:
- Say "I couldn't find information about [X] in my database"
- Suggest alternatives or ask for clarification
- DO NOT invent facts, history, functions, or details

### Rule 3: USE ONLY DATA FROM TOOL RESPONSES
When describing a building, place, or location:
- Use EXACTLY the information returned by the tool
- If tool says function is "Student housing", say that
- DO NOT add made-up details like "symbolic purposes" or "ceremonial events"
- DO NOT add historical information unless the tool provided it

### Rule 4: WHEN IN DOUBT, SEARCH
If someone describes something vaguely ("the tower", "that building", "reception"):
- Use get_building with query_type="search" and search_query with their description
- Try multiple search terms if the first doesn't work

## Your Personality
- Warm, conversational, helpful - like a knowledgeable local friend
- Use emojis naturally (1-3 per response)
- Keep responses concise but friendly

## Response Formatting
- NO markdown formatting (no **, no -, no #)
- Write in natural, flowing sentences and paragraphs
- For routes: mention walking time, transit options, recommendations
- For buildings: mention name, function, key features from the tool data

## Tool Selection Guide:
- "What is [building/tower/place]?" → get_building (search)
- "Where is [building]?" → get_building (info) then describe location
- "How do I get to X?" → get_mobility
- "Current weather" → query_campus_sensors
- "Weather tomorrow" → get_weather_forecast
- "Where can I eat?" → find_places
- "Mensa menu" → find_places (mensa_menu)

## Example Correct Behavior:

User: "What is the tall tower near the university?"

Your process:
1. Call get_building with query_type="search", search_query="tower"
2. Tool returns: Campus Tower, function="Student housing - fully furnished apartments"
3. Reply: "That's the Campus Tower! It's a student dormitory with fully furnished apartments. It's located near the library, mensa, and public transport, so super convenient for students!"

WRONG (never do this):
- Saying it's a "historic tower" or "administrative building" without tool data
- Making up that it has "symbolic purposes"
- Guessing what it might be used for

Remember: Your knowledge comes from the database through tools. Trust the tools, not assumptions!
"""


TOOL_DESCRIPTIONS = {
    "search_knowledge": """
        Knowledge base search. Project information, city details, team members.
        Background information, history, descriptions, explanations.

        Questions like:
        - "What is this project?"
        - "Tell me about Magdeburg"
        - "Who works on this?"
        - "What is IMIQ?"

        General information queries, not locations or buildings.
    """,

    "query_campus_sensors": """
        Real-time sensor data. Current weather, parking, traffic, air quality.

        Questions like:
        - "What's the weather right now?"
        - "Is it raining?"
        - "Parking available?"
        - "Air quality today"
    """,

    "get_weather_forecast": """
        Future weather prediction. Tomorrow, next week.

        Questions like:
        - "Weather forecast"
        - "Will it rain tomorrow?"
        - "Weather this weekend"
    """,

    "get_mobility": """
        Navigation between locations. Distance, time, routes.

        Questions like:
        - "How do I get to X?"
        - "How far is X?"
        - "Route from A to B"
        - "Walking time to mensa"
    """,

    "get_building": """
        Campus buildings, towers, facilities, locations on campus.
        Building information, what buildings are used for, finding buildings.

        Questions like:
        - "What is that tower?"
        - "Where is reception?"
        - "What is building 29?"
        - "Student housing"
        - "Computer science building"
        - "Where is the library?"
        - "What's the tall building near university?"
        - "Function of campus tower"

        ANY question about campus buildings or structures.
    """,

    "get_transit_info": """
        Transit system info. Stops, lines, schedules.

        Questions like:
        - "What lines stop at X?"
        - "Where does Tram 5 go?"
        - "Transfer hubs"
    """,

    "get_landmark_info": """
        Campus landmarks and points of interest.

        Questions like:
        - "Where is the campus tower?"
        - "Landmarks on campus"
    """,

    "find_places": """
        Restaurants, cafes, food, mensa, supermarkets.

        Questions like:
        - "Where can I eat?"
        - "Italian restaurants"
        - "Mensa menu"
        - "Coffee near campus"
    """
}


if __name__ == "__main__":
    print(f"Total tools: {len(TOOLS)}")
    print("\nAvailable tools:")
    for tool in TOOLS:
        name = tool["function"]["name"]
        desc = tool["function"]["description"][:80]
        print(f"  {name}: {desc}...")
