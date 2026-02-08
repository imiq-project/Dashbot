"""
Prompt templates for the Router Agent. Contains system prompts, few-shot examples, and output schema for intent classification.
"""

from typing import Dict, Any

ROUTER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_intent": {
            "type": "string",
            "enum": [
                "get_weather",
                "get_route",
                "find_route",
                "get_location_info",
                "get_parking_info",
                "get_traffic_info",
                "get_air_quality",
                "get_transit_info",
                "get_sensor_info",
                "knowledge_query",
                "greeting",
                "compound_query",
                "clarification_needed"
            ],
            "description": "The main intent of the user query"
        },
        "sub_intents": {
            "type": "array",
            "items": {
                "type": "string"
            },
            "description": "List of sub-intents for compound queries"
        },
        "entities": {
            "type": "object",
            "properties": {
                "origin": {"type": ["string", "null"]},
                "destination": {"type": ["string", "null"]},
                "location": {"type": ["string", "null"]},
                "weather_location": {"type": ["string", "null"]},
                "time_constraint": {"type": ["string", "null"]},
                "building_name": {"type": ["string", "null"]},
                "poi_name": {"type": ["string", "null"]}
            },
            "description": "Extracted entities from the query"
        },
        "required_capabilities": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "sensor_data_retrieval",
                    "graph_location_lookup",
                    "transit_routing",
                    "traffic_data_retrieval",
                    "knowledge_base_search"
                ]
            },
            "description": "Capabilities needed to answer this query"
        },
        "execution_strategy": {
            "type": "string",
            "enum": ["parallel", "sequential"],
            "description": "Whether sub-tasks can run in parallel or must be sequential"
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence score for the intent classification"
        },
        "is_compound": {
            "type": "boolean",
            "description": "Whether this is a compound query with multiple intents"
        },
        "clarification_question": {
            "type": ["string", "null"],
            "description": "Question to ask user if clarification is needed"
        },
        "dialogue_action": {
            "type": "string",
            "enum": ["execute_immediately", "ask_clarification", "continue_conversation"],
            "description": "How to proceed with the dialogue: execute_immediately (have all info), ask_clarification (need more info), continue_conversation (follow-up to previous turn)"
        },
        "missing_entities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of entities that are missing and need to be gathered from user"
        }
    },
    "required": [
        "primary_intent",
        "sub_intents",
        "entities",
        "required_capabilities",
        "execution_strategy",
        "confidence",
        "is_compound",
        "dialogue_action",
        "missing_entities"
    ]
}

ROUTER_SYSTEM_PROMPT = """You are a specialized intent classification and query parsing agent for a Magdeburg mobility assistant.

## CRITICAL CONTEXT: THIS IS A MOBILITY AND LOCATION APP

Users ask about:
- Locations (buildings, stops, streets, landmarks, restaurants, cafes)
- Routes (how to get from A to B)
- Transit (trams, buses, stops)
- Weather and sensors at locations
- Parking at locations

## 🚨 FUNDAMENTAL RULES - READ CAREFULLY

### RULE #1: EVERY LOCATION NAME IS VALID
If a user mentions ANY location name - **even if you don't recognize it**:
- ✅ ALWAYS extract it as an entity
- ✅ ALWAYS set appropriate intent (get_location_info, find_route, etc.)
- ✅ ALWAYS include graph_location_lookup capability
- ✅ Use HIGH confidence (0.85+) for clear location queries
- ❌ NEVER use clarification_needed just because you don't know the name
- ❌ NEVER second-guess location names

**Examples of valid location names (trust Neo4j has them):**
- German stop names: Reform, Hasselbachplatz, Universitätsplatz, Opernhaus, Rathaus.. you may not know trust Neo4j has them
- Buildings: Mensa, Library, Tower, Building 01-30 and many more you may now know trust Neo4j has them
- Landmarks: Dom, Cathedral, Campus Tower
- Streets: Ernst-Reuter-Allee, Breiter Weg
- ANY German place name the user mentions

### RULE #2: LOCATION QUERY PATTERNS
These are ALL location queries → use get_location_info + graph_location_lookup:
- "Where is X?"
- "Find X"
- "X location"
- "X tram stop"
- "Where is the X?"
- "Is there a [place type] near X?"

### RULE #3: NEVER USE clarification_needed FOR LOCATION NAMES
❌ WRONG:
- User: "Where is Reform?"
- You: clarification_needed (because you don't recognize "Reform")

✅ CORRECT:
- User: "Where is Reform?"
- You: get_location_info + graph_location_lookup + location="Reform" + confidence=0.90+

### RULE #4: HIGH CONFIDENCE FOR LOCATION QUERIES
Location queries are CLEAR queries. Use confidence 0.85-0.95 for:
- "Where is X?" → 0.92
- "Find X" → 0.90
- "X stop" → 0.95
- "From X to Y" → 0.88

Only use low confidence (<0.5) for truly ambiguous queries like "What about that?"

---

## SUPPORTED INTENTS

**get_weather**: User wants current weather information
- Examples: "What's the weather?", "Is it raining?", "Temperature at Building 03?", "Weather near mensa?"
- Capabilities:
  - NO location: sensor_data_retrieval only
  - WITH location (building, mensa, etc.): graph_location_lookup + sensor_data_retrieval (SEQUENTIAL!)
- **IMPORTANT**: If user asks about weather at/near a specific place, you MUST include BOTH graph_location_lookup AND sensor_data_retrieval with execution_strategy="sequential"

**get_route**: User wants navigation/transit directions
- Examples: "How do I get to the mensa?", "Route from Hauptbahnhof to campus", "From Reform to Opernhaus"
- Capabilities: graph_location_lookup + transit_routing (sequential)

**get_location_info**: User wants information about a physical location/building/POI/stop/sensor
- Examples: "Where is Building 03?", "Where is Reform?", "Find a cafe", "Hasselbachplatz location", "Reform tram stop"
- Capabilities: graph_location_lookup
- **USE THIS FOR ALL "WHERE IS X" QUERIES**
- **USE THIS FOR ALL SENSOR QUERIES** (where are sensors, list sensors, tell me about sensors)
- **USE THIS FOR BUILDING INFO QUERIES** ("What is Building 80?", "What do they do at Building X?", "Tell me about the library")
- Building data (name, function, departments, institutes, research focus, facilities) is stored in Neo4j, NOT in knowledge base!

**get_parking_info**: User wants parking availability information
- Examples: "Is there parking available?", "Parking at Northpark?"
- Capabilities: graph_location_lookup + sensor_data_retrieval (sequential)

**get_traffic_info**: User wants traffic conditions
- Examples: "How's traffic on A2?", "Traffic at computer science faculty?"
- Capabilities: graph_location_lookup + traffic_data_retrieval (sequential if location mentioned)

**get_air_quality**: User wants air quality information
- Examples: "What's the air quality?", "How's the air?", "Air quality near Building 80?"
- Capabilities:
  - NO location: sensor_data_retrieval only
  - WITH location: graph_location_lookup + sensor_data_retrieval (SEQUENTIAL!)

**get_transit_info**: User wants public transit information (stops, lines, schedules)
- Examples: "Which trams stop at Reform?", "What lines go to Hauptbahnhof?", "Transit near the mensa?"
- Capabilities: graph_location_lookup

**get_sensor_info**: User wants general sensor information
- Examples: "What sensors are near Building 03?", "List sensors at the campus"
- Capabilities: graph_location_lookup + sensor_data_retrieval (sequential)

**knowledge_query**: User has a general NON-LOCATION question about policies, schedules, or events
- Examples: "When does the library close?", "What events are happening?"
- Capabilities: knowledge_base_search
- **NOTE: Do NOT use this for "Where is X" queries - those are get_location_info!**
- **NOTE: Do NOT use this for building info queries!** Questions like "What is Building 80?", "What do they do at the mensa?", "Tell me about Building 03" should use get_location_info because building data (function, departments, research, facilities) is stored in Neo4j graph, not in documents!
- **NOTE: Do NOT use this for building/campus property queries!** Questions about dorms, dormitories, housing, accommodation, labs, facilities, departments, prices, cooling, infrastructure are ALL stored as building properties in Neo4j (especially in the 'note' and 'function' fields). Use get_location_info + graph_location_lookup for these!

**compound_query**: User has multiple requests in one query
- Examples: "Weather and route to mensa", "Where is Building 03 and how do I get there?"

**greeting**: Basic greetings
- Examples: "Hi", "Hello", "Thanks", "Goodbye"

**clarification_needed**: Query is TRULY ambiguous (NO location name mentioned)
- Examples: "What about that place?" (no place name given), "Is it open?" (no context)
- **DO NOT USE THIS if user mentions a location name - even if unknown to you!**

---

## REQUIRED CAPABILITIES MAPPING

Based on intent, select the appropriate capabilities:

**graph_location_lookup**: For ALL location/spatial queries
- ✅ All building locations ("Where is Building 03?")
- ✅ All stop locations ("Where is Reform?", "Hasselbachplatz location")
- ✅ All POI searches ("Find a restaurant", "Is there a cafe near X?")
- ✅ All distance queries ("How far is X from Y?")
- ✅ ALL "where is X" queries
- ✅ Route queries (need to find locations first)
- ✅ ALL SENSOR QUERIES ("Where are the weather sensors?", "List parking sensors", "Tell me about sensors")

**sensor_data_retrieval**: For REAL-TIME data only
- Weather queries (current conditions)
- Parking availability
- Uses FIWARE API

**transit_routing**: For travel time/duration calculations
- Route planning with turn-by-turn directions
- Duration estimates for different transport modes
- Uses OpenRouteService

**traffic_data_retrieval**: For traffic conditions
- Real-time traffic data
- Uses TomTom API

**knowledge_base_search**: ONLY for non-location general info
- Opening hours, schedules
- University policies, events
- Uses RAG system

---

## CRITICAL RULES FOR CAPABILITY SELECTION

1. **ANY "where is X" query** → graph_location_lookup
   - "Where is Reform?" → graph_location_lookup
   - "Where is Opernhaus?" → graph_location_lookup
   - "Find the mensa" → graph_location_lookup

2. **Route queries** → graph_location_lookup + transit_routing (sequential)
   - Need to find locations first, then calculate route

3. **Weather/parking at location** → graph_location_lookup + sensor_data_retrieval (sequential)
   - Need to find location first, then get sensor data

4. **General weather (no location)** → sensor_data_retrieval only

---

## ENTITY EXTRACTION RULES

1. **Locations**: Extract ALL location names mentioned
   - Keep names as user wrote them: "Reform" stays "Reform", "Opernhaus" stays "Opernhaus"
   - Normalize building numbers: "Building 3" → "Building 03"
   - Extract into both 'location' and 'poi_name' fields for location queries

2. **Routes**: Identify origin and destination
   - "from X to Y" → origin: "X", destination: "Y"
   - "how to get to Y" → origin: null, destination: "Y"
   - "from Reform to Opernhaus" → origin: "Reform", destination: "Opernhaus"

3. **Time constraints**: Extract temporal information
   - "now", "today", "tomorrow", specific times

---

## EXECUTION STRATEGY

**parallel**: When sub-tasks are independent
- Just getting weather
- Just finding a location
- Multiple independent queries

**sequential**: When tasks have dependencies
- Route queries (find locations → calculate route)
- Weather at location (find location → get weather)
- Parking at location (find location → get parking)

---

## CONFIDENCE SCORING GUIDELINES

**0.9-1.0**: Crystal clear query
- "Where is Building 03?" → 0.98
- "What's the weather?" → 0.98

**0.85-0.89**: Clear query with standard phrasing
- "Where is Reform?" → 0.92 (clear location query, unknown name is OK)
- "Find the mensa" → 0.90
- "Reform tram stop" → 0.95

**0.7-0.84**: Clear intent, minor ambiguity
- "How to get to that building?" → 0.75

**0.5-0.69**: Ambiguous but likely interpretation
- "What about parking?" → 0.60

**<0.5**: Too ambiguous, request clarification
- "What about that?" → 0.30
- "Is it open?" → 0.25

**⚠️ IMPORTANT: Unknown location names should NOT lower confidence!**
- "Where is XYZ?" is still a CLEAR location query even if you don't know "XYZ"
- Confidence should be 0.85-0.95 for clear location queries regardless of recognition

---

## DIALOGUE ACTION RULES

Determine the appropriate dialogue_action based on what information is available:

**execute_immediately**: User query has all required information
- "What's the weather?" → All info present, execute immediately
- "Where is Building 03?" → Location specified, execute immediately
- "How do I get from Hauptbahnhof to Building 03 by car?" → Origin, destination, mode all present

**ask_clarification**: Missing required information that affects the answer
- "How do I get to Building 03?" → Missing transport_mode
  - missing_entities: ["transport_mode"]
  - Note: Origin can default to user location, but transport mode affects route significantly
- "I want to go to the mensa" → Missing transport_mode
  - missing_entities: ["transport_mode"]

**continue_conversation**: User is responding to a previous clarification
- "I'll take my car" → Providing transport_mode in response to previous question
- "By bus" → Providing transport_mode
- "Walking" → Providing transport_mode
- "The one near the library" → Providing location clarification

### Key Rules for dialogue_action:

1. **Route queries WITHOUT transport mode** → ask_clarification, missing_entities: ["transport_mode"]
   - "How do I get to X?" → ask_clarification
   - "Route to the mensa" → ask_clarification
   - "I want to go from A to B" → ask_clarification

2. **Route queries WITH transport mode** → execute_immediately
   - "How do I drive to X?" → execute_immediately
   - "Walking route to the mensa" → execute_immediately
   - "Take the tram to Hauptbahnhof" → execute_immediately

3. **Simple information queries** → execute_immediately
   - Weather, location info, parking status → execute_immediately

4. **Short responses that provide missing info** → continue_conversation
   - "Car", "Walking", "By tram" → continue_conversation
   - "I'll drive", "Let's walk" → continue_conversation

---

## OUTPUT FORMAT

You must output ONLY valid JSON matching the schema. No explanations, no markdown.

```json
{
  "primary_intent": "get_location_info",
  "sub_intents": ["get_location_info"],
  "entities": {
    "origin": null,
    "destination": null,
    "location": "Reform",
    "weather_location": null,
    "time_constraint": null,
    "building_name": null,
    "poi_name": "Reform"
  },
  "required_capabilities": ["graph_location_lookup"],
  "execution_strategy": "parallel",
  "confidence": 0.92,
  "is_compound": false,
  "clarification_question": null
}
```

---

## PATTERN EXAMPLES

**Pattern: "Where is X?"**
→ primary_intent: get_location_info
→ location: X, poi_name: X
→ capabilities: [graph_location_lookup]
→ confidence: 0.90-0.95

**Pattern: "What is Building X?" or "Tell me about Building X" or "What do they do at X?"**
→ primary_intent: get_location_info (NOT knowledge_query!)
→ building_name: X, location: X
→ capabilities: [graph_location_lookup]
→ confidence: 0.88-0.92
→ Building info (function, departments, research, facilities) is in Neo4j, not documents!

**Pattern: "X tram stop" or "X stop"**
→ primary_intent: get_location_info
→ location: X, poi_name: X
→ capabilities: [graph_location_lookup]
→ confidence: 0.95

**Pattern: "From X to Y" or "How to get from X to Y"**
→ primary_intent: find_route
→ origin: X, destination: Y
→ capabilities: [graph_location_lookup, transit_routing]
→ execution_strategy: sequential
→ confidence: 0.88-0.92

**Pattern: "Weather at X"**
→ primary_intent: get_weather
→ location: X, weather_location: X
→ capabilities: [graph_location_lookup, sensor_data_retrieval]
→ execution_strategy: sequential
→ confidence: 0.90

**Pattern: "Parking at X"**
→ primary_intent: get_parking_info
→ location: X, poi_name: X
→ capabilities: [graph_location_lookup, sensor_data_retrieval]
→ execution_strategy: sequential
→ confidence: 0.88

**Pattern: "Where are the [type] sensors?" or "List [type] sensors" or "Tell me about [type] sensors"**
→ primary_intent: get_location_info
→ location: "[type] sensors", poi_name: "[type] sensors"
→ capabilities: [graph_location_lookup]
→ execution_strategy: parallel
→ confidence: 0.92
→ Examples: "Where are the weather sensors?", "List parking sensors", "Show me traffic sensors", "Tell me about sensors"

**Pattern: "Is there a [type] sensor near X?"**
→ primary_intent: get_location_info
→ location: X, building_name: X
→ capabilities: [graph_location_lookup]
→ execution_strategy: parallel
→ confidence: 0.90

**Pattern: "How many dorms?" or "Compare dorm prices" or "Student accommodation" or "Housing options"**
→ primary_intent: get_location_info (NOT knowledge_query!)
→ location: "dorm", poi_name: "dorm"
→ capabilities: [graph_location_lookup]
→ confidence: 0.90
→ Dorm/housing data (prices, room types, unit counts) is stored in Neo4j building 'note' property, NOT in knowledge base!
→ Also applies to: labs, facilities, departments, research centers, infrastructure queries

**Pattern: "Which buildings look alike?" or "Which buildings are similar?" or "Buildings with similar design"**
→ primary_intent: get_location_info (NOT knowledge_query!)
→ location: "similar buildings", poi_name: "alike"
→ capabilities: [graph_location_lookup]
→ execution_strategy: parallel
→ confidence: 0.90
→ Building similarity/design info is stored in Neo4j node properties, not in knowledge base!

**Pattern: "How many sensors?" or "How many [type] sensors?" or "Count sensors"**
→ primary_intent: get_location_info
→ location: "sensors", poi_name: "sensors"
→ capabilities: [graph_location_lookup]
→ execution_strategy: parallel
→ confidence: 0.92
→ Use graph_location_lookup to query sensor counts from Neo4j

**Pattern: "What can I eat at [restaurant]?" or "What food/cuisine does [restaurant] serve?" or "What type of food at [place]?"**
→ primary_intent: get_location_info (NOT knowledge_query!)
→ poi_name: [restaurant], location: [restaurant]
→ capabilities: [graph_location_lookup]
→ execution_strategy: parallel
→ confidence: 0.92
→ Restaurant cuisine/food info is stored in Neo4j POI properties (cuisine field), NOT in knowledge base!
→ Examples: "What can I eat at Izgaram?", "What cuisine is Döner King?", "What food at Mensa?"

---

## IMPORTANT FINAL REMINDERS

1. ✅ This is a MOBILITY/LOCATION app - location queries are the PRIMARY use case
2. ✅ EVERY location name is valid - trust Neo4j has the data
3. ✅ "Where is X?" is ALWAYS get_location_info + graph_location_lookup
4. ✅ Use HIGH confidence (0.85-0.95) for clear location queries
5. ✅ Unknown location names should NOT trigger clarification_needed
6. ✅ Unknown location names should NOT lower confidence
7. ✅ Always output valid JSON only
8. ✅ Use null for missing entities, not empty strings
9. ✅ For compound queries, list ALL sub-intents
10. ✅ Consider dependencies when choosing execution strategy
"""

FEW_SHOT_EXAMPLES = [
    {
        "user_query": "What's the weather?",
        "expected_output": {
            "primary_intent": "get_weather",
            "sub_intents": ["get_weather"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": None,
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": None
            },
            "required_capabilities": ["sensor_data_retrieval"],
            "execution_strategy": "parallel",
            "confidence": 0.98,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "What's the weather near Building 80?",
        "expected_output": {
            "primary_intent": "get_weather",
            "sub_intents": ["get_weather"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "Building 80",
                "weather_location": "Building 80",
                "time_constraint": None,
                "building_name": "Building 80",
                "poi_name": None
            },
            "required_capabilities": ["graph_location_lookup", "sensor_data_retrieval"],
            "execution_strategy": "sequential",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "How do I get to Building 03 from Hauptbahnhof?",
        "expected_output": {
            "primary_intent": "get_route",
            "sub_intents": ["get_route"],
            "entities": {
                "origin": "Hauptbahnhof",
                "destination": "Building 03",
                "location": None,
                "weather_location": None,
                "time_constraint": None,
                "building_name": "Building 03",
                "poi_name": None
            },
            "required_capabilities": ["graph_location_lookup", "transit_routing"],
            "execution_strategy": "sequential",
            "confidence": 0.95,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "ask_clarification",
            "missing_entities": ["transport_mode"]
        }
    },
    {
        "user_query": "What's the weather at Building 03 and how do I get there from the station?",
        "expected_output": {
            "primary_intent": "compound_query",
            "sub_intents": ["get_weather", "get_route"],
            "entities": {
                "origin": "Hauptbahnhof",
                "destination": "Building 03",
                "location": None,
                "weather_location": "Building 03",
                "time_constraint": None,
                "building_name": "Building 03",
                "poi_name": None
            },
            "required_capabilities": [
                "sensor_data_retrieval",
                "graph_location_lookup",
                "transit_routing"
            ],
            "execution_strategy": "parallel",
            "confidence": 0.92,
            "is_compound": True,
            "clarification_question": None,
            "dialogue_action": "ask_clarification",
            "missing_entities": ["transport_mode"]
        }
    },
    {
        "user_query": "Where's the tower?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "tower",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "tower"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.75,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Is there parking near the library?",
        "expected_output": {
            "primary_intent": "get_parking_info",
            "sub_intents": ["get_parking_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "library",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "library"
            },
            "required_capabilities": ["graph_location_lookup", "sensor_data_retrieval"],
            "execution_strategy": "sequential",
            "confidence": 0.88,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Weather and route to mensa",
        "expected_output": {
            "primary_intent": "compound_query",
            "sub_intents": ["get_weather", "get_route"],
            "entities": {
                "origin": None,
                "destination": "Mensa Unicampus",
                "location": None,
                "weather_location": "Mensa Unicampus",
                "time_constraint": None,
                "building_name": None,
                "poi_name": "Mensa Unicampus"
            },
            "required_capabilities": [
                "sensor_data_retrieval",
                "graph_location_lookup",
                "transit_routing"
            ],
            "execution_strategy": "parallel",
            "confidence": 0.90,
            "is_compound": True,
            "clarification_question": None,
            "dialogue_action": "ask_clarification",
            "missing_entities": ["transport_mode"]
        }
    },
    {
        "user_query": "Is there a restaurant near Building 03?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "Building 03",
                "weather_location": None,
                "time_constraint": None,
                "building_name": "Building 03",
                "poi_name": "restaurant"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.88,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "What about that place?",
        "expected_output": {
            "primary_intent": "clarification_needed",
            "sub_intents": ["clarification_needed"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": None,
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": None
            },
            "required_capabilities": [],
            "execution_strategy": "parallel",
            "confidence": 0.2,
            "is_compound": False,
            "clarification_question": "Which location are you asking about? Could you provide more details?",
            "dialogue_action": "ask_clarification",
            "missing_entities": ["location"]
        }
    },
    {
        "user_query": "When does the library close?",
        "expected_output": {
            "primary_intent": "knowledge_query",
            "sub_intents": ["knowledge_query"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "library",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "library"
            },
            "required_capabilities": ["knowledge_base_search"],
            "execution_strategy": "parallel",
            "confidence": 0.93,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "What can I eat at Izgaram?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "Izgaram",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "Izgaram"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "What food does Döner King serve?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "Döner King",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "Döner King"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "What is Building 80 about?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "Building 80",
                "weather_location": None,
                "time_constraint": None,
                "building_name": "Building 80",
                "poi_name": None
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.90,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "What do they do at the mensa?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "mensa",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "mensa"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.88,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Tell me about the Faculty of Computer Science",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "Faculty of Computer Science",
                "weather_location": None,
                "time_constraint": None,
                "building_name": "Faculty of Computer Science",
                "poi_name": None
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.90,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Traffic on A2 and weather",
        "expected_output": {
            "primary_intent": "compound_query",
            "sub_intents": ["get_traffic_info", "get_weather"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "A2",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": None
            },
            "required_capabilities": [
                "traffic_data_retrieval",
                "sensor_data_retrieval"
            ],
            "execution_strategy": "parallel",
            "confidence": 0.91,
            "is_compound": True,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Where is Reform?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "Reform",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "Reform"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Reform tram stop",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "Reform",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "Reform"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.95,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "How do I get to Hasselbachplatz?",
        "expected_output": {
            "primary_intent": "find_route",
            "sub_intents": ["find_route"],
            "entities": {
                "origin": None,
                "destination": "Hasselbachplatz",
                "location": None,
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": None
            },
            "required_capabilities": ["graph_location_lookup", "transit_routing"],
            "execution_strategy": "sequential",
            "confidence": 0.88,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "ask_clarification",
            "missing_entities": ["transport_mode"]
        }
    },
    {
        "user_query": "How can I go from Reform to Opernhaus?",
        "expected_output": {
            "primary_intent": "find_route",
            "sub_intents": ["find_route"],
            "entities": {
                "origin": "Reform",
                "destination": "Opernhaus",
                "location": None,
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": None
            },
            "required_capabilities": ["graph_location_lookup", "transit_routing"],
            "execution_strategy": "sequential",
            "confidence": 0.90,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "ask_clarification",
            "missing_entities": ["transport_mode"]
        }
    },
    {
        "user_query": "Where are the weather sensors?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "weather sensors",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "weather sensors"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Can you tell me about weather sensors?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "weather sensors",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "weather sensors"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.90,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "List all parking sensors",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "parking sensors",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "parking sensors"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Is there a weather sensor near Building 03?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "Building 03",
                "weather_location": None,
                "time_constraint": None,
                "building_name": "Building 03",
                "poi_name": "weather sensor"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.90,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Which buildings look alike?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "similar buildings",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "alike"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.90,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Which 2 buildings are similar?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "similar buildings",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "similar"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.90,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "How many sensors are there?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "sensors",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "sensors"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "How many weather sensors do you have?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "weather sensors",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "weather sensors"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "How many dorms are there on campus?",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "dorm",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "dorm"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.90,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "Compare dormitory prices",
        "expected_output": {
            "primary_intent": "get_location_info",
            "sub_intents": ["get_location_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "dormitory",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "dormitory"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.90,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "What tram lines are available?",
        "expected_output": {
            "primary_intent": "get_transit_info",
            "sub_intents": ["get_transit_info"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": "tram lines",
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "tram lines"
            },
            "required_capabilities": ["graph_location_lookup"],
            "execution_strategy": "parallel",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    },
    {
        "user_query": "I'll take my car",
        "expected_output": {
            "primary_intent": "find_route",
            "sub_intents": ["find_route"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": None,
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": None,
                "transport_mode": "driving"
            },
            "required_capabilities": ["graph_location_lookup", "transit_routing"],
            "execution_strategy": "sequential",
            "confidence": 0.85,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "continue_conversation",
            "missing_entities": []
        }
    },
    {
        "user_query": "By bus",
        "expected_output": {
            "primary_intent": "find_route",
            "sub_intents": ["find_route"],
            "entities": {
                "origin": None,
                "destination": None,
                "location": None,
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": None,
                "transport_mode": "transit"
            },
            "required_capabilities": ["graph_location_lookup", "transit_routing"],
            "execution_strategy": "sequential",
            "confidence": 0.85,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "continue_conversation",
            "missing_entities": []
        }
    },
    {
        "user_query": "I want to walk to the mensa",
        "expected_output": {
            "primary_intent": "find_route",
            "sub_intents": ["find_route"],
            "entities": {
                "origin": None,
                "destination": "mensa",
                "location": None,
                "weather_location": None,
                "time_constraint": None,
                "building_name": None,
                "poi_name": "mensa",
                "transport_mode": "walking"
            },
            "required_capabilities": ["graph_location_lookup", "transit_routing"],
            "execution_strategy": "sequential",
            "confidence": 0.92,
            "is_compound": False,
            "clarification_question": None,
            "dialogue_action": "execute_immediately",
            "missing_entities": []
        }
    }
]


def build_router_prompt(
    user_query: str,
    include_examples: bool = True,
    conversation_context: list[Dict[str, str]] = None
) -> list[Dict[str, Any]]:
    system_content = ROUTER_SYSTEM_PROMPT

    if conversation_context:
        system_content += """

---

## CONVERSATION CONTEXT - CRITICAL FOR MULTI-TURN QUERIES

You have access to the conversation history below. Use it to:
1. **Resolve references**: "What greek options do I have?" after discussing restaurants → understand they want Greek restaurants
2. **Maintain topic continuity**: If user was asking about Building 80, "What sensors are there?" refers to Building 80
3. **Infer missing entities**: "Is there parking nearby?" after discussing mensa → parking near mensa
4. **Understand follow-up queries**: "What about traffic?" after route discussion → traffic on that route

### IMPORTANT:
- When the current query is ambiguous but context makes it clear, use HIGH confidence (0.85+)
- Extract entities from BOTH the current query AND conversation context
- If user references "there", "that building", "nearby", etc., look at previous context for the location
- DO NOT use clarification_needed if the context makes the query clear
"""

    messages = [
        {
            "role": "system",
            "content": system_content
        }
    ]

    if include_examples:
        for example in FEW_SHOT_EXAMPLES:
            messages.append({
                "role": "user",
                "content": example["user_query"]
            })

            import json
            messages.append({
                "role": "assistant",
                "content": json.dumps(example["expected_output"], indent=2)
            })

    if conversation_context:
        messages.append({
            "role": "system",
            "content": "--- CONVERSATION HISTORY (use this to understand context) ---"
        })

        for turn in conversation_context:
            messages.append({
                "role": turn["role"],
                "content": turn["content"]
            })

        messages.append({
            "role": "system",
            "content": "--- END OF CONVERSATION HISTORY ---\n\nNow analyze the following NEW query with the above context in mind:"
        })

    messages.append({
        "role": "user",
        "content": user_query
    })

    return messages


def validate_router_output(output: Dict[str, Any]) -> tuple[bool, str]:
    required_fields = [
        "primary_intent",
        "sub_intents",
        "entities",
        "required_capabilities",
        "execution_strategy",
        "confidence",
        "is_compound",
        "dialogue_action",
        "missing_entities"
    ]

    for field in required_fields:
        if field not in output:
            return False, f"Missing required field: {field}"

    valid_intents = [
        "get_weather",
        "get_route",
        "find_route",
        "get_distance",
        "get_location_info",
        "get_parking_info",
        "get_traffic_info",
        "get_air_quality",
        "get_transit_info",
        "get_sensor_info",
        "knowledge_query",
        "greeting",
        "compound_query",
        "clarification_needed"
    ]
    if output["primary_intent"] not in valid_intents:
        return False, f"Invalid primary_intent: {output['primary_intent']}"

    if not isinstance(output["sub_intents"], list):
        return False, "sub_intents must be a list"

    if not isinstance(output["entities"], dict):
        return False, "entities must be a dictionary"

    if not isinstance(output["required_capabilities"], list):
        return False, "required_capabilities must be a list"

    if output["execution_strategy"] not in ["parallel", "sequential"]:
        return False, f"Invalid execution_strategy: {output['execution_strategy']}"

    if not isinstance(output["confidence"], (int, float)):
        return False, "confidence must be a number"
    if not 0.0 <= output["confidence"] <= 1.0:
        return False, "confidence must be between 0.0 and 1.0"

    if not isinstance(output["is_compound"], bool):
        return False, "is_compound must be a boolean"

    valid_actions = ["execute_immediately", "ask_clarification", "continue_conversation"]
    if output.get("dialogue_action") and output["dialogue_action"] not in valid_actions:
        return False, f"Invalid dialogue_action: {output['dialogue_action']}"

    if output.get("missing_entities") is not None and not isinstance(output["missing_entities"], list):
        return False, "missing_entities must be a list"

    return True, "Valid"
