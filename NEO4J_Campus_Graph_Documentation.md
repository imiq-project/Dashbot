# OVGU Campus Spatial Graph - Complete Documentation

## 🎯 Project Overview

**Goal:** Build a smart mobility chatbot for OVGU Magdeburg campus that can answer natural human questions like:
- "Where can I eat near Building 16?"
- "I don't want Italian, any Turkish food nearby?"
- "Is there wheelchair accessible route to the library?"
- "What's near the Universität tram stop?"
- "What's the temperature near Mensa?"
- "Are there free parking spots near Faculty CS?"

---

## 📊 Current Database State

### Node Types & Counts

| Node Type | Count | Description |
|-----------|-------|-------------|
| **Stop** | 297 | Tram/bus stops in Magdeburg |
| **POI** | 91 | Points of Interest (restaurants, cafes, shops, library) |
| **Building** | 59 | OVGU campus buildings |
| **Street** | 57 | Streets with coordinates |
| **Sensor** | 18 | IoT sensors (Weather, Parking, Traffic, AirQuality) |
| **Line** | 24 | Transit lines (Tram 1, 2, 3, etc.) |
| **Landmark** | 6 | Notable landmarks |
| **Area** | 2 | Campus areas |

### POI Categories Distribution

| Category | Count | Examples |
|----------|-------|----------|
| cafe | 36 | Starbucks, Coffee Fellows, Cafe Frosi |
| restaurant | 35 | L'Osteria, Izgaram, Shirokuro |
| supermarket | 12 | PENNY, REWE, Aldi |
| kiosk | 4 | Small shops |
| mensa | 1 | Mensa Uni |
| sports | 1 | Sports venue |
| education | 1 | Vision Hub |
| library | 1 | Universitätsbibliothek |

### Sensor Types Distribution

| Sensor Type | Count | Realtime Attributes |
|-------------|-------|---------------------|
| Weather | 9 | temperature, humidity, barometricPressure, windSpeed, rainfall |
| AirQuality | 4 | no2, pm10, pm25, o3 |
| Parking | 3 | freeSpaces, totalSpaces |
| Traffic | 2 | avgSpeed, cyclists, pedestrians, vehiclesIn, vehiclesOut |

---

## 🔗 Relationships

### POI & Building Relationships

| Relationship | Count | Description |
|--------------|-------|-------------|
| **NEARBY** | 1,792 | Building/Stop → POI (with category, tier, distance) |
| **NEAREST_BUILDING** | 270 | POI → nearest campus building |
| **NEAREST_STOP** | 250 | POI → nearest transit stop |
| **ADJACENT_TO** | 229 | Building ↔ Building (<150m) |
| **ACCESSIBLE_ROUTE** | 114 | Wheelchair accessible building connections |
| **ON_STREET** | 230+ | Entity on street |

### Sensor Relationships

| Relationship | Count | Description |
|--------------|-------|-------------|
| **NEAR_BUILDING** | 422 | Sensor → Buildings within 500m |
| **NEARBY_POI** | 185 | Sensor → POIs within 500m |
| **NEARBY_STOP** | 77 | Sensor → Stops within 500m |
| **NEAREST_STOP** | 18 | Sensor → Closest stop |
| **NEAREST_BUILDING** | 18 | Sensor → Closest building |
| **NEAREST_POI** | 18 | Sensor → Closest POI |

### Transit Relationships

| Relationship | Count | Description |
|--------------|-------|-------------|
| NEXT_STOP | 945 | Transit route connections |
| WALKING_DISTANCE | 598 | Walkable connections |
| SERVED_BY | 529 | Stop ↔ Line |

---

## 🌡️ FIWARE IoT Integration

### Sensor Data Structure

Sensors in Neo4j store coordinates and type information. Real-time data is queried from FIWARE using geo-coordinates.

**Sensor Node Properties:**
```
(:Sensor {
    id: 'Weather_Sensor_1',
    name: 'Weather Sensor 1',
    type: 'Weather',           // Used for FIWARE query
    category: 'weather',
    latitude: 52.138780,       // Used for FIWARE geo-query
    longitude: 11.645330,
    realtime_attributes: ['temperature', 'humidity'],
    created_at: datetime()
})
```

### FIWARE API Configuration

```python
# Set in .env file — never hardcode API keys
FIWARE_BASE_URL = os.getenv("FIWARE_BASE_URL")
FIWARE_API_KEY = os.getenv("FIWARE_API_KEY")
```

### Querying FIWARE by Coordinates

The chatbot queries FIWARE using geo-coordinates (not entity IDs):

```python
import requests
from config import FIWARE_BASE_URL, FIWARE_API_KEY

def get_sensor_data(sensor_type, latitude, longitude, radius=500):
    with requests.session() as session:
        session.headers['x-api-key'] = FIWARE_API_KEY

        response = session.get(
            f"{FIWARE_BASE_URL}/entities",
            params={
                "type": sensor_type,
                "georel": f"near;maxDistance:{radius}",
                "geometry": "point",
                "coords": f"{latitude},{longitude}",
                "limit": 1
            }
        )

        if response.status_code == 200:
            return response.json()
        return None
```

### Available FIWARE Entity Types

| FIWARE Type | Attributes |
|-------------|------------|
| Weather | temperature, humidity |
| Parking | freeSpaces, totalSpaces |
| Traffic | avgSpeed, cyclists, pedestrians, vehiclesIn, vehiclesOut |
| AirQuality | no2, pm10, pm25, o3 |

### Sensor Locations

| Sensor ID | Type | Latitude | Longitude |
|-----------|------|----------|-----------|
| Weather_Sensor_1 | Weather | 52.138780 | 11.645330 |
| Weather_Sensor_2 | Weather | 52.141750 | 11.656400 |
| Weather_Sensor_3 | Weather | 52.139660 | 11.647610 |
| Weather_Sensor_4 | Weather | 52.138880 | 11.647070 |
| Weather_Sensor_5 | Weather | 52.140310 | 11.640390 |
| Weather_Sensor_6 | Weather | 52.142760 | 11.645130 |
| Weather_Sensor_7 | Weather | 52.140200 | 11.636550 |
| Weather_Sensor_8 | Weather | 52.141234 | 11.654584 |
| Weather_Sensor_9 | Weather | 52.146147 | 11.661766 |
| Parking_Sensor_1 | Parking | 52.141200 | 11.655800 |
| Parking_Sensor_2 | Parking | 52.138780 | 11.645330 |
| Parking_Sensor_3 | Parking | 52.143100 | 11.645700 |
| Traffic_Sensor_1 | Traffic | 52.141050 | 11.655110 |
| Traffic_Sensor_2 | Traffic | 52.138750 | 11.645060 |
| AirQuality_Sensor_1 | AirQuality | 52.120768 | 11.632659 |
| AirQuality_Sensor_2 | AirQuality | 52.131761 | 11.631908 |
| AirQuality_Sensor_3 | AirQuality | 52.127919 | 11.611443 |
| AirQuality_Sensor_4 | AirQuality | 52.131893 | 11.627042 |

---

## 🔍 Full-Text Search (Lucene Indexes)

### Overview

The chatbot uses **Neo4j full-text search indexes** (Lucene-based) for all location searches. This provides:
- **BM25 relevance scoring** — rare/specific words (e.g., "imiq") automatically rank higher than common words (e.g., "office")
- **Fuzzy matching** — typos like "libary" still find "library" (Levenshtein distance 1)
- **Index-backed speed** — no full table scans
- **Cross-type search** — Buildings, Stops, POIs, and Landmarks searched simultaneously

### Full-Text Indexes

4 indexes are auto-created on first search via `_ensure_fulltext_indexes()`:

```cypher
CREATE FULLTEXT INDEX building_fts IF NOT EXISTS FOR (b:Building)
  ON EACH [b.name, b.function, b.note, b.address, b.aliases, b.departments]

CREATE FULLTEXT INDEX stop_fts IF NOT EXISTS FOR (s:Stop)
  ON EACH [s.name, s.id]

CREATE FULLTEXT INDEX poi_fts IF NOT EXISTS FOR (p:POI)
  ON EACH [p.name, p.type, p.cuisine, p.aliases, p.note, p.address]

CREATE FULLTEXT INDEX landmark_fts IF NOT EXISTS FOR (l:Landmark)
  ON EACH [l.name, l.description]
```

- List properties (`aliases`, `departments`) are indexed element-by-element
- Indexes are idempotent (`IF NOT EXISTS`) — safe to run on every startup
- Availability is cached in `_fulltext_available` for the process lifetime
- If index creation fails (e.g., permissions), the system falls back to legacy `CONTAINS` search

### How Search Works

**User query:** `"imiq office"`

1. **Lucene query built:** `imiq~1 imiq^2 office~1 office^2`
   - `~1` = fuzzy (edit distance 1 for typo tolerance)
   - `^2` = boost exact matches over fuzzy matches
2. **4 indexes queried** in parallel (building, stop, poi, landmark)
3. **BM25 scoring:** "imiq" is rare (1 building) → high IDF score. "office" is common (many buildings) → low IDF score. IMIQ Project Building wins.
4. **Enrichment:** Streets, building details, POI details added
5. **Name boost:** Small Python-level bonus for name-field matches (compensates for Lucene not distinguishing fields)

### Query Examples

| User Input | Lucene Query | What BM25 Does |
|---|---|---|
| "imiq office" | `imiq~1 imiq^2 office~1 office^2` | "imiq" is rare → high score for Building 80 |
| "mensa" | `mensa~1 mensa^2` | Finds Mensa POI and building |
| "libary" (typo) | `libary~1 libary^2` | Fuzzy matches "library" |
| "italian restaurant" | `italian~1 italian^2 restaurant~1 restaurant^2` | Matches POI cuisine + type |

### Fallback

If full-text indexes are unavailable, the system falls back to legacy `CONTAINS`-based search:
1. Exact phrase match across all node types
2. Word-by-word matching with Cypher-level scoring
3. Single keyword search

---

## 🤖 Chatbot Query Examples

### Find Weather Near a Building

```cypher
// User asks: "What's the weather near Building 29?"
WITH '29' AS requested_building_id

MATCH (b:Building {id: requested_building_id})
OPTIONAL MATCH (s:Sensor {type: 'Weather'})
WHERE s.latitude IS NOT NULL
WITH b, s, point.distance(
    point({latitude: b.latitude, longitude: b.longitude}),
    point({latitude: s.latitude, longitude: s.longitude})
) AS dist
ORDER BY dist
WITH b, collect({sensor: s, distance: dist})[0] AS nearest

RETURN b.name AS building_name,
       nearest.sensor.latitude AS sensor_lat,
       nearest.sensor.longitude AS sensor_lon,
       round(nearest.distance) AS distance_m
// Then query FIWARE with sensor_lat, sensor_lon
```

### Find Parking Availability

```cypher
// User asks: "Any free parking near Mensa?"
MATCH (p:POI)
WHERE toLower(p.name) CONTAINS 'mensa'
WITH p
MATCH (s:Sensor {type: 'Parking'})
WITH p, s, point.distance(
    point({latitude: p.latitude, longitude: p.longitude}),
    point({latitude: s.latitude, longitude: s.longitude})
) AS dist
ORDER BY dist LIMIT 1
RETURN s.latitude, s.longitude, dist AS distance_m
// Then query FIWARE for real-time freeSpaces
```

### Handle Missing Sensor Coverage

```cypher
// Query with user-friendly message when no sensor nearby
WITH '40' AS requested_building_id

MATCH (b:Building {id: requested_building_id})
OPTIONAL MATCH (s:Sensor {type: 'Weather'})
WHERE s.latitude IS NOT NULL
WITH b, s, 
     CASE WHEN s IS NOT NULL THEN
         point.distance(
             point({latitude: b.latitude, longitude: b.longitude}),
             point({latitude: s.latitude, longitude: s.longitude})
         )
     ELSE null END AS dist
ORDER BY dist
WITH b, collect({sensor: s, distance: dist})[0] AS nearest

RETURN b.name AS building_name,
       round(nearest.distance) AS distance_m,
       CASE 
           WHEN nearest.distance IS NULL THEN 'Sorry, no weather sensors are available.'
           WHEN nearest.distance > 1000 THEN 'No weather sensor nearby. Data may not be accurate.'
           WHEN nearest.distance > 500 THEN 'Nearest sensor is ' + toString(round(nearest.distance)) + 'm away.'
           ELSE 'Weather sensor available nearby.'
       END AS user_message;
```

### Food Recommendations

```cypher
// User asks: "Where can I eat near Building 16?"
MATCH (b:Building {id: '16'})-[r:NEARBY]->(p:POI)
WHERE r.category = 'food' AND r.tier = 'nearest'
RETURN p.name, p.cuisine, r.distance_m, p.opening_hours
ORDER BY r.rank LIMIT 3
```

### Filter by Cuisine

```cypher
// User asks: "I don't want Italian, any Turkish food nearby?"
MATCH (b:Building {id: '16'})-[r:NEARBY]->(p:POI)
WHERE r.category = 'food'
  AND (p.cuisine = 'turkish' OR 'middle_eastern' IN p.cuisine_tags)
RETURN p.name, r.distance_m, p.opening_hours
ORDER BY r.distance_m
```

---

## ✅ Recent Updates

### February 2026 — Full-Text Search & Security Fixes

**Search System Overhaul:**
- Replaced manual `toLower().CONTAINS` 4-strategy cascade with **Neo4j Lucene full-text indexes**
- 4 auto-created indexes: `building_fts`, `stop_fts`, `poi_fts`, `landmark_fts`
- BM25 scoring handles word rarity automatically (fixes "imiq office" returning wrong building)
- Real fuzzy matching via Lucene `word~1` (replaces fake first-4-chars approach)
- Automatic fallback to legacy CONTAINS search if indexes unavailable
- All search strategies now cover Building, Stop, POI, and Landmark node types (previously only Buildings for fallback strategies)

**Enrichment:**
- Added `_enrich_buildings_with_details()` — attaches full properties (function, note, departments, aliases, nearby_buildings, sensors, nearest_stops) to search results before scoring
- Added `_enrich_pois_with_details()` — attaches aliases, note, dietary_options, opening_hours to POI results

**Security Fixes:**
- Moved all hardcoded API keys (FIWARE, TomTom, ElevenLabs) to environment variables
- Fixed 9 Cypher injection points (f-string → parameterized queries)
- Replaced unsafe pickle serialization with JSON
- Fixed CORS allow_credentials with wildcard origins

**Multi-Agent System:**
- Added session lifecycle (POST /session/start → /chat → /session/end)
- Auto-cleanup removes idle sessions after 30 minutes
- Added `<think>` tag stripping for Qwen3 models
- Added 90s HTTP timeout for LLM calls

### January 2026 — Library & Sensor Rebuild

**Added Library POI:**
- Created Universitätsbibliothek as POI node
- Connected with NEARBY, NEAREST_BUILDING, NEAREST_STOP relationships

**Rebuilt Sensor System:**
- Deleted old sensor nodes with inconsistent schema
- Created 18 new sensor nodes with:
  - Generic naming (Weather_Sensor_1, Parking_Sensor_1, etc.)
  - Proper coordinates for FIWARE geo-queries
  - Consistent properties structure
- Created 738 sensor relationships:
  - NEAR_BUILDING (422)
  - NEARBY_POI (185)
  - NEARBY_STOP (77)
  - NEAREST_STOP (18)
  - NEAREST_BUILDING (18)
  - NEAREST_POI (18)

**FIWARE Integration:**
- Confirmed geo-query capability
- Sensors queryable by coordinates with radius
- Supports Weather, Parking, Traffic, AirQuality types

---

## 🚀 Next Steps Roadmap

### Step 1: Enrich POI Data
- Fill missing cuisine data
- Add dietary options (vegan, vegetarian, halal)
- Add price range (€, €€, €€€)

### Step 2: Add Missing POI Categories
| Category | Status | Action Needed |
|----------|--------|---------------|
| ATM/Bank | ❌ Missing | Add Sparkasse, Deutsche Bank locations |
| Pharmacy | ❌ Missing | Add Apotheke locations |
| Print/Copy | ❌ Missing | Add copy shops |
| Toilet/WC | ❌ Missing | Add public toilets |

### Step 3: Complete Accessibility Data
- Update all buildings with wheelchair info
- Add elevator, ramp, accessible WC data

### Step 4: Real-time Integration
| Data Source | Purpose |
|-------------|---------|
| FIWARE Sensors | Weather, Parking, Traffic, Air Quality |
| MVB API | Real-time tram arrivals |
| Mensa API | Today's menu & prices |

---

## 📈 Data Quality Metrics

### Current State
| Metric | Value |
|--------|-------|
| Total Nodes | ~570 |
| Total Relationships | ~5,500+ |
| Sensors with coordinates | 18/18 (100%) |
| Sensor relationships | 738 |
| POIs with NEARBY | 91/91 (100%) |
| Buildings with NEARBY | 59/59 (100%) |

---

## 🗂️ File Structure

```
/app_trial/
├── APP.py                  # CLI entry point (mono-agent evaluation)
├── api.py                  # FastAPI REST server (session management, streaming)
├── orchestrator.py         # Multi-agent pipeline coordinator
├── config.py               # Environment variable configuration
├── neo4j_tools.py          # Neo4j database interface (search, routing, sensors)
├── .env                    # API keys and model settings (not committed)
├── agents/
│   ├── base_agent.py       # Abstract base class (LLM calls, retries, timeouts)
│   ├── router_agent.py     # Intent classification
│   ├── neo4j_agent.py      # LLM-based function selector for Neo4j
│   ├── synthesizer_agent.py # Natural language response generation
│   └── dialogue_manager.py # Multi-turn session state
├── prompts/
│   ├── neo4j_prompts.py    # 25+ function defs & few-shot examples
│   └── synthesizer_prompts.py
├── tools/
│   └── router.py           # Query routing logic
├── data/
│   └── knowledge/          # Static knowledge files
└── NEO4J_Campus_Graph_Documentation.md (this file)
```

### Key Architecture

```
User Query → RouterAgent → Neo4jAgent → neo4j_tools.py → Neo4j (AuraDB)
                                                              ↓
                        SynthesizerAgent ← specialist results ←
                              ↓
                     Natural language response
```

- **RouterAgent** classifies intent (building info, directions, sensor data, etc.)
- **Neo4jAgent** selects which `neo4j_tools.py` function to call via LLM + few-shot examples
- **neo4j_tools.py** executes the query using full-text search indexes
- **SynthesizerAgent** converts raw data into a human-friendly response

---

*Last Updated: February 7, 2026*
*Project: OVGU Smart Mobility Chatbot*
