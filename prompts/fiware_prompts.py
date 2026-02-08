"""
Prompt templates for the FIWARE Agent. Contains system prompts for sensor data parameter extraction.
"""

from typing import Dict, Any

FIWARE_ENTITY_TYPES = {
    "Weather": {
        "description": "Weather sensor data (temperature, humidity, pressure, etc.)",
        "common_attributes": [
            "temperature", "humidity", "barometricPressure",
            "windSpeed", "windDirection", "cumulativeRainfall", "rainIntensity",
            "lightIntensity", "lightUV"
        ],
        "sensor_ids": [
            "Sensor:Weather:WelcomeCenter", "Sensor:Weather:UniMensa", "Sensor:Weather:Library",
            "Sensor:Weather:ScienceHub", "Sensor:Weather:FacultyCS", "Sensor:Weather:NorthPark",
            "Sensor:Weather:GeschwisterPark", "Sensor:Weather:Walter", "Sensor:Weather:Winfred"
        ],
        "id_pattern": "Sensor:Weather:*",
        "examples": [
            "What's the weather?",
            "Temperature at FacultyCS",
            "Is it raining?",
            "What's the humidity?"
        ]
    },
    "Parking": {
        "description": "Parking lot availability and status",
        "common_attributes": [
            "freeSpaces", "totalSpaces"
        ],
        "sensor_ids": [
            "ParkingSpot:ScienceHarbor", "ParkingSpot:FacultyCS", "ParkingSpot:NorthPark"
        ],
        "id_pattern": "ParkingSpot:*",
        "examples": [
            "Is there parking available?",
            "Parking near the library",
            "How many spots available?"
        ]
    },
    "AirQuality": {
        "description": "Air quality measurements",
        "common_attributes": [
            "no2", "o3", "pm10", "pm25"
        ],
        "sensor_ids": [
            "Air:Schleinufer", "Air:GuerickeStrasse", "Air:West", "Air:CityTunnel"
        ],
        "id_pattern": "Air:*",
        "examples": [
            "Air quality at campus",
            "Pollution levels",
            "PM2.5 levels"
        ]
    },
    "Traffic": {
        "description": "Traffic flow and speed data at junctions",
        "common_attributes": [
            "avgSpeed", "cyclists", "pedestrians", "vehiclesIn", "vehiclesOut", "timestamp"
        ],
        "sensor_ids": [
            "Traffic:Junction:ScienceHub", "Traffic:Junction:FacultyCS"
        ],
        "id_pattern": "Traffic:Junction:*",
        "examples": [
            "Traffic conditions",
            "How many cyclists?"
        ]
    },
    "Room": {
        "description": "Indoor room sensor data (temperature, pressure)",
        "common_attributes": [
            "temperature", "pressure"
        ],
        "sensor_ids": [
            "Room0", "Room1", "Room2", "Room3", "Mens"
        ],
        "id_pattern": "Room*",
        "examples": [
            "Room temperature",
            "Room pressure"
        ]
    },
    "Vehicle": {
        "description": "Vehicle and robot tracking data",
        "common_attributes": [
            "location", "category", "source"
        ],
        "sensor_ids": [
            "DeliveryRobot", "Vehicles:*"
        ],
        "id_pattern": "Vehicles:*",
        "examples": [
            "Where is the delivery robot?",
            "Vehicle locations"
        ]
    },
    "POI": {
        "description": "Points of Interest",
        "common_attributes": [
            "name", "category", "subCategory", "location", "accessibility"
        ],
        "sensor_ids": [
            "POI:VisionHub"
        ],
        "id_pattern": "POI:*",
        "examples": [
            "Points of interest nearby"
        ]
    }
}

FIWARE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_type": {
            "type": "string",
            "enum": ["Weather", "Parking", "AirQuality", "Traffic", "Room", "Vehicle", "POI"],
            "description": "FIWARE entity type to query"
        },
        "entity_id": {
            "type": ["string", "null"],
            "description": "Specific entity ID (if known)"
        },
        "id_pattern": {
            "type": ["string", "null"],
            "description": "Regex pattern for entity IDs"
        },
        "query_filter": {
            "type": ["string", "null"],
            "description": "NGSIv2 q filter (e.g., 'temperature>20')"
        },
        "attributes": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "Specific attributes to retrieve"
        },
        "location_filter": {
            "type": ["object", "null"],
            "properties": {
                "georel": {"type": "string"},
                "geometry": {"type": "string"},
                "coords": {"type": "string"}
            },
            "description": "Geographic filter (if location-based)"
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "description": "Max results to return"
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence in parameter extraction"
        },
        "reasoning": {
            "type": "string",
            "description": "Why these parameters were chosen"
        }
    },
    "required": ["entity_type", "limit", "confidence"]
}

FIWARE_SYSTEM_PROMPT = """You are a FIWARE parameter extraction agent for a Magdeburg mobility assistant.

Your role is to analyze user queries about real-time sensor data and extract parameters
for querying the FIWARE Context Broker API (NGSIv2).

## AVAILABLE ENTITY TYPES

{entity_types_list}

## YOUR TASK

Given:
1. User's query
2. Router analysis (intent, entities, etc.)

Output a JSON object with:
1. Which FIWARE entity type to query
2. Optional filters (entity ID, patterns, query_filter string)
3. Which attributes to retrieve (or null for all)
4. Confidence score (0.0-1.0)
5. Brief reasoning

## ENTITY IDS (IMPORTANT!)

The actual entity IDs in the system follow these patterns:
- Weather sensors: "Sensor:Weather:FacultyCS", "Sensor:Weather:Library", "Sensor:Weather:WelcomeCenter", etc.
- Parking: "ParkingSpot:ScienceHarbor", "ParkingSpot:FacultyCS", "ParkingSpot:NorthPark"
- Air Quality: "Air:Schleinufer", "Air:GuerickeStrasse", "Air:West", "Air:CityTunnel"
- Traffic: "Traffic:Junction:ScienceHub", "Traffic:Junction:FacultyCS"
- Rooms: "Room0", "Room1", "Room2", "Room3", "Mens"
- Vehicles: "DeliveryRobot", "Vehicles:*"
- POI: "POI:VisionHub"

## ATTRIBUTE NAMES (IMPORTANT!)

Use exact attribute names from the API:
- Weather: temperature, humidity (NOT relativeHumidity), barometricPressure, windSpeed, windDirection, cumulativeRainfall, rainIntensity
- Parking: freeSpaces, totalSpaces (NOT availableSpotNumber)
- AirQuality: no2, o3, pm10, pm25
- Traffic: avgSpeed, cyclists, pedestrians, vehiclesIn, vehiclesOut
- Room: temperature, pressure

## QUERY FILTER FORMAT (CRITICAL!)

The query_filter must be a STRING using NGSIv2 Simple Query Language:
- Comparison: "humidity<80", "temperature>20", "freeSpaces==0"
- Multiple conditions: "humidity>=60;humidity<=80" (use semicolon)
- NOT a dict/object! Always a plain string or null.

Examples:
- "humidity<80" ✓
- "temperature>25" ✓
- "freeSpaces>0" ✓
- "humidity>=60;humidity<=80" ✓
- {"humidity": {"lt": 80}} ✗ WRONG!

## PARAMETER EXTRACTION RULES

1. **Entity Type Selection**:
   - Weather/temperature/humidity → Weather
   - Parking → Parking
   - Air quality/pollution → AirQuality
   - Traffic → Traffic
   - Room/indoor → Room
   - Vehicle/robot → Vehicle

2. **Entity ID**:
   - For specific location like "FacultyCS", use entity_id: "Sensor:Weather:FacultyCS"
   - For "Welcome Center", use entity_id: "Sensor:Weather:WelcomeCenter"
   - For parking at "FacultyCS", use entity_id: "ParkingSpot:FacultyCS"

3. **Limits**:
   - Default: 10 for most queries
   - Increase to 20 if user asks for "all" or comparison across locations

## COMMON QUERY PATTERNS

**Weather Queries**:
- "What's the weather?" → Weather, limit=10
- "Temperature at FacultyCS?" → Weather, entity_id="Sensor:Weather:FacultyCS", attrs=["temperature"]
- "What's the humidity?" → Weather, attrs=["humidity"], limit=10
- "Places with humidity below 80" → Weather, query_filter="humidity<80", attrs=["humidity"], limit=20

**Parking Queries**:
- "Is there parking?" → Parking, attrs=["freeSpaces","totalSpaces"], limit=5
- "Parking at FacultyCS" → Parking, entity_id="ParkingSpot:FacultyCS"
- "Parking with free spaces" → Parking, query_filter="freeSpaces>0"

**Air Quality Queries**:
- "Air quality?" → AirQuality, limit=5
- "PM2.5 levels" → AirQuality, attrs=["pm25"]

## OUTPUT FORMAT

You must output ONLY valid JSON. No explanations, no markdown.

Example:
```json
{
  "entity_type": "Weather",
  "entity_id": null,
  "id_pattern": null,
  "query_filter": "humidity<80",
  "attributes": ["humidity", "temperature"],
  "location_filter": null,
  "limit": 20,
  "confidence": 0.95,
  "reasoning": "User asked for places with humidity below 80%"
}
```

## CONFIDENCE GUIDELINES

- **0.9-1.0**: Clear sensor query with known entity type
- **0.7-0.89**: Good match, some assumptions made
- **0.5-0.69**: Uncertain about entity type or parameters
- **<0.5**: Query doesn't match any sensor type

Always prioritize the most recent real-time data.
"""

FIWARE_FEW_SHOT_EXAMPLES = [
    {
        "user_query": "What's the weather?",
        "router_output": {
            "primary_intent": "get_weather",
            "entities": {}
        },
        "expected_output": {
            "entity_type": "Weather",
            "entity_id": None,
            "id_pattern": None,
            "query_filter": None,
            "attributes": None,
            "location_filter": None,
            "limit": 10,
            "confidence": 0.98,
            "reasoning": "General weather query, get all weather sensors with all attributes"
        }
    },
    {
        "user_query": "What's the humidity?",
        "router_output": {
            "primary_intent": "get_weather",
            "entities": {}
        },
        "expected_output": {
            "entity_type": "Weather",
            "entity_id": None,
            "id_pattern": None,
            "query_filter": None,
            "attributes": ["humidity"],
            "location_filter": None,
            "limit": 10,
            "confidence": 0.96,
            "reasoning": "Humidity query, get humidity from all weather sensors"
        }
    },
    {
        "user_query": "Show me places where humidity is below 80%",
        "router_output": {
            "primary_intent": "get_weather",
            "entities": {}
        },
        "expected_output": {
            "entity_type": "Weather",
            "entity_id": None,
            "id_pattern": None,
            "query_filter": "humidity<80",
            "attributes": ["humidity", "temperature"],
            "location_filter": None,
            "limit": 20,
            "confidence": 0.95,
            "reasoning": "Humidity filter query, using NGSIv2 query string format"
        }
    },
    {
        "user_query": "What's the temperature at FacultyCS?",
        "router_output": {
            "primary_intent": "get_weather",
            "entities": {
                "weather_location": "FacultyCS",
                "building_name": "FacultyCS"
            }
        },
        "expected_output": {
            "entity_type": "Weather",
            "entity_id": "Sensor:Weather:FacultyCS",
            "id_pattern": None,
            "query_filter": None,
            "attributes": ["temperature"],
            "location_filter": None,
            "limit": 1,
            "confidence": 0.95,
            "reasoning": "Temperature query at FacultyCS, using exact sensor ID Sensor:Weather:FacultyCS"
        }
    },
    {
        "user_query": "Weather at Welcome Center",
        "router_output": {
            "primary_intent": "get_weather",
            "entities": {
                "weather_location": "Welcome Center"
            }
        },
        "expected_output": {
            "entity_type": "Weather",
            "entity_id": "Sensor:Weather:WelcomeCenter",
            "id_pattern": None,
            "query_filter": None,
            "attributes": None,
            "location_filter": None,
            "limit": 1,
            "confidence": 0.95,
            "reasoning": "Weather at Welcome Center, using exact sensor ID (note: no space in ID)"
        }
    },
    {
        "user_query": "Is it raining?",
        "router_output": {
            "primary_intent": "get_weather",
            "entities": {}
        },
        "expected_output": {
            "entity_type": "Weather",
            "entity_id": None,
            "id_pattern": None,
            "query_filter": None,
            "attributes": ["rainIntensity", "cumulativeRainfall"],
            "location_filter": None,
            "limit": 10,
            "confidence": 0.96,
            "reasoning": "Precipitation query, check rain intensity and cumulative rainfall"
        }
    },
    {
        "user_query": "Is there parking available?",
        "router_output": {
            "primary_intent": "get_parking_info",
            "entities": {}
        },
        "expected_output": {
            "entity_type": "Parking",
            "entity_id": None,
            "id_pattern": None,
            "query_filter": None,
            "attributes": ["freeSpaces", "totalSpaces"],
            "location_filter": None,
            "limit": 5,
            "confidence": 0.94,
            "reasoning": "Parking availability query, get all parking sensors with freeSpaces and totalSpaces"
        }
    },
    {
        "user_query": "Parking at FacultyCS",
        "router_output": {
            "primary_intent": "get_parking_info",
            "entities": {
                "location": "FacultyCS",
                "building_name": "FacultyCS"
            }
        },
        "expected_output": {
            "entity_type": "Parking",
            "entity_id": "ParkingSpot:FacultyCS",
            "id_pattern": None,
            "query_filter": None,
            "attributes": ["freeSpaces", "totalSpaces"],
            "location_filter": None,
            "limit": 1,
            "confidence": 0.95,
            "reasoning": "Parking at FacultyCS, using exact sensor ID ParkingSpot:FacultyCS"
        }
    },
    {
        "user_query": "Parking with free spaces",
        "router_output": {
            "primary_intent": "get_parking_info",
            "entities": {}
        },
        "expected_output": {
            "entity_type": "Parking",
            "entity_id": None,
            "id_pattern": None,
            "query_filter": "freeSpaces>0",
            "attributes": ["freeSpaces", "totalSpaces"],
            "location_filter": None,
            "limit": 5,
            "confidence": 0.93,
            "reasoning": "Filter parking by available spaces using NGSIv2 query string"
        }
    },
    {
        "user_query": "How's the air quality?",
        "router_output": {
            "primary_intent": "get_air_quality",
            "entities": {}
        },
        "expected_output": {
            "entity_type": "AirQuality",
            "entity_id": None,
            "id_pattern": None,
            "query_filter": None,
            "attributes": ["no2", "o3", "pm10", "pm25"],
            "location_filter": None,
            "limit": 5,
            "confidence": 0.90,
            "reasoning": "Air quality query, get NO2, O3, PM10, PM2.5 from all sensors"
        }
    },
    {
        "user_query": "Traffic conditions",
        "router_output": {
            "primary_intent": "get_traffic",
            "entities": {}
        },
        "expected_output": {
            "entity_type": "Traffic",
            "entity_id": None,
            "id_pattern": None,
            "query_filter": None,
            "attributes": ["avgSpeed", "cyclists", "pedestrians", "vehiclesIn", "vehiclesOut"],
            "location_filter": None,
            "limit": 5,
            "confidence": 0.92,
            "reasoning": "Traffic query, get speed and counts from all traffic junction sensors"
        }
    }
]


def build_fiware_prompt(user_query: str, router_output: Dict[str, Any]) -> list[Dict[str, str]]:
    entity_types_list = []
    for entity_type, info in FIWARE_ENTITY_TYPES.items():
        attrs = ", ".join(info["common_attributes"][:4])
        sensor_ids = ", ".join(info.get("sensor_ids", [])[:3])
        id_pattern = info.get("id_pattern", "")
        entity_types_list.append(
            f"**{entity_type}**: {info['description']}\n"
            f"  Attributes: {attrs}\n"
            f"  Sensor IDs: {sensor_ids}\n"
            f"  ID Pattern: {id_pattern}"
        )

    system_prompt = FIWARE_SYSTEM_PROMPT.replace(
        "{entity_types_list}", "\n\n".join(entity_types_list)
    )

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    import json
    for example in FIWARE_FEW_SHOT_EXAMPLES:
        user_msg = f"Query: {example['user_query']}\n\nRouter Output:\n{json.dumps(example['router_output'], indent=2)}"
        messages.append({"role": "user", "content": user_msg})

        messages.append({
            "role": "assistant",
            "content": json.dumps(example['expected_output'], indent=2)
        })

    actual_msg = f"Query: {user_query}\n\nRouter Output:\n{json.dumps(router_output, indent=2)}"
    messages.append({"role": "user", "content": actual_msg})

    return messages


def validate_fiware_output(output: Dict[str, Any]) -> tuple[bool, str]:
    required = ["entity_type", "limit", "confidence"]
    for field in required:
        if field not in output:
            return False, f"Missing required field: {field}"

    if output["entity_type"] not in FIWARE_ENTITY_TYPES:
        return False, f"Invalid entity_type: {output['entity_type']}"

    if not isinstance(output["limit"], int):
        return False, "limit must be an integer"
    if not 1 <= output["limit"] <= 100:
        return False, "limit must be between 1 and 100"

    if not isinstance(output["confidence"], (int, float)):
        return False, "confidence must be a number"
    if not 0.0 <= output["confidence"] <= 1.0:
        return False, "confidence must be between 0.0 and 1.0"

    if output.get("attributes") is not None:
        if not isinstance(output["attributes"], list):
            return False, "attributes must be a list or null"

    return True, "Valid"
