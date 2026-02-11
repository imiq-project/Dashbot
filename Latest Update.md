# Latest Update - Neo4j Universal Building Search

**Date:** January 27, 2026
**Updated File:** `neo4j_tools.py`

---

## Problem Statement

The Neo4j building search was **inconsistent and limited**:

1. **Inconsistent search across functions** - Different functions used different search logic
2. **Static property search** - Only searched hardcoded property names (name, id, function)
3. **No alias support** - "Welcome Centre" couldn't find "Campus Welcome Center" even though "welcome centre" was stored as an alias
4. **No typo tolerance** - "welcame centree" or "libary" wouldn't match anything
5. **No dynamic property search** - Couldn't find buildings by phone number or other custom properties

### Example of the Problem

```
User: "What does weather sensor show near welcome centre?"

[NEO4J] Searching for building: 'welcome centre'
[NEO4J] ❌ Building not found: 'Welcome Centre'
```

The building "Campus Welcome Center" existed with aliases `["welcome center", "welcome", "welcome centre", "visitor center", "reception"]`, but the search couldn't find it.

---

## Solution Implemented

### 1. New Universal Building Finder (`_find_building_universal`)

Created a single source of truth for ALL building searches:

```python
def _find_building_universal(self, search_input: str, session=None) -> Optional[Dict]:
    """
    UNIVERSAL building search - used by ALL functions that need to find a building.

    Search strategy:
    1. Normalize input (lowercase, remove common prefixes)
    2. Try exact ID match
    3. Search ALL text properties in Neo4j (dynamic - whatever properties exist)
    4. Fallback to semantic search (handles typos like "welcame centree" → "welcome centre")
    """
```

### 2. Dynamic Property Search (Cypher Query)

The search now dynamically searches **ALL properties** on each Building node, not a hardcoded list:

```cypher
MATCH (b:Building)
WHERE
    // Exact ID matches
    b.id = $query_id OR b.id = $search_term

    // Search ALL properties dynamically using safe type conversion
    OR ANY(key IN keys(b) WHERE
        // Use CASE to safely convert any value to searchable string
        toLower(
            CASE
                WHEN b[key] IS NULL THEN ''
                WHEN b[key] IS :: STRING THEN b[key]
                WHEN b[key] IS :: LIST<ANY> THEN
                    reduce(s = '', item IN b[key] |
                        s + ' ' + CASE WHEN item IS :: STRING THEN item ELSE toString(item) END
                    )
                ELSE toString(b[key])
            END
        ) CONTAINS $search_term
    )

RETURN b.id as id, b.name as name, b.latitude as latitude, b.longitude as longitude
LIMIT 1
```

**Key Features:**
- Uses `keys(b)` to get ALL property names dynamically
- Handles both STRING and LIST properties safely
- Uses `CASE WHEN` to avoid type errors with `toLower()`

### 3. Dynamic Semantic Search Initialization

The semantic search now indexes ALL properties from each building:

```python
def _init_semantic_search(self):
    # Get ALL properties from the node dynamically
    building_node = dict(record["building"])

    # Create searchable text from ALL properties dynamically
    text_parts = []
    for key, value in building_node.items():
        if isinstance(value, list):
            text_parts.append(" ".join(str(v) for v in value if v))
        elif isinstance(value, (str, int, float)):
            text_parts.append(str(value))  # Includes phone numbers!
```

### 4. Lowered Semantic Search Threshold

Changed from `0.25` to `0.18` to catch more typos:

```python
def _semantic_building_search(self, query: str, threshold: float = 0.18) -> Optional[Dict]:
    """Threshold lowered to 0.18 to catch more typos (e.g., 'libary' -> 'library')."""
```

---

## Functions Updated

All these functions now use `_find_building_universal()` for consistent search:

| Function | Purpose |
|----------|---------|
| `get_building_info()` | Get detailed building information |
| `get_sensor_near_building()` | Find nearest sensor to a building |
| `get_all_sensors_near_building()` | Find all sensors near a building |
| `_find_places_near_building()` | Find POIs near a building |
| `find_building_by_function()` | Search buildings by any property |
| `_get_sensors_by_distance()` | Fallback sensor search |

Functions that call `get_building_info()` automatically benefit:
- `get_nearby_buildings()`
- `get_nearest_tram_from_building()`

---

## What Now Works

### 1. Spelling Variants (British/American)

```
Query: "Welcome Centre" (British)
Result: ✅ Found "Campus Welcome Center" via aliases
```

### 2. Search by Any Property

```
Query: "faculty computer science"
Result: ✅ Found "Faculty of Computer Science"

Query: "299" (a price in housing_options)
Result: ✅ Found dorms with that price in their housing_options array
```

### 3. Typo Tolerance

```
Query: "libary" (typo)
Result: ✅ Semantic search finds closest match (score: 0.20)
```

### 4. Phone Number Search (if property exists)

If a building has a `phone` property like `"+49 391 67 515 75"`, searching for that number will find the building.

### 5. Alias Arrays

Buildings with aliases like:
```
aliases: ["welcome center", "welcome", "welcome centre", "visitor center", "reception"]
```

Can now be found by ANY of those terms.

---

## Test Results

| Test | Query | Result |
|------|-------|--------|
| Spelling variant | "Welcome Centre" | ✅ Found Campus Welcome Center |
| Department search | "faculty computer science" | ✅ Found Faculty of Computer Science |
| Typo tolerance | "libary" | ✅ Found via semantic search |
| Standard search | "mensa" | ✅ Found Mensa / OvGU Sports Center |
| American spelling | "welcome center" | ✅ Found Campus Welcome Center |

---

## Architecture Overview

```
User Query: "weather near welcome centre"
         ↓
┌─────────────────────────────────────────────────────────────┐
│                 _find_building_universal()                  │
│                                                             │
│  1. Normalize: "welcome centre" → "welcome centre"          │
│  2. Dynamic Cypher: Search ALL properties                   │
│     → Found in aliases array!                               │
│  3. Return: {id: "01", name: "Campus Welcome Center", ...}  │
└─────────────────────────────────────────────────────────────┘
         ↓
    get_sensor_near_building() uses the found building
         ↓
    Returns nearest Weather sensor (8m away)
```

---

## Important Notes

### What the System CAN Do:
- Find buildings by any text in any property
- Handle spelling variants and typos
- Search arrays (aliases, departments, housing_options, etc.)
- Find buildings by phone numbers or other custom properties

### What the System CANNOT Do:
- Numerical comparisons (e.g., "rent lower than 500€")
- The prices are embedded in text strings, not separate numeric fields
- The LLM (Synthesizer) handles numerical interpretation from the returned text

### Example of Numerical Query Workflow:
```
User: "Are there dorms with rent lower than 500€?"
         ↓
RouterAgent: Identifies as housing query
         ↓
Neo4jAgent: Fetches all dorms with housing_options
         ↓
SynthesizerAgent: Reads housing_options text, extracts prices,
                  reports: "Yes! All dorms have options under 500€"
```

---

## Files Changed

- `neo4j_tools.py` - Main changes to building search logic

## New Methods Added

- `_find_building_universal()` - Universal building search
- `_get_sensors_by_distance_from_building()` - Helper for sensor search with pre-found building

## Methods Modified

- `_init_semantic_search()` - Now indexes ALL properties dynamically
- `_semantic_building_search()` - Threshold lowered to 0.18
- `get_building_info()` - Now uses universal finder
- `get_sensor_near_building()` - Now uses universal finder
- `get_all_sensors_near_building()` - Now uses universal finder
- `_find_places_near_building()` - Now uses universal finder
- `find_building_by_function()` - Now uses dynamic property search
- `_get_sensors_by_distance()` - Now uses universal finder

---

## Update 2: ID Priority & Synthesizer Fixes

**Date:** January 27, 2026 (later)

### Problem 1: ID Search Returning Wrong Building

When searching for building "24", the system returned "Campus Welcome Center" instead of "Faculty of Natural Sciences" because:
- Campus Welcome Center's latitude `52.14024458724847` contains "24"
- The dynamic property search found this match before the ID match

**Fix:** Split the search into two steps:
1. **Step 1:** Try exact ID match FIRST (highest priority)
2. **Step 2:** If no ID match, search text properties (excluding numeric fields like latitude/longitude)

```cypher
// STEP 1: Exact ID match (highest priority)
MATCH (b:Building)
WHERE b.id = $query_id OR b.id = $search_term
RETURN b
LIMIT 1

// STEP 2: Text property search (excludes numeric fields)
MATCH (b:Building)
WHERE ANY(key IN keys(b) WHERE
    NOT key IN ['latitude', 'longitude', 'lat', 'lon', 'id']
    AND toLower(...) CONTAINS $search_term
)
```

### Problem 2: Synthesizer Exposing Internal Details

The Synthesizer was saying things like:
> "Buildings 06 and 30 have similar **scores**, indicating they might have a similar design"

Users don't know what "scores" means - this is internal system information.

**Fix:** Added guidelines to `synthesizer_prompts.py`:
```
**IMPORTANT - Hide Internal System Details:**
- NEVER mention "scores", "confidence levels", "match types", or "search strategies"
- NEVER expose technical details like "node IDs", "Neo4j", "FIWARE", "agent names"
- Users don't care about HOW we found the answer, only WHAT the answer is
```

### Test Results After Fix

| Query | Before | After |
|-------|--------|-------|
| "24" | Campus Welcome Center (wrong!) | Faculty of Natural Sciences (correct!) |
| "alike" | Found Buildings 23, 24 | Found Buildings 23, 24 with notes |
| "similar" | Found Buildings 23, 24 | Found Buildings 23, 24 |

### Example: "Which buildings look alike?"

Now the system correctly finds:
- **Building 23** (Faculty of Economics): `note: "Looks alike Building 24 - small cube buildings that look really similar"`
- **Building 24** (Faculty of Natural Sciences): `note: "Looks alike Building 23 - small cube buildings that look really similar"`

---

## Update 3: Router & Neo4j Agent Query Routing Fixes

**Date:** January 27, 2026 (later)

### Problem 1: "Which buildings look alike?" Misrouted to Knowledge Base

The Router was classifying building similarity queries as `knowledge_query` instead of `get_location_info`:

```
Query: "Which 2 buildings look alike"
Router: primary_intent: "knowledge_query", required_capabilities: ["knowledge_base_search"]
```

Building similarity info (like "Looks alike Building 24") is stored in Neo4j node properties, NOT in the knowledge base.

**Fix:** Added patterns and few-shot examples in `router_prompts.py`:

```python
**Pattern: "Which buildings look alike?" or "Which buildings are similar?"**
-> primary_intent: get_location_info
-> capabilities: [graph_location_lookup]
```

### Problem 2: "How many sensors?" Returned 0 Sensors

The query "how many sensors" was calling `list_sensors_by_type` with `sensor_type: None`, which returned 0 results.

```
[NEO4J] list_sensors_by_type: type='None'
[NEO4J] Found 0 sensors of type 'None'
```

**Fix 1:** Added `list_all_sensors()` function in `neo4j_tools.py`:

```python
def list_all_sensors(self) -> Dict:
    """List ALL sensors of all types with counts by type."""
```

**Fix 2:** Added few-shot examples in `neo4j_prompts.py`:

```python
{
    "user_query": "How many sensors are there?",
    "expected_output": {
        "function_name": "list_all_sensors",
        "parameters": {}
    }
}
```

### Problem 3: Building Similarity Queries Not Using find_building_by_function

The Neo4j agent wasn't aware that `find_building_by_function` could search ALL properties.

**Fix:** Added `find_building_by_function` to `NEO4J_FUNCTIONS` in `neo4j_prompts.py`:

```python
"find_building_by_function": {
    "description": "Search for buildings by ANY property (name, function, notes, etc.)",
    "parameters": {"query": "Search term"},
    "examples": ["Which buildings look alike?", "Which buildings are similar?"]
}
```

### Problem 4: Route Queries Return Empty Directions

When no graph path (BORDERED_BY relationships) exists between buildings, the `get_directions_between_buildings` function returned empty directions even though both buildings were found.

**Fix:** Added fallback in `get_directions_between_buildings` that calculates:
- Distance using Neo4j spatial functions
- Cardinal direction (north, south, east, west, or diagonal like "northeast")
- Estimated walking time (based on ~80m/min average walking speed)

```python
if not directions:
    # Calculate distance and basic direction from coordinates
    directions.append({
        "step": 1,
        "instruction": f"Head {primary_direction} from {from_building}",
        "towards": to_building,
        "distance_meters": distance_m,
        "estimated_walking_time_minutes": walking_time_min
    })
```

### Files Changed

| File | Changes |
|------|---------|
| `prompts/router_prompts.py` | Added patterns for "alike/similar", "how many sensors" |
| `prompts/neo4j_prompts.py` | Added `find_building_by_function`, `list_all_sensors` functions and examples |
| `neo4j_tools.py` | Added `list_all_sensors()` method, added fallback directions with distance calculation, fixed `_classify_location` |

### Problem 5: POI vs Building Classification Error

**Issue:** "Izgaram" (a restaurant) was incorrectly matched to "IBZ" (a building) via semantic search with a low score (0.33), preventing the POI search from running.

**Root cause:** The `_classify_location` function tried building search (which has semantic fallback) BEFORE trying POI search.

**Fix:** Modified `_classify_location` to:
1. Try exact building match first (no semantic fallback)
2. If only semantic match found, try POI search first
3. Only use semantic building match as last resort

```python
# If building match is semantic (not exact), try POI first!
if match_type in ["exact", "id_match", "property"]:
    return "building", {...}
else:
    print("Semantic building match found, but trying POI first...")
    semantic_building = building_result  # Save for later

# Try POI BEFORE accepting semantic building match
poi_result = self.get_poi_for_routing(location)
if poi_result.get("success"):
    return "poi", {...}
```

Also fixed `get_building_info` to propagate `match_type` to the result.

**Test Result:**
```
Query: "How can I go to izgaram from building 80?"
Before: Izgaram → IBZ (WRONG - semantic building match)
After: Izgaram → Izgaram restaurant (CORRECT - POI match)

Route: Building 80 → Bus 73 → Tram 8 → Izgaram
       Walk 1min → 9 stops → Transfer → 5 stops → Walk 1min
```

### Problem 6: get_nearby_buildings Parameter Mismatch

**Issue:** The Neo4j agent called `get_nearby_buildings(target="Building 03", radius_meters=500)` but the actual function signature is `get_nearby_buildings(building_id)`.

```
Neo4jTransitGraph.get_nearby_buildings() got an unexpected keyword argument 'target'
```

**Root cause:** The `NEO4J_FUNCTIONS` definition in `neo4j_prompts.py` had wrong parameter names.

**Fix:** Updated `neo4j_prompts.py`:
- Changed `target` → `building_id`
- Removed `radius_meters` and `building_filter` (function doesn't support them)
- Updated few-shot example

```python
# Before (WRONG)
"parameters": {
    "target": "Target building or location name",
    "radius_meters": "Search radius in meters"
}

# After (CORRECT)
"parameters": {
    "building_id": "Building name, number, or ID"
}
```

**Test Result:**
```
Query: "Which buildings are close to Building 03?"
Result: Found 2 nearby buildings:
  - Building 04 (Rectorate) - south
  - Building 02 (Faculty of Mathematics) - south-west
```

### Expected Behavior After Fix

| Query | Before | After |
|-------|--------|-------|
| "Which buildings look alike?" | knowledge_query | get_location_info + find_building_by_function |
| "How many sensors?" | list_sensors_by_type(None) = 0 | list_all_sensors() = 18 |
| "How many weather sensors?" | list_sensors_by_type(None) | list_sensors_by_type("Weather") = 9 |

---

## Update 4: Cuisine Filter Fix for Near-Building Searches

**Date:** January 27, 2026 (later)

### Problem: Turkish Restaurant Near Building Returns Wrong Results

When searching "Turkish restaurant near building 27", the system returned Asian, Greek, and Italian restaurants instead of Turkish ones. The cuisine filter was being ignored.

**Root Cause:** The `find_places` function accepted the `cuisine` parameter but didn't pass it to `_find_places_near_building`:

```python
# BEFORE (BROKEN)
elif query_type == "near_building":
    return self._find_places_near_building(session, building_id, place_type, limit)
    # cuisine was NOT passed!
```

The `_find_places_near_building` function also didn't accept or use the `cuisine` parameter.

### Fix Applied

1. **Updated `find_places`** to pass cuisine parameter:
```python
# AFTER (FIXED)
elif query_type == "near_building":
    return self._find_places_near_building(session, building_id, place_type, cuisine, limit)
```

2. **Updated `_find_places_near_building`** function signature:
```python
def _find_places_near_building(self, session, building_id: str, place_type: str, cuisine: str, limit: int) -> Dict:
```

3. **Added cuisine filter to Cypher queries** (both relationship and spatial):
```python
where_clauses = []
if place_type and place_type != "all":
    where_clauses.append("p.type = $place_type")
if cuisine:
    where_clauses.append("toLower(p.cuisine) CONTAINS toLower($cuisine)")
```

### Expected Behavior After Fix

| Query | Before | After |
|-------|--------|-------|
| "Turkish restaurant near building 27" | Asian, Greek, Italian (WRONG) | Izgaram (Turkish) ✅ |
| "Italian restaurant near mensa" | All restaurants (ignoring filter) | Only Italian restaurants ✅ |

---

## Update 5: New Fixed Schema Migration

**Date:** January 28, 2026

### Schema Changes

Buildings and POIs now have a **fixed schema** (all nodes have the same properties). The `id` field has been **removed** from buildings - building numbers are now stored in `aliases`.

### Building Schema (12 properties)
| Property | Type | Required |
|----------|------|----------|
| name | String | Yes |
| aliases | List | Yes (includes building numbers like "Building 29") |
| function | String | Yes |
| latitude | Float | Yes |
| longitude | Float | Yes |
| address | String | No (null if unknown) |
| opening_hours | String | No |
| phone | String | No |
| website | String | No |
| accessibility | String | No |
| departments | List | No |
| note | String | No |

### POI Schema (14 properties)
| Property | Type | Required |
|----------|------|----------|
| name | String | Yes |
| type | String | Yes |
| aliases | List | Yes |
| cuisine | String | No |
| latitude | Float | Yes |
| longitude | Float | Yes |
| address | String | No |
| opening_hours | String | No |
| phone | String | No |
| website | String | No |
| accessibility | String | No |
| price_range | String | No |
| dietary_options | List | No |
| fiware_id | String | No |
| note | String | No |

### Code Changes in neo4j_tools.py

**Search Logic Updated:**
- `_find_building_universal()`: Now searches `name` → `aliases` → `function/note`
- All Cypher queries: Changed from `Building {id: $id}` to `Building {name: $name}`
- Building results: `id` field now contains the building name for backward compatibility

**Search Priority (NEW):**
```cypher
-- Priority 1: Exact name match
WHERE toLower(b.name) = $search_term

-- Priority 2: Alias match (includes building numbers)
WHERE ANY(alias IN b.aliases WHERE toLower(alias) = $search_term)

-- Priority 3: Other text properties
WHERE toLower(b.function) CONTAINS $search_term
```

### Benefits of New Schema

1. **Predictable queries** - LLM knows exactly what properties exist
2. **Simpler Cypher** - No dynamic `keys(b)` iteration needed
3. **Aliases for everything** - "Welcome Centre" finds "Campus Welcome Center" via aliases
4. **Building numbers in aliases** - "Building 29" or "29" finds "Faculty of Computer Science"

---

## Update 6: Entity Caching for Follow-up Questions

**Date:** January 28, 2026

### Problem

When users asked follow-up questions like "What can I eat there?" after discussing a restaurant, the system couldn't answer because:
1. "there" doesn't match any location in Neo4j
2. Previous query results weren't stored
3. Synthesizer had no context about previously mentioned entities

### Solution: Entity Cache

Added an entity caching system to the Orchestrator that:
1. **Caches entities** from every Neo4j query (POIs, Buildings, Stops)
2. **Passes cache to Synthesizer** so it can answer follow-up questions
3. **Matches pronouns** like "there", "that restaurant", "it" to cached entities

### Files Changed

| File | Changes |
|------|---------|
| `orchestrator.py` | Added `entity_cache`, `_cache_entities_from_results()`, `_get_cached_entity()` |
| `prompts/synthesizer_prompts.py` | Added instructions and few-shot examples for using cached entities |
| `prompts/router_prompts.py` | Added patterns for "What can I eat at X?" → get_location_info |
| `prompts/neo4j_prompts.py` | Added few-shot examples for food/cuisine queries |
| `neo4j_tools.py` | POI queries now return cuisine, opening_hours, price_range, dietary_options |

### How It Works

```
Query 1: "How far is Izgaram from Building 3?"
  ↓
Neo4j returns: {name: "Izgaram", cuisine: "turkish", ...}
  ↓
Orchestrator caches: entity_cache["izgaram"] = {...}
  ↓
Response: "Izgaram is 1.3km from Building 3"

Query 2: "What can I eat there?"
  ↓
Router: get_location_info (poi_name: "there")
  ↓
Neo4j fails: "there" not found
  ↓
Orchestrator: cached_entity = entity_cache["izgaram"]
  ↓
Synthesizer receives: cached_entity: {cuisine: "turkish", ...}
  ↓
Response: "At Izgaram you can enjoy Turkish cuisine!"
```

### Cache Details

- Max cache size: 20 entities (configurable via `max_cache_size`)
- Cached by: entity name (lowercase) + all aliases
- Clears on: `reset_conversation()` or session restart
- Contains: All properties from Neo4j (cuisine, opening_hours, etc.)

---

## Update 7: TomTom Driving Routes & Parking Query Fix

**Date:** February 2, 2026

### Problem 1: ORS Driving Routes Lack Traffic Awareness

OpenRouteService (ORS) was used for all routes (walking, cycling, driving), but it:
- Doesn't know about real-time road closures
- Doesn't provide traffic-aware travel times
- Doesn't return street names for navigation
- Can't avoid congestion or incidents

### Solution: Split Routing by Transport Mode

**New Routing Strategy:**
| Mode | Service | Features |
|------|---------|----------|
| Walking | ORS | Pedestrian paths |
| Cycling | ORS | Bike lanes, paths |
| **Driving** | **TomTom** | Traffic-aware, street names, avoids closures |

### Files Changed

| File | Changes |
|------|---------|
| `clients/tomtom_client.py` | Added `get_driving_route_with_directions()` method |
| `orchestrator.py` | Updated `_call_ors()` to route driving to TomTom |
| `orchestrator.py` | Updated `_get_proactive_context()` to use TomTom for driving directions |
| `prompts/synthesizer_prompts.py` | Added "DRIVING ROUTES - POWERED BY TOMTOM" section |

### New TomTom Method: `get_driving_route_with_directions()`

```python
def get_driving_route_with_directions(
    self,
    start_coords: Tuple[float, float],  # (lat, lon)
    end_coords: Tuple[float, float],
    max_steps: int = 6
) -> Dict:
    """
    Returns:
    - distance, duration (traffic-aware)
    - traffic_status: "clear", "moderate_traffic", "heavy_traffic"
    - traffic_message: Human-readable summary
    - streets_on_route: List of street names (for Neo4j alignment)
    - directions: Turn-by-turn with coordinates
    - directions_text: Simplified direction instructions
    - departure_time, arrival_time
    """
```

### Updated `_call_ors()` Logic

```python
def _call_ors(self, origin_coords, dest_coords, modes=None):
    # Split modes
    ors_modes = [m for m in modes if m in ["walking", "cycling"]]
    use_tomtom = "driving" in modes

    # 1. ORS for walking/cycling
    if ors_modes:
        routes = self.ors_client.get_multi_modal_routes(...)

    # 2. TomTom for driving (traffic-aware)
    if use_tomtom and self.tomtom_client:
        driving_route = self.tomtom_client.get_driving_route_with_directions(...)
        # Includes: traffic_status, streets_on_route, directions
```

### Example Output

```
Query: "How can I get to mensa from hauptbahnhof?"

--- ORS Routes (Walking/Cycling) ---
  walking: 24 min (2.1 km) - source: ORS
  cycling: 8 min (2.1 km) - source: ORS

--- TomTom Route (Driving) ---
  driving: 5 min (3.0 km) - source: TomTom
  traffic: clear (Traffic is clear.)
  streets: Ernst-Reuter-Allee, Magdeburger Ring, Walther-Rathenau-Straße
```

### Street Names for Neo4j Alignment

The `streets_on_route` array can be used to:
- Display navigation instructions with real street names
- Align routes with Neo4j street/road data
- Show which major roads the route uses

---

### Problem 2: Direct Parking Queries Not Working

When user asked "what are the parking options near mensa?":
- Router classified as `get_location_info` (not `get_parking_info`)
- Only Neo4j was queried (searched for "parking near Mensa" as a location)
- FIWARE (real-time parking data) was never called
- Result: "I couldn't find parking details"

### Solution: Parking Query Detection in Proactive Context

Added parking data fetch for any query that mentions parking:

```python
def _get_proactive_context(self, intent, entities, query, ...):
    # Direct parking queries - fetch from FIWARE
    if self._is_parking_query(query):
        # Try to get coordinates for mentioned location
        location_coords = self._get_coordinates_for_location(location_name)

        # Fetch real-time parking data
        parking = self._quick_parking_check(location_coords, max_distance_km=1.0)
        if parking:
            context["parking"] = parking
            context["parking_query"] = True
```

### New Method: `_is_parking_query()`

```python
def _is_parking_query(self, query: str) -> bool:
    parking_keywords = [
        "parking", "park my car", "where to park", "car park", "parkplatz",
        "can i park", "where can i park", "park near", "park close",
        "park available", "free parking", "parking spot", "parking space"
    ]
    return any(kw in query.lower() for kw in parking_keywords)
```

### Fixed `_quick_parking_check()`

The method now properly handles queries without destination coordinates:

```python
def _quick_parking_check(self, destination_coords=None, max_distance_km=0.5):
    # Calculate distance if we have both coords
    distance = None
    if destination_coords and parking_lat and parking_lon:
        distance = self._haversine_distance(...)
        if distance > max_distance_km:
            continue  # Skip if too far

    # If no destination coords, return ALL parking (for direct queries)
    nearby_parking.append({
        "name": name,
        "available": available,
        "capacity": capacity,
        "distance_km": distance  # None if no destination coords
    })
```

### Synthesizer Prompt Updates

Added parking query handling instructions:

```markdown
## PARKING QUERIES

When proactive_context contains parking data:
1. List available parking options with spots
2. Mention which is closest if distance_km provided
3. Report total availability

Example:
Query: "what are the parking options near mensa?"
Response: "There are a couple of parking options near Mensa.
NorthPark is the closest with 6 spots available.
ScienceHarbor also has 10 spots free."
```

### Test Results

| Query | Before | After |
|-------|--------|-------|
| Driving route | ORS only (no traffic) | TomTom with traffic + streets |
| "parking near mensa" | "couldn't find details" | "NorthPark: 6 spots, ScienceHarbor: 10 spots" |
| "where can I park?" | No FIWARE data | Real-time parking from FIWARE |

---

### Summary of Changes

**TomTom Integration:**
- Driving routes now use TomTom (traffic-aware, street names)
- Walking/cycling still use ORS
- Automatic fallback to ORS if TomTom unavailable

**Parking Queries:**
- Direct parking questions now fetch FIWARE data
- Location-aware filtering (nearby parking only)
- Works with or without specific location mentioned

**Key Benefits:**
- Driving routes avoid closed roads automatically
- Real-time traffic delays included in travel time
- Street names available for Neo4j alignment
- Parking queries always return real-time data

---

## Update 8: streets_on_route for Walking/Cycling (ORS)

**Date:** February 2, 2026

### Addition

Added `streets_on_route` to ORS walking and cycling routes for Neo4j alignment (same as TomTom driving routes).

### Files Changed

| File | Change |
|------|--------|
| `clients/ors_client.py` | Added `streets_on_route` to `get_route_with_directions()` |
| `orchestrator.py` | Added `streets_on_route` to proactive context for walking/cycling |

### Code Changes

**ors_client.py - `get_route_with_directions()`:**
```python
directions = []
streets_on_route = []  # NEW: List of street names for Neo4j alignment

for segment in segments:
    for step in steps:
        name = step.get("name", "")

        # Collect unique street names
        if name and name not in streets_on_route and name != "-":
            streets_on_route.append(name)

return {
    # ...
    "streets_on_route": streets_on_route  # NEW
}
```

### Example Output

```python
# Walking route
{
    "duration": "22 min",
    "distance": "1.9 km",
    "streets_on_route": [
        "Gustav-Adolf-Straße",
        "Walther-Rathenau-Straße",
        "Breiter Weg",
        "Erzbergerstraße",
        "Otto-von-Guericke-Straße",
        "Ernst-Reuter-Allee",
        "Bahnhofstraße"
    ]
}

# Cycling route
{
    "duration": "7 min",
    "distance": "2.0 km",
    "streets_on_route": [
        "Gustav-Adolf-Straße",
        "Walther-Rathenau-Straße",
        "Universitätsplatz",
        "Erzbergerstraße",
        "Ernst-Reuter-Allee",
        "Bahnhofstraße"
    ]
}
```

### All Transport Modes Now Have streets_on_route

| Mode | Service | streets_on_route |
|------|---------|------------------|
| Walking | ORS | Yes |
| Cycling | ORS | Yes |
| Driving | TomTom | Yes |

---

## Update 9: Fixed Coordinate Extraction for Building Routes

**Date:** February 2, 2026

### Problem

When routing from "IMIQ Office" to "Mensa", the system returned wrong routes (3 min walk instead of 10 min):

```
# Neo4j semantic search (CORRECT):
'imiq office' → IMIQ Project Building

# Coordinate lookup via find_any_location (WRONG):
'IMIQ Office' → International Office (matched word "Office")
→ Wrong coordinates used for ORS/TomTom routing!
```

### Root Cause

`get_directions_between_buildings()` returned `from` and `to` WITHOUT coordinates:

```python
return {
    "from": {"id": ..., "name": ...},  # NO lat/lon!
    "to": {"id": ..., "name": ...},    # NO lat/lon!
}
```

This caused `_extract_coordinates_from_neo4j()` to fail, falling back to `find_any_location()` which matched the wrong building.

### Fix

Added latitude/longitude to the `from` and `to` dicts in `neo4j_tools.py`:

```python
return {
    "from": {
        "id": from_b["id"],
        "name": from_b.get("name", ...),
        "latitude": from_b.get("latitude"),    # NEW
        "longitude": from_b.get("longitude")   # NEW
    },
    "to": {
        "id": to_b["id"],
        "name": to_b.get("name", ...),
        "latitude": to_b.get("latitude"),      # NEW
        "longitude": to_b.get("longitude")     # NEW
    },
    ...
}
```

### Test Result

```
FROM: IMIQ Project Building
  lat: 52.141220062856185
  lon: 11.65497609511592

TO: Mensa / OvGU Sports Center (SPOZ)
  lat: 52.13946521407472
  lon: 11.6472895960172
```

Now routes use the correct coordinates from the resolved buildings.

---

*Last Updated: February 2, 2026*
