"""
Prompt templates for the Neo4j Agent. Contains system prompts and function mapping instructions for graph database queries.
"""

from typing import Dict, Any

NEO4J_FUNCTIONS = {
    "get_building_info": {
        "description": "Get detailed information about a campus building",
        "parameters": {
            "building_id": "Building name, number, or ID (e.g., 'Building 03', 'Mensa', 'tower')"
        },
        "examples": [
            "Where is Building 03?",
            "Tell me about the library",
            "What's at the mensa?"
        ]
    },
    "find_building_by_function": {
        "description": """Search for buildings by ANY property (name, function, description, notes, etc.).
        This searches ALL properties on building nodes dynamically!
        Use this for:
        - 'Which buildings look alike?' → find_building_by_function('alike')
        - 'Which buildings are similar?' → find_building_by_function('similar')
        - 'Find buildings with computer science' → find_building_by_function('computer science')
        - 'Buildings with lecture halls' → find_building_by_function('lecture')
        Returns multiple matching buildings (up to 10).""",
        "parameters": {
            "query": "Search term to match against ANY building property"
        },
        "examples": [
            "Which buildings look alike?",
            "Which buildings are similar?",
            "Find computer science buildings",
            "Buildings with labs",
            "Dorms with housing options"
        ]
    },
    "find_any_location": {
        "description": """Universal location search across ALL node types (Buildings, Stops, POIs, Landmarks).
        Use this for general 'where is X?' queries when you don't know if it's a building, stop, POI, or landmark.
        This searches everything at once!""",
        "parameters": {
            "search_term": "What to search for (name, description, or alias)",
            "limit": "Max results to return (default: 5)"
        },
        "examples": [
            "Where is Reform?",
            "Where is the mensa?",
            "Where is Hasselbachplatz?",
            "Find the tower"
        ]
    },
    "get_nearby_buildings": {
        "description": "Find buildings near a specific building using spatial relationships",
        "parameters": {
            "building_id": "Building name, number, or ID (e.g., 'Building 03', 'mensa', 'library')"
        },
        "examples": [
            "What buildings are near Building 03?",
            "Which buildings are close to the mensa?",
            "Buildings near the library"
        ]
    },
    "find_places_near_building": {
        "description": "Find restaurants, cafes, or other POIs near a building. Supports cuisine filtering!",
        "parameters": {
            "building_id": "Building name or ID",
            "place_type": "Type: Restaurant, Cafe, Bar, or 'all'",
            "cuisine": "Optional cuisine filter: turkish, italian, asian, greek, indian, german, pizza, etc.",
            "radius_meters": "Search radius (default: 1000)",
            "limit": "Max results (default: 5)"
        },
        "examples": [
            "Is there a restaurant near Building 03?",
            "Turkish restaurant near Building 27",
            "Italian restaurants near the library",
            "Cafes within 500m of the mensa"
        ]
    },
    "find_places_by_cuisine": {
        "description": "Find restaurants by cuisine type (Turkish, Italian, Asian, Greek, etc.)",
        "parameters": {
            "cuisine": "Cuisine type: turkish, italian, asian, greek, indian, german, etc.",
            "place_type": "Type: Restaurant (default)",
            "limit": "Max results (default: 5)"
        },
        "examples": [
            "Find a Turkish restaurant",
            "Suggest an Italian restaurant",
            "Any Asian restaurants?",
            "Greek food nearby"
        ]
    },
    "find_places_near_coordinates": {
        "description": "Find places near specific lat/lon coordinates",
        "parameters": {
            "lat": "Latitude",
            "lon": "Longitude",
            "place_type": "Type: Restaurant, Cafe, Bar, or 'all'",
            "cuisine": "Cuisine type (optional)",
            "radius_meters": "Search radius (default: 1000)",
            "limit": "Max results (default: 5)"
        },
        "examples": [
            "Restaurants near my current location",
            "Find cafes nearby"
        ]
    },
    "get_nearest_tram_from_building": {
        "description": "Find the nearest tram/bus stop to a building",
        "parameters": {
            "building_id": "Building name or ID"
        },
        "examples": [
            "Nearest tram stop to Building 03",
            "How do I get to public transport from the library?"
        ]
    },
    "get_directions_between_buildings": {
        "description": "Get walking directions between two campus buildings (ONLY use when BOTH locations are definitely buildings)",
        "parameters": {
            "from_building": "Starting building name or ID",
            "to_building": "Destination building name or ID"
        },
        "examples": [
            "How do I walk from Building 03 to the mensa?",
            "Walking directions from library to tower"
        ]
    },
    "get_multimodal_route": {
        "description": """Smart routing that handles ANY combination of locations:
        - Transit stops (e.g., Hauptbahnhof, Hasselbachplatz, Reform)
        - Buildings (e.g., Building 03, library, mensa)
        - Landmarks (e.g., tower, cathedral)
        USE THIS for routing queries when origin or destination might be a transit stop!""",
        "parameters": {
            "origin": "Starting location (stop, building, or landmark name)",
            "destination": "Destination location (stop, building, or landmark name)"
        },
        "examples": [
            "How do I get from Hauptbahnhof to Building 03?",
            "Route from Reform to the library",
            "How to get from the mensa to Hasselbachplatz?",
            "Directions from Building 03 to Opernhaus"
        ]
    },
    "get_landmark_info": {
        "description": "Get information about a campus landmark",
        "parameters": {
            "landmark_name": "Landmark name (e.g., 'tower', 'cathedral')"
        },
        "examples": [
            "Where is the tower?",
            "Tell me about the cathedral"
        ]
    },
    "get_distance_between_locations": {
        "description": """Calculate the straight-line distance between ANY two locations.
        Searches across ALL node types (Building, POI, Stop, Landmark) to find both locations
        and returns the distance in meters with estimated walking time.
        USE THIS for 'how far' questions about ANY two places!""",
        "parameters": {
            "location1": "First location name (building, POI, stop, or landmark)",
            "location2": "Second location name (building, POI, stop, or landmark)"
        },
        "examples": [
            "How far is the mensa from Building 03?",
            "How far is Izgaram from the library?",
            "Distance between Hauptbahnhof and the campus?",
            "How far is the parking from Building 80?",
            "What's the distance from Reform to the mensa?"
        ]
    },
    "get_poi_info": {
        "description": """Get DETAILED information about a specific POI (restaurant, cafe, bar, shop, etc.).
        Returns name, type, cuisine, address, coordinates, dietary options, opening hours,
        nearest transit stop, nearest building, and street.
        Use this when user asks specifically about a POI's details, menu, or properties.""",
        "parameters": {
            "poi_name": "Name of the POI (e.g., 'Izgaram', 'Starbucks', 'Mensa')"
        },
        "examples": [
            "Tell me about Izgaram",
            "What cuisine does Döner King have?",
            "Details about the Mensa restaurant",
            "What are the opening hours of Starbucks?"
        ]
    },
    "get_stop_info": {
        "description": """Get DETAILED information about a specific transit stop.
        Returns name, ID, coordinates, and all tram/bus lines serving the stop.
        Use this when user asks about a specific stop's details or which lines serve it.""",
        "parameters": {
            "stop_name": "Name of the transit stop (e.g., 'Magdeburg Hauptbahnhof', 'Reform')"
        },
        "examples": [
            "Tell me about Reform stop",
            "What lines serve Hauptbahnhof?",
            "Details about Hasselbachplatz stop"
        ]
    },
    "get_line_info": {
        "description": """Get information about a specific tram/bus line including its stops.
        Returns the line name and ordered list of all stops on the line.
        Use this when user asks about a specific tram/bus line.""",
        "parameters": {
            "line_name": "Line name or number (e.g., 'Line 1', 'Line 9', 'N1')"
        },
        "examples": [
            "What stops does Line 1 have?",
            "Tell me about tram Line 9",
            "Where does Line 2 go?"
        ]
    },
    "get_all_lines": {
        "description": """List ALL tram/bus lines available in the transit network.
        Returns line names and stop counts. Use when user wants to know what lines exist.""",
        "parameters": {},
        "examples": [
            "What tram lines are there?",
            "List all bus/tram lines",
            "How many tram lines exist?",
            "What public transport lines are available?"
        ]
    },
    "get_line_route": {
        "description": """Get the full ordered route of a tram/bus line (all stops in sequence).
        Returns stops in order for both directions of travel.""",
        "parameters": {
            "line_name": "Line name (e.g., 'Line 1', 'Line 9')",
            "direction": "Direction: 'forward', 'reverse', or 'both' (default: 'both')"
        },
        "examples": [
            "Show me the full route of Line 1",
            "What's the route of tram Line 9?",
            "All stops on Line 2 in order"
        ]
    },
    "check_proximity": {
        "description": """Check if two locations are near each other.
        Uses graph relationships (NEARBY, ADJACENT_TO, ACCESSIBLE_ROUTE) and distance calculation.
        Returns whether they are near and the distance/walk time between them.""",
        "parameters": {
            "location1": "First location name (building, POI, or stop)",
            "location2": "Second location name (building, POI, or stop)"
        },
        "examples": [
            "Is the mensa near Building 03?",
            "Are Building 05 and Building 06 close?",
            "Is Izgaram near the library?",
            "How close is Reform to Building 03?"
        ]
    },
    "get_accessible_route": {
        "description": """Find wheelchair-accessible route between two buildings.
        Uses pre-computed ACCESSIBLE_ROUTE relationships with distance and walk time.
        Returns direct route or multi-hop accessible path (up to 3 hops).""",
        "parameters": {
            "from_building": "Starting building name",
            "to_building": "Destination building name"
        },
        "examples": [
            "Is there a wheelchair accessible route from Building 03 to mensa?",
            "Accessible path from library to Building 05",
            "Can I get from Building 01 to Building 10 in a wheelchair?"
        ]
    },
    "get_walking_connections": {
        "description": """Find transit stops within walking distance of a given stop.
        Returns nearby stops with walking distance in meters and estimated walk time.
        Use this when user wants to know what stops they can walk to from a stop.""",
        "parameters": {
            "stop_name": "Transit stop name (e.g., 'Magdeburg Hauptbahnhof', 'Reform')",
            "max_walk_time": "Maximum walking time in minutes (default: 10)"
        },
        "examples": [
            "What stops can I walk to from Hauptbahnhof?",
            "Stops within walking distance of Reform",
            "What's walkable from Hasselbachplatz?"
        ]
    },
    "get_building_spatial_relations": {
        "description": """Get ALL spatial relationships for a building:
        - What area it faces (FACES)
        - Buildings it's contiguous to (CONTIGUOUS_TO)
        - Buildings that surround/are surrounded by it
        - Similar-looking buildings (LOOKS_ALIKE)
        - Same-structure buildings (SAME_STRUCTURE)
        - Internally connected buildings (CONNECTED_INTERNALLY, e.g., through passages)
        Use for 'what faces X?', 'what's connected to X?', 'similar buildings to X?'""",
        "parameters": {
            "building_name": "Building name or number"
        },
        "examples": [
            "What area does Building 06 face?",
            "Is Building 03 connected to any other building?",
            "What buildings look similar?",
            "What's contiguous to the mensa?"
        ]
    },
    "get_building_landmarks": {
        "description": """Get landmarks associated with a building.
        Returns landmarks the building has (HAS_LANDMARK), is behind (BEHIND_LANDMARK),
        or has views of (VIEWS). Includes position and side information.""",
        "parameters": {
            "building_name": "Building name or number"
        },
        "examples": [
            "What landmarks are near Building 01?",
            "Are there any landmarks at Building 18?",
            "What can I see from the Campus Tower?"
        ]
    },
    "get_building_infrastructure": {
        "description": """Get infrastructure details for a building, including cooling systems.
        Returns which buildings provide cooling to this building and which receive cooling from it.""",
        "parameters": {
            "building_name": "Building name or number"
        },
        "examples": [
            "Does Building 03 have cooling?",
            "What infrastructure does Building 02 have?",
            "Which building provides cooling to Building 01?"
        ]
    },
    "get_area_info": {
        "description": """Get information about a campus area (plaza, square, etc.).
        Returns area details, landmarks it contains, buildings that border it,
        and buildings that face it.""",
        "parameters": {
            "area_name": "Area name (e.g., 'University Main Plaza', 'Pfälzer Platz')"
        },
        "examples": [
            "Tell me about the University Main Plaza",
            "What's in the main plaza?",
            "What buildings are around Pfälzer Platz?"
        ]
    },
    "find_transfer_hubs": {
        "description": """Find transit stops served by multiple tram/bus lines (transfer hubs).
        Returns stops with the most line connections, useful for finding transfer points.""",
        "parameters": {
            "min_lines": "Minimum number of lines a stop must serve (default: 2)",
            "limit": "Max results to return (default: 10)"
        },
        "examples": [
            "Where can I transfer between tram lines?",
            "What are the main transfer hubs?",
            "Which stops have the most connections?"
        ]
    },
    "get_sensor_for_location": {
        "description": "Get sensor information for a specific named location (searches by sensor name/id)",
        "parameters": {
            "location_name": "Location or sensor name to search for",
            "sensor_type": "Optional type filter (Weather, Parking, Traffic, AirQuality)"
        },
        "examples": [
            "Find sensor at Building 03",
            "Get the parking sensor info"
        ]
    },
    "list_sensors_by_type": {
        "description": """List ALL sensors of a specific type. Use this when users ask:
        - 'Where are the weather sensors?' → list_sensors_by_type('Weather')
        - 'Show me all parking sensors' → list_sensors_by_type('Parking')
        - 'What traffic sensors do you have?' → list_sensors_by_type('Traffic')
        Returns a list of all sensors with their id, name, type, latitude, longitude.""",
        "parameters": {
            "sensor_type": "Type of sensor: Weather, Parking, Traffic, or AirQuality"
        },
        "examples": [
            "Where are the weather sensors?",
            "List all parking sensors",
            "Show me the traffic sensors",
            "What air quality sensors exist?"
        ]
    },
    "list_all_sensors": {
        "description": """List ALL sensors of ALL types. Use this when users ask:
        - 'How many sensors are there?' → list_all_sensors()
        - 'What sensors do you have?' → list_all_sensors()
        - 'List all sensors' → list_all_sensors()
        - 'Show me all sensors' → list_all_sensors()
        Returns total count, count by type, and list of all sensors.""",
        "parameters": {},
        "examples": [
            "How many sensors are there?",
            "What sensors do you have?",
            "List all sensors",
            "Show me all sensors",
            "How many sensors?"
        ]
    },
    "get_sensor_near_building": {
        "description": "Find the SINGLE nearest sensor to a building. Use get_all_sensors_near_building if user wants multiple sensors.",
        "parameters": {
            "building_id": "Building name or ID",
            "sensor_type": "Optional type filter (Weather, Parking, Traffic, AirQuality)"
        },
        "examples": [
            "Is there A sensor near Building 03?",
            "Find THE nearest parking sensor near the mensa"
        ]
    },
    "get_all_sensors_near_building": {
        "description": """Find ALL sensors near a building. Use this when user wants multiple sensors or asks about 'sensors' (plural).
        Returns a list of all sensors with their types and distances.
        PREFER THIS over get_sensor_near_building for general sensor queries!""",
        "parameters": {
            "building_id": "Building name or ID",
            "sensor_type": "Optional type filter (Weather, Parking, Traffic, AirQuality)",
            "limit": "Maximum number of sensors to return (default 10)"
        },
        "examples": [
            "What sensors are near Building 80?",
            "Show me all sensors near the mensa",
            "List sensors near the library",
            "What other sensors are nearby?",
            "Any sensors near Building 03?"
        ]
    },
    "get_nearest_sensor": {
        "description": "Find the nearest sensor to specific coordinates within a radius",
        "parameters": {
            "latitude": "Latitude coordinate",
            "longitude": "Longitude coordinate",
            "sensor_type": "Optional type filter (Weather, Parking, Traffic, AirQuality)",
            "radius": "Search radius in meters (default 1000)"
        },
        "examples": [
            "Nearest weather sensor to my location",
            "Find sensor at coordinates 52.139, 11.645"
        ]
    },
    "get_buildings_in_direction": {
        "description": """Find buildings in a specific cardinal direction (north/south/east/west) from a building.
        Uses the BORDERED_BY relationship with 'side' property from the graph database.
        MUST USE THIS for directional questions like 'what is north of X?'""",
        "parameters": {
            "building_name": "The reference building name or number",
            "direction": "Cardinal direction: 'north', 'south', 'east', or 'west'"
        },
        "examples": [
            "What is north of Building 3?",
            "What buildings are south of the mensa?",
            "What's east of the library?",
            "Buildings west of Building 10"
        ]
    },
    "what_is_north_of": {
        "description": "Find buildings north of a specific building (shorthand for get_buildings_in_direction with direction='north')",
        "parameters": {
            "building_name": "The reference building name or number"
        },
        "examples": [
            "What is north of Building 3?",
            "What's to the north of the mensa?"
        ]
    },
    "what_is_south_of": {
        "description": "Find buildings south of a specific building (shorthand for get_buildings_in_direction with direction='south')",
        "parameters": {
            "building_name": "The reference building name or number"
        },
        "examples": [
            "What is south of Building 3?",
            "What's to the south of the library?"
        ]
    },
    "what_is_east_of": {
        "description": "Find buildings east of a specific building (shorthand for get_buildings_in_direction with direction='east')",
        "parameters": {
            "building_name": "The reference building name or number"
        },
        "examples": [
            "What is east of Building 3?",
            "What's to the east of the mensa?"
        ]
    },
    "what_is_west_of": {
        "description": "Find buildings west of a specific building (shorthand for get_buildings_in_direction with direction='west')",
        "parameters": {
            "building_name": "The reference building name or number"
        },
        "examples": [
            "What is west of Building 3?",
            "What's to the west of the library?"
        ]
    },
    "get_building_borders": {
        "description": """Get ALL borders of a building (streets, other buildings, areas) with their directions.
        Returns what is on each side (north/south/east/west) of the building.
        Use this for general 'what surrounds X?' or 'what borders X?' questions.""",
        "parameters": {
            "building_name": "The building name or number"
        },
        "examples": [
            "What surrounds Building 3?",
            "What borders the mensa?",
            "Show me what's around the library"
        ]
    }
}

NEO4J_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "function_name": {
            "type": "string",
            "enum": list(NEO4J_FUNCTIONS.keys()),
            "description": "The Neo4j function to call"
        },
        "parameters": {
            "type": "object",
            "description": "Parameters to pass to the function"
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence in function selection"
        },
        "reasoning": {
            "type": "string",
            "description": "Why this function was chosen"
        }
    },
    "required": ["function_name", "parameters", "confidence"]
}

NEO4J_SYSTEM_PROMPT = """You are a Neo4j function selector for a Magdeburg mobility assistant.

Your role is to analyze user intent and select the appropriate Neo4j function to call.
You do NOT generate Cypher queries - you select from pre-built, tested functions.

## AVAILABLE FUNCTIONS

{functions_list}

## YOUR TASK

Given:
1. User's query
2. Router analysis (intent, entities, etc.)

Output a JSON object specifying:
1. Which function to call
2. What parameters to pass
3. Your confidence (0.0-1.0)
4. Brief reasoning

## PARAMETER EXTRACTION RULES

1. **Building Names**:
   - Normalize: "building 3" → "Building 03", "bldg 5" → "Building 05"
   - Common names: "mensa", "library", "tower" (pass as-is)

2. **Place Types**:
   - Valid types: "Restaurant", "Cafe", "Bar", "all"
   - Normalize: "restaurant" → "Restaurant", "cafe" → "Cafe"

3. **Distances**:
   - Default radius: 500m for buildings, 1000m for POIs
   - Extract from query: "within 200m" → 200

4. **Missing Parameters**:
   - Use sensible defaults from function definitions
   - If critical parameter missing, set confidence < 0.7

## CHOOSING BETWEEN get_building_info AND find_any_location

Use **get_building_info** when:
- User explicitly says "building" (e.g., "Building 29", "Building 03")
- Query is clearly about a specific campus building you know exists
- User references building by number

Use **find_any_location** when:
- You don't know what type of location it is
- User just asks "where is X?" without specifying building
- Could be a transit stop (e.g., "Reform", "Hasselbachplatz", "Universitätsplatz")
- Could be a POI/restaurant (e.g., "Starbucks", "pizza place")
- Could be a landmark (e.g., "tower", "cathedral")
- Location name sounds like it could be a stop or landmark
- **When in doubt, use find_any_location - it searches everything!**

Examples:
- "Where is Reform?" → find_any_location (unknown type, likely a stop)
- "Where is the mensa?" → find_any_location (could be building or POI)
- "Where is Hasselbachplatz?" → find_any_location (likely a stop or square)
- "Where is Building 29?" → get_building_info (explicitly a building)
- "Where is the computer science building?" → get_building_info (clearly a building)

## DECISION LOGIC

**General location queries** → find_any_location (searches everything!)
- "Where is X?" → find_any_location(search_term="X")
- "Find X" → find_any_location(search_term="X")
- "Locate X" → find_any_location(search_term="X")

**Specific building queries** → get_building_info
- "Where is Building 03?" → get_building_info(building_id="Building 03")
- "Tell me about Building 29" → get_building_info(building_id="Building 29")

**Nearby queries** → get_nearby_buildings or find_places_near_building
- "Buildings near X" → get_nearby_buildings(building_id="X")
- "Which buildings are close to X?" → get_nearby_buildings(building_id="X")
- "Restaurants near X" → find_places_near_building(building_id="X", place_type="Restaurant")
- "Turkish restaurant near X" → find_places_near_building(building_id="X", place_type="Restaurant", cuisine="turkish")
- "Italian food near X" → find_places_near_building(building_id="X", place_type="Restaurant", cuisine="italian")

**Transit queries** → get_nearest_tram_from_building
- "Nearest stop to X" → get_nearest_tram_from_building(building_id="X")

**Routing/directions queries** → get_multimodal_route (PREFERRED for most routing!)
- "How do I get from X to Y?" → get_multimodal_route(origin="X", destination="Y")
- "Route from X to Y" → get_multimodal_route(origin="X", destination="Y")
- "Directions from X to Y" → get_multimodal_route(origin="X", destination="Y")
- USE THIS when origin or destination could be a transit stop (Hauptbahnhof, Reform, Hasselbachplatz, etc.)

**Walking between buildings ONLY** → get_directions_between_buildings
- ONLY use when you are 100% CERTAIN both locations are campus buildings
- "Walk from Building 03 to Building 05" → get_directions_between_buildings
- "Walking from library to mensa" → get_directions_between_buildings (both are buildings)

## POI & STOP DETAIL QUERIES

**Detailed POI info** → get_poi_info
- "Tell me about Izgaram" → get_poi_info(poi_name="Izgaram")
- "What cuisine does Döner King have?" → get_poi_info(poi_name="Döner King")
- "Opening hours of Starbucks" → get_poi_info(poi_name="Starbucks")
- Use when user wants DETAILS about a specific restaurant/cafe/shop

**Detailed stop info** → get_stop_info
- "Tell me about Reform stop" → get_stop_info(stop_name="Reform")
- "What lines serve Hauptbahnhof?" → get_stop_info(stop_name="Magdeburg Hauptbahnhof")
- Use when user wants details or lines for a specific transit stop

## TRANSIT LINE QUERIES

**Specific line info** → get_line_info or get_line_route
- "What stops does Line 1 have?" → get_line_info(line_name="Line 1")
- "Full route of Line 9" → get_line_route(line_name="Line 9")
- "Where does Line 2 go?" → get_line_route(line_name="Line 2")

**List all lines** → get_all_lines
- "What tram lines are there?" → get_all_lines()
- "How many tram lines exist?" → get_all_lines()

**Transfer hubs** → find_transfer_hubs
- "Where can I transfer between lines?" → find_transfer_hubs()
- "Main transfer stops" → find_transfer_hubs(min_lines=3)

## PROXIMITY & ACCESSIBILITY QUERIES

**Is X near Y?** → check_proximity
- "Is mensa near Building 03?" → check_proximity(location1="mensa", location2="Building 03")
- "Are Building 05 and 06 close?" → check_proximity(location1="Building 05", location2="Building 06")

**Accessible routes** → get_accessible_route
- "Wheelchair route from X to Y" → get_accessible_route(from_building="X", to_building="Y")
- "Accessible path from library to mensa" → get_accessible_route(from_building="library", to_building="mensa")

**Walking connections between stops** → get_walking_connections
- "What stops can I walk to from Hauptbahnhof?" → get_walking_connections(stop_name="Magdeburg Hauptbahnhof")
- "Walkable stops from Reform" → get_walking_connections(stop_name="Reform")

## SPATIAL & INFRASTRUCTURE QUERIES

**Spatial relations** → get_building_spatial_relations
- "What faces Building 06?" → get_building_spatial_relations(building_name="Building 06")
- "What buildings are connected internally?" → get_building_spatial_relations(building_name=...)
- "Which buildings look similar?" → get_building_spatial_relations(building_name=...) — BUT prefer find_building_by_function(query="alike") for general search

**Landmarks at a building** → get_building_landmarks
- "What landmarks are near Building 01?" → get_building_landmarks(building_name="Building 01")
- "What can I see from the tower?" → get_building_landmarks(building_name="Campus Tower")

**Infrastructure** → get_building_infrastructure
- "Does Building 03 have cooling?" → get_building_infrastructure(building_name="Building 03")
- "Which building cools Building 01?" → get_building_infrastructure(building_name="Building 01")

**Area info** → get_area_info
- "Tell me about the main plaza" → get_area_info(area_name="University Main Plaza")
- "What buildings are around Pfälzer Platz?" → get_area_info(area_name="Pfälzer Platz")

## BUILDING PROPERTY SEARCH QUERIES - IMPORTANT!

**Search buildings by ANY property** → find_building_by_function
- "Which buildings look alike?" → find_building_by_function(query="alike")
- "Which buildings are similar?" → find_building_by_function(query="alike")
- "Find computer science buildings" → find_building_by_function(query="computer science")
- "Buildings with labs" → find_building_by_function(query="lab")
- This searches ALL properties on building nodes dynamically (name, function, notes, etc.)
- Building similarity info is stored in the "note" property (e.g., "Looks alike Building 24")

## SENSOR QUERIES - IMPORTANT!

**Count ALL sensors** → list_all_sensors
- "How many sensors are there?" → list_all_sensors()
- "What sensors do you have?" → list_all_sensors()
- "List all sensors" → list_all_sensors()
- Use this when user doesn't specify a type and wants to see ALL sensors

**List all sensors of a type** → list_sensors_by_type
- "Where are the weather sensors?" → list_sensors_by_type(sensor_type="Weather")
- "Show me all parking sensors" → list_sensors_by_type(sensor_type="Parking")
- "What traffic sensors do you have?" → list_sensors_by_type(sensor_type="Traffic")
- "List air quality sensors" → list_sensors_by_type(sensor_type="AirQuality")
- "How many weather sensors?" → list_sensors_by_type(sensor_type="Weather")
- Valid types: Weather, Parking, Traffic, AirQuality

**Single sensor near a building** → get_sensor_near_building
- "Is there A weather sensor near Building 03?" → get_sensor_near_building(building_id="Building 03", sensor_type="Weather")
- Use when user asks about "a sensor" (singular) or "the nearest sensor"

**ALL sensors near a building** → get_all_sensors_near_building (PREFERRED!)
- "What sensors are near Building 80?" → get_all_sensors_near_building(building_id="Building 80")
- "Show me all sensors near mensa" → get_all_sensors_near_building(building_id="mensa")
- "Any sensors nearby?" → get_all_sensors_near_building(building_id=...)
- Use when user asks about "sensors" (plural), "all sensors", or "what sensors"
- **PREFER this function for general sensor queries!**

**Sensor at coordinates** → get_nearest_sensor
- "Find sensor at 52.139, 11.645" → get_nearest_sensor(latitude=52.139, longitude=11.645)
- Use when coordinates are provided

## OUTPUT FORMAT

You must output ONLY valid JSON matching the schema. No explanations, no markdown.

Example:
```json
{
  "function_name": "find_any_location",
  "parameters": {
    "search_term": "Reform",
    "limit": 5
  },
  "confidence": 0.95,
  "reasoning": "General location query - unknown type, use universal search"
}
```

## CONFIDENCE GUIDELINES

- **0.9-1.0**: Perfect match, all parameters clear
- **0.7-0.89**: Good match, some parameter assumptions
- **0.5-0.69**: Uncertain, missing critical info
- **<0.5**: Cannot determine correct function

Always prioritize the most specific function that matches the query.
"""

NEO4J_FEW_SHOT_EXAMPLES = [
    {
        "user_query": "Where is Building 03?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {"building_name": "Building 03"}
        },
        "expected_output": {
            "function_name": "get_building_info",
            "parameters": {
                "building_id": "Building 03"
            },
            "confidence": 0.98,
            "reasoning": "Direct building lookup query with explicit building number"
        }
    },
    {
        "user_query": "Where is Reform?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "Reform",
                "poi_name": "Reform"
            }
        },
        "expected_output": {
            "function_name": "find_any_location",
            "parameters": {
                "search_term": "Reform",
                "limit": 5
            },
            "confidence": 0.95,
            "reasoning": "General location query - unknown type, likely a stop. Use universal search."
        }
    },
    {
        "user_query": "Where is the mensa?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "mensa",
                "poi_name": "mensa"
            }
        },
        "expected_output": {
            "function_name": "find_any_location",
            "parameters": {
                "search_term": "mensa",
                "limit": 5
            },
            "confidence": 0.92,
            "reasoning": "Mensa could be a building or POI - use universal search to find all matches"
        }
    },
    {
        "user_query": "Where is Hasselbachplatz?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "destination": "Hasselbachplatz",
                "location": "Hasselbachplatz"
            }
        },
        "expected_output": {
            "function_name": "find_any_location",
            "parameters": {
                "search_term": "Hasselbachplatz",
                "limit": 3
            },
            "confidence": 0.90,
            "reasoning": "Unknown location type - could be stop, landmark, or square. Use universal search."
        }
    },
    {
        "user_query": "What can I eat at Izgaram?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "Izgaram",
                "poi_name": "Izgaram"
            }
        },
        "expected_output": {
            "function_name": "find_any_location",
            "parameters": {
                "search_term": "Izgaram",
                "limit": 1
            },
            "confidence": 0.92,
            "reasoning": "User asking about food/cuisine at a restaurant - find the POI to get its cuisine property"
        }
    },
    {
        "user_query": "What food does Döner King serve?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "Döner King",
                "poi_name": "Döner King"
            }
        },
        "expected_output": {
            "function_name": "find_any_location",
            "parameters": {
                "search_term": "Döner King",
                "limit": 1
            },
            "confidence": 0.92,
            "reasoning": "User asking about cuisine type - find the POI to get its cuisine property"
        }
    },
    {
        "user_query": "Find the campus tower",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "campus tower",
                "building_name": "tower"
            }
        },
        "expected_output": {
            "function_name": "find_any_location",
            "parameters": {
                "search_term": "tower",
                "limit": 3
            },
            "confidence": 0.88,
            "reasoning": "Tower could be a building or landmark - use universal search"
        }
    },
    {
        "user_query": "Is there an Italian restaurant near Building 05?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "building_name": "Building 05",
                "poi_name": "restaurant",
                "location": "Building 05"
            }
        },
        "expected_output": {
            "function_name": "find_places_near_building",
            "parameters": {
                "building_id": "Building 05",
                "place_type": "Restaurant",
                "cuisine": "Italian",
                "radius_meters": 1000,
                "limit": 5
            },
            "confidence": 0.95,
            "reasoning": "POI search near building with cuisine filter"
        }
    },
    {
        "user_query": "Find cafes near the library",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "poi_name": "cafe",
                "location": "library"
            }
        },
        "expected_output": {
            "function_name": "find_places_near_building",
            "parameters": {
                "building_id": "library",
                "place_type": "Cafe",
                "radius_meters": 1000,
                "limit": 5
            },
            "confidence": 0.92,
            "reasoning": "Cafe search near library building"
        }
    },
    {
        "user_query": "What buildings are within 200 meters of the mensa?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {"location": "mensa"}
        },
        "expected_output": {
            "function_name": "get_nearby_buildings",
            "parameters": {
                "building_id": "mensa"
            },
            "confidence": 0.90,
            "reasoning": "Buildings near mensa - use get_nearby_buildings with building_id"
        }
    },
    {
        "user_query": "Nearest tram stop to Building 03",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {"building_name": "Building 03"}
        },
        "expected_output": {
            "function_name": "get_nearest_tram_from_building",
            "parameters": {
                "building_id": "Building 03"
            },
            "confidence": 0.95,
            "reasoning": "Finding nearest transit stop"
        }
    },
    {
        "user_query": "How do I walk from Building 03 to the mensa?",
        "router_output": {
            "primary_intent": "get_route",
            "entities": {
                "origin": "Building 03",
                "destination": "mensa"
            }
        },
        "expected_output": {
            "function_name": "get_directions_between_buildings",
            "parameters": {
                "from_building": "Building 03",
                "to_building": "mensa"
            },
            "confidence": 0.93,
            "reasoning": "Walking directions between campus buildings"
        }
    },
    {
        "user_query": "Where is the tower?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {"poi_name": "tower", "location": "tower"}
        },
        "expected_output": {
            "function_name": "find_any_location",
            "parameters": {
                "search_term": "tower",
                "limit": 3
            },
            "confidence": 0.88,
            "reasoning": "Tower could be building or landmark - use universal search"
        }
    },
    {
        "user_query": "How do I get from Hauptbahnhof to Building 03?",
        "router_output": {
            "primary_intent": "get_route",
            "entities": {
                "origin": "Hauptbahnhof",
                "destination": "Building 03",
                "building_name": "Building 03"
            }
        },
        "expected_output": {
            "function_name": "get_multimodal_route",
            "parameters": {
                "origin": "Hauptbahnhof",
                "destination": "Building 03"
            },
            "confidence": 0.92,
            "reasoning": "Hauptbahnhof is a transit stop, not a building - use multimodal routing"
        }
    },
    {
        "user_query": "Route from Reform to the library",
        "router_output": {
            "primary_intent": "get_route",
            "entities": {
                "origin": "Reform",
                "destination": "library"
            }
        },
        "expected_output": {
            "function_name": "get_multimodal_route",
            "parameters": {
                "origin": "Reform",
                "destination": "library"
            },
            "confidence": 0.90,
            "reasoning": "Reform is likely a transit stop - use multimodal routing for mixed location types"
        }
    },
    {
        "user_query": "Where are the weather sensors?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "weather sensors",
                "poi_name": "weather sensors"
            }
        },
        "expected_output": {
            "function_name": "list_sensors_by_type",
            "parameters": {
                "sensor_type": "Weather"
            },
            "confidence": 0.95,
            "reasoning": "User wants to list ALL weather sensors - use list_sensors_by_type to get all of them"
        }
    },
    {
        "user_query": "Show me all parking sensors",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "parking sensors"
            }
        },
        "expected_output": {
            "function_name": "list_sensors_by_type",
            "parameters": {
                "sensor_type": "Parking"
            },
            "confidence": 0.95,
            "reasoning": "User wants a list of all parking sensors"
        }
    },
    {
        "user_query": "What traffic sensors do you have?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "traffic sensors"
            }
        },
        "expected_output": {
            "function_name": "list_sensors_by_type",
            "parameters": {
                "sensor_type": "Traffic"
            },
            "confidence": 0.95,
            "reasoning": "User is asking about available traffic sensors - list them all"
        }
    },
    {
        "user_query": "Is there a weather sensor near Building 03?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "building_name": "Building 03",
                "location": "Building 03"
            }
        },
        "expected_output": {
            "function_name": "get_sensor_near_building",
            "parameters": {
                "building_id": "Building 03",
                "sensor_type": "Weather"
            },
            "confidence": 0.93,
            "reasoning": "User wants the nearest weather sensor to a specific building"
        }
    },
    {
        "user_query": "What sensors are near Building 80?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "building_name": "Building 80",
                "location": "Building 80"
            }
        },
        "expected_output": {
            "function_name": "get_all_sensors_near_building",
            "parameters": {
                "building_id": "Building 80"
            },
            "confidence": 0.95,
            "reasoning": "User asks about 'sensors' (plural) - return ALL sensors near the building"
        }
    },
    {
        "user_query": "Show me all sensors near the mensa",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "mensa"
            }
        },
        "expected_output": {
            "function_name": "get_all_sensors_near_building",
            "parameters": {
                "building_id": "mensa"
            },
            "confidence": 0.95,
            "reasoning": "User wants ALL sensors near mensa, not just one"
        }
    },
    {
        "user_query": "Find parking sensor near the mensa",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "mensa"
            }
        },
        "expected_output": {
            "function_name": "get_sensor_near_building",
            "parameters": {
                "building_id": "mensa",
                "sensor_type": "Parking"
            },
            "confidence": 0.92,
            "reasoning": "User wants nearest parking sensor to mensa building"
        }
    },
    {
        "user_query": "Which buildings look alike?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "similar buildings",
                "poi_name": "alike"
            }
        },
        "expected_output": {
            "function_name": "find_building_by_function",
            "parameters": {
                "query": "alike"
            },
            "confidence": 0.92,
            "reasoning": "User wants to find buildings with 'alike' in their properties - use dynamic property search"
        }
    },
    {
        "user_query": "Which 2 buildings are similar?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "similar buildings",
                "poi_name": "similar"
            }
        },
        "expected_output": {
            "function_name": "find_building_by_function",
            "parameters": {
                "query": "alike"
            },
            "confidence": 0.90,
            "reasoning": "User wants similar buildings - search for 'alike' which is stored in building notes"
        }
    },
    {
        "user_query": "How many sensors are there?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "sensors",
                "poi_name": "sensors"
            }
        },
        "expected_output": {
            "function_name": "list_all_sensors",
            "parameters": {},
            "confidence": 0.95,
            "reasoning": "User wants to know the total count of all sensors - use list_all_sensors to get counts by type"
        }
    },
    {
        "user_query": "What sensors do you have?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "sensors"
            }
        },
        "expected_output": {
            "function_name": "list_all_sensors",
            "parameters": {},
            "confidence": 0.95,
            "reasoning": "User wants to see all available sensors - list_all_sensors returns all sensors with counts"
        }
    },
    {
        "user_query": "How many weather sensors do you have?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "weather sensors",
                "poi_name": "weather sensors"
            }
        },
        "expected_output": {
            "function_name": "list_sensors_by_type",
            "parameters": {
                "sensor_type": "Weather"
            },
            "confidence": 0.95,
            "reasoning": "User asks specifically about weather sensors - use list_sensors_by_type with Weather type"
        }
    },
    {
        "user_query": "Tell me about Izgaram restaurant",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "poi_name": "Izgaram",
                "location": "Izgaram"
            }
        },
        "expected_output": {
            "function_name": "get_poi_info",
            "parameters": {
                "poi_name": "Izgaram"
            },
            "confidence": 0.95,
            "reasoning": "User wants detailed info about a specific POI - use get_poi_info for full details"
        }
    },
    {
        "user_query": "What lines serve Reform stop?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "Reform"
            }
        },
        "expected_output": {
            "function_name": "get_stop_info",
            "parameters": {
                "stop_name": "Reform"
            },
            "confidence": 0.93,
            "reasoning": "User wants to know which lines serve a specific stop - get_stop_info returns line info"
        }
    },
    {
        "user_query": "What tram lines are there?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "tram lines"
            }
        },
        "expected_output": {
            "function_name": "get_all_lines",
            "parameters": {},
            "confidence": 0.95,
            "reasoning": "User wants to see all available tram/bus lines"
        }
    },
    {
        "user_query": "What stops does Line 1 have?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "Line 1"
            }
        },
        "expected_output": {
            "function_name": "get_line_route",
            "parameters": {
                "line_name": "Line 1",
                "direction": "both"
            },
            "confidence": 0.95,
            "reasoning": "User wants the full route of a specific line - use get_line_route for ordered stops"
        }
    },
    {
        "user_query": "Is the mensa near Building 03?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "mensa",
                "building_name": "Building 03"
            }
        },
        "expected_output": {
            "function_name": "check_proximity",
            "parameters": {
                "location1": "mensa",
                "location2": "Building 03"
            },
            "confidence": 0.93,
            "reasoning": "User is asking whether two locations are near each other - use check_proximity"
        }
    },
    {
        "user_query": "Is there a wheelchair accessible route from library to mensa?",
        "router_output": {
            "primary_intent": "get_route",
            "entities": {
                "origin": "library",
                "destination": "mensa"
            }
        },
        "expected_output": {
            "function_name": "get_accessible_route",
            "parameters": {
                "from_building": "library",
                "to_building": "mensa"
            },
            "confidence": 0.95,
            "reasoning": "User explicitly asks about wheelchair/accessible route - use get_accessible_route"
        }
    },
    {
        "user_query": "What stops can I walk to from Hauptbahnhof?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "Hauptbahnhof"
            }
        },
        "expected_output": {
            "function_name": "get_walking_connections",
            "parameters": {
                "stop_name": "Magdeburg Hauptbahnhof",
                "max_walk_time": 10
            },
            "confidence": 0.93,
            "reasoning": "User wants to know walkable stops from a transit stop"
        }
    },
    {
        "user_query": "What area does Building 06 face?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "building_name": "Building 06"
            }
        },
        "expected_output": {
            "function_name": "get_building_spatial_relations",
            "parameters": {
                "building_name": "Building 06"
            },
            "confidence": 0.92,
            "reasoning": "User asks about spatial relations (facing) - use get_building_spatial_relations"
        }
    },
    {
        "user_query": "Are there any landmarks near Building 01?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "building_name": "Building 01"
            }
        },
        "expected_output": {
            "function_name": "get_building_landmarks",
            "parameters": {
                "building_name": "Building 01"
            },
            "confidence": 0.92,
            "reasoning": "User asking about landmarks at/near a specific building"
        }
    },
    {
        "user_query": "Tell me about the University Main Plaza",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "University Main Plaza"
            }
        },
        "expected_output": {
            "function_name": "get_area_info",
            "parameters": {
                "area_name": "University Main Plaza"
            },
            "confidence": 0.93,
            "reasoning": "User asking about a campus area/plaza - use get_area_info"
        }
    },
    {
        "user_query": "Where can I transfer between tram lines?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "transfer"
            }
        },
        "expected_output": {
            "function_name": "find_transfer_hubs",
            "parameters": {
                "min_lines": 2,
                "limit": 10
            },
            "confidence": 0.93,
            "reasoning": "User wants to find stops where they can transfer between lines"
        }
    },
    {
        "user_query": "Does Building 03 have cooling?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "building_name": "Building 03"
            }
        },
        "expected_output": {
            "function_name": "get_building_infrastructure",
            "parameters": {
                "building_name": "Building 03"
            },
            "confidence": 0.90,
            "reasoning": "User asking about building infrastructure/cooling systems"
        }
    },
    {
        "user_query": "How many dorms are there on campus?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "dorm",
                "poi_name": "dorm"
            }
        },
        "expected_output": {
            "function_name": "find_building_by_function",
            "parameters": {
                "query": "dormitory"
            },
            "confidence": 0.92,
            "reasoning": "User wants to find dormitory buildings - search building properties (function, note) for 'dormitory'. Note field contains housing prices, room types, and unit counts."
        }
    },
    {
        "user_query": "Compare dorm prices",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "dormitory",
                "poi_name": "dormitory"
            }
        },
        "expected_output": {
            "function_name": "find_building_by_function",
            "parameters": {
                "query": "dormitory"
            },
            "confidence": 0.92,
            "reasoning": "User wants dormitory pricing - search for dormitories, pricing data is in the 'note' property"
        }
    },
    {
        "user_query": "What student accommodation is available?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {
                "location": "accommodation",
                "poi_name": "accommodation"
            }
        },
        "expected_output": {
            "function_name": "find_building_by_function",
            "parameters": {
                "query": "student accommodation"
            },
            "confidence": 0.90,
            "reasoning": "User wants student housing info - building function field contains 'Student accommodation'"
        }
    },
    {
        "user_query": "What's the mensa menu today?",
        "router_output": {
            "primary_intent": "get_location_info",
            "entities": {"location": "Mensa", "poi_name": "Mensa"}
        },
        "expected_output": {
            "function_name": "get_building_info",
            "parameters": {
                "building_id": "Mensa"
            },
            "confidence": 0.95,
            "reasoning": "Mensa is a campus building - use get_building_info to get full building data including linked services"
        }
    }
]


def build_neo4j_prompt(
    user_query: str,
    router_output: Dict[str, Any],
    conversation_context: list[Dict[str, str]] = None
) -> list[Dict[str, str]]:
    import json

    functions_list = []
    for func_name, func_info in NEO4J_FUNCTIONS.items():
        params_str = ", ".join([f"{k}: {v}" for k, v in func_info["parameters"].items()])
        functions_list.append(
            f"**{func_name}**\n"
            f"  Description: {func_info['description']}\n"
            f"  Parameters: {params_str}"
        )

    system_prompt = NEO4J_SYSTEM_PROMPT.replace(
        "{functions_list}", "\n\n".join(functions_list)
    )

    if conversation_context:
        system_prompt += """

## CONVERSATION CONTEXT - USE FOR MULTI-TURN QUERIES

You have access to the conversation history. Use it to:
1. **Resolve references**: "What Greek options do I have?" after discussing Turkish restaurants → find_places_by_cuisine(cuisine="greek")
2. **Maintain context**: "What other sensors are there?" after discussing Building 80 → get_all_sensors_near_building(building_id="Building 80")
3. **Infer missing parameters**: "Any cafes nearby?" after discussing library → find_places_near_building(building_id="library", place_type="Cafe")

### CRITICAL:
- Extract location/building references from conversation history when current query is vague
- If user says "nearby", "there", "that building" - look at previous context
- Use HIGH confidence when context makes the query clear
"""

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    for example in NEO4J_FEW_SHOT_EXAMPLES:
        user_msg = f"Query: {example['user_query']}\n\nRouter Output:\n{json.dumps(example['router_output'], indent=2)}"
        messages.append({"role": "user", "content": user_msg})

        messages.append({
            "role": "assistant",
            "content": json.dumps(example['expected_output'], indent=2)
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
            "content": "--- END OF CONVERSATION HISTORY ---\n\nNow select the function for the following query with the above context in mind:"
        })

    actual_msg = f"Query: {user_query}\n\nRouter Output:\n{json.dumps(router_output, indent=2)}"
    messages.append({"role": "user", "content": actual_msg})

    return messages


def validate_neo4j_output(output: Dict[str, Any]) -> tuple[bool, str]:
    if "function_name" not in output:
        return False, "Missing function_name"

    if "parameters" not in output:
        return False, "Missing parameters"

    if "confidence" not in output:
        return False, "Missing confidence"

    if output["function_name"] not in NEO4J_FUNCTIONS:
        return False, f"Invalid function_name: {output['function_name']}"

    if not isinstance(output["parameters"], dict):
        return False, "parameters must be a dictionary"

    if not isinstance(output["confidence"], (int, float)):
        return False, "confidence must be a number"

    if not 0.0 <= output["confidence"] <= 1.0:
        return False, "confidence must be between 0.0 and 1.0"

    return True, "Valid"
