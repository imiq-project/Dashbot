"""
FastAPI REST server for the Magdeburg Campus Assistant.
Provides HTTP endpoints for chat, text-to-speech, route map building, and dialogue management.
Handles streaming responses and integrates with the multi-agent orchestrator system.
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from io import BytesIO
import os
import json
import asyncio
import re
import threading
import time
from elevenlabs.client import ElevenLabs
import APP
from APP import (
    chat_optimized,
    SmartToolRouter,
    ParallelToolExecutor,
    KnowledgeBase,
    TOOLS,
    KNOWLEDGE_DIR,
    neo4j_graph,
    fiware_client,
    ors_client,
    TOOL_DESCRIPTIONS,
    execute_tool_call
)

from agents.dialogue_manager import (
    DialogueManager,
    DialogueState,
    DialoguePhase,
    ResponseType
)
from services.coordinate_resolver import get_coordinates, search_buildings, initialize_resolver as init_coord_resolver

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "b8gbDO0ybjX1VA89pBdX")
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

print("🚀 Starting Magdeburg Assistant API v4.5 (Proactive Conversational Flow)...")

print("🔊 Initializing ElevenLabs TTS...")
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

print("🔧 Setting up tool router...")
tool_router = SmartToolRouter(
    tools=TOOLS,
    model_name=EMBEDDING_MODEL,
    tool_descriptions=TOOL_DESCRIPTIONS
)

print("📚 Loading knowledge base...")
knowledge_base = KnowledgeBase(
    KNOWLEDGE_DIR,
    tool_router.embedder,
    model_name=EMBEDDING_MODEL
)

import APP
APP.knowledge_base = knowledge_base

print("⚡ Setting up parallel executor...")
parallel_executor = ParallelToolExecutor(max_workers=5)

print("🧠 Initializing semantic coordinate resolver...")
init_coord_resolver(neo4j_graph, ors_client)

conversations: Dict[str, List[Dict]] = {}
_conversations_lock = threading.Lock()

dialogue_states: Dict[str, DialogueState] = {}
_dialogue_states_lock = threading.Lock()

_dialogue_manager: Optional[DialogueManager] = None
_dialogue_manager_lock = threading.Lock()


def get_dialogue_manager():
    global _dialogue_manager
    with _dialogue_manager_lock:
        if _dialogue_manager is None:
            try:
                from orchestrator import create_orchestrator
                from openai import OpenAI
                import config

                llm_client = OpenAI(
                    api_key=config.OPENAI_API_KEY,
                    base_url=config.OPENAI_BASE_URL
                )

                orchestrator = create_orchestrator(
                    llm_client=llm_client,
                    neo4j_graph=neo4j_graph,
                    fiware_client=fiware_client,
                    ors_client=ors_client,
                    verbose=False
                )

                _dialogue_manager = DialogueManager(orchestrator, verbose=True)
                print("✅ Dialogue manager initialized")
            except Exception as e:
                print(f"⚠️ Could not initialize dialogue manager: {e}")
                _dialogue_manager = None

    return _dialogue_manager


def get_dialogue_state(session_id: str) -> DialogueState:
    with _dialogue_states_lock:
        if session_id not in dialogue_states:
            dialogue_states[session_id] = DialogueState()
        return dialogue_states[session_id]


def reset_dialogue_state(session_id: str) -> None:
    with _dialogue_states_lock:
        if session_id in dialogue_states:
            dialogue_states[session_id].reset()
        else:
            dialogue_states[session_id] = DialogueState()

captured_tool_params: Dict[str, Dict[str, Any]] = {}
_captured_tool_lock = threading.Lock()

def capture_tool_call(session_id: str, tool_name: str, arguments: dict):
    with _captured_tool_lock:
        if session_id not in captured_tool_params:
            captured_tool_params[session_id] = {}
        captured_tool_params[session_id][tool_name] = arguments
    print(f"   📦 Captured {tool_name}: {arguments}")

def get_captured_tools(session_id: str) -> Dict[str, Any]:
    with _captured_tool_lock:
        return captured_tool_params.get(session_id, {})

def clear_captured_tools(session_id: str):
    with _captured_tool_lock:
        if session_id in captured_tool_params:
            captured_tool_params[session_id] = {}

_original_execute_tool_call = execute_tool_call
_current_session_id = "default"

def wrapped_execute_tool_call(tool_name: str, arguments: dict) -> str:
    global _current_session_id

    if tool_name in ['get_mobility', 'get_building', 'get_transit_info', 'get_landmark_info', 'query_campus_sensors', 'get_weather_forecast']:
        capture_tool_call(_current_session_id, tool_name, arguments)

    return _original_execute_tool_call(tool_name, arguments)

APP.execute_tool_call = wrapped_execute_tool_call

print("✅ API Ready!")

app = FastAPI(
    title="Magdeburg Assistant API",
    description="AI Assistant for OVGU Campus and Magdeburg City - Proactive Conversational Flow",
    version="4.5.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

SESSION_TIMEOUT_SECONDS = 1800  # 30 minutes of inactivity → auto-cleanup
_session_last_active: Dict[str, float] = {}
_session_active_lock = threading.Lock()


def _touch_session(session_id: str) -> None:
    """Update last-active timestamp for a session."""
    with _session_active_lock:
        _session_last_active[session_id] = time.time()


def _auto_cleanup_sessions() -> None:
    """Remove sessions inactive for longer than SESSION_TIMEOUT_SECONDS."""
    now = time.time()
    with _session_active_lock:
        expired = [
            sid for sid, last in _session_last_active.items()
            if now - last > SESSION_TIMEOUT_SECONDS
        ]
    for sid in expired:
        _destroy_session(sid)
        with _session_active_lock:
            _session_last_active.pop(sid, None)
    if expired:
        print(f"🧹 Auto-cleaned {len(expired)} expired session(s)")


async def _cleanup_loop():
    """Background loop that runs auto-cleanup every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        _auto_cleanup_sessions()


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_cleanup_loop())


class UserLocation(BaseModel):
    lat: float
    lon: float

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    language: Optional[str] = "en"
    stream: Optional[bool] = True
    user_location: Optional[UserLocation] = None
    conversational: Optional[bool] = True

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None


def decode_polyline(encoded: str) -> List[List[float]]:
    if not encoded:
        return []

    decoded = []
    i = 0
    lat = 0
    lng = 0

    while i < len(encoded):
        shift = 0
        result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else result >> 1
        lat += dlat

        shift = 0
        result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if result & 1 else result >> 1
        lng += dlng

        decoded.append([lat / 1e5, lng / 1e5])

    return decoded


def get_route_geometry_from_ors(start_coords: tuple, end_coords: tuple, profile: str) -> Optional[Dict]:
    try:
        route = ors_client.get_route(start_coords, end_coords, profile)

        if not route or not route.get("success"):
            return None

        geometry = route.get("geometry", {})

        if isinstance(geometry, str):
            coords = decode_polyline(geometry)
        elif isinstance(geometry, dict):
            if geometry.get("type") == "LineString":
                coords = [[c[1], c[0]] for c in geometry.get("coordinates", [])]
            elif "coordinates" in geometry:
                coords = [[c[1], c[0]] for c in geometry.get("coordinates", [])]
            else:
                coords = []
        else:
            coords = []

        if coords:
            print(f"   ✅ ORS {profile}: {len(coords)} points")
            return {
                "coordinates": coords,
                "distance": route.get("distance"),
                "duration": route.get("duration"),
            }

        return None

    except Exception as e:
        print(f"   ❌ ORS error for {profile}: {e}")
        return None


def get_transit_segment_coords(from_stop: str, to_stop: str, line: str) -> List[List[float]]:
    try:
        query = """
        MATCH path = (start:Stop)-[:NEXT_STOP*]->(end:Stop)
        WHERE start.name CONTAINS $from_stop
          AND end.name CONTAINS $to_stop
          AND ALL(r IN relationships(path) WHERE r.line = $line)
        WITH path, length(path) as pathLength
        ORDER BY pathLength ASC
        LIMIT 1
        UNWIND nodes(path) as stop
        RETURN stop.latitude as lat, stop.longitude as lng
        """

        with neo4j_graph.driver.session(database=neo4j_graph.database) as session:
            result = session.run(query, from_stop=from_stop, to_stop=to_stop, line=line)
            coords = []
            for record in result:
                if record["lat"] and record["lng"]:
                    coords.append([record["lat"], record["lng"]])

            if coords:
                print(f"   ✅ Transit {line}: {len(coords)} stops")
            return coords

    except Exception as e:
        print(f"   ⚠️ Transit segment error: {e}")
        return []


def get_transit_route_geometry(origin: str, destination: str) -> Optional[Dict]:
    try:
        transit_data = neo4j_graph.get_multimodal_route(origin, destination)

        if not transit_data or not transit_data.get("success"):
            return None

        route = transit_data.get("route", {})
        segments = route.get("segments", [])

        transit_segments = []

        for segment in segments:
            if segment.get("type") == "transit":
                segment_coords = get_transit_segment_coords(
                    segment.get("from", ""),
                    segment.get("to", ""),
                    segment.get("line", "")
                )

                if segment_coords:
                    line_info = neo4j_graph.get_line_info(segment.get("line", ""))
                    line_color = "#ff6b6b"
                    if line_info.get("success") and line_info.get("line"):
                        line_color = line_info["line"].get("color", "#ff6b6b")

                    transit_segments.append({
                        "line": segment.get("line"),
                        "color": line_color,
                        "coordinates": segment_coords,
                        "from": segment.get("from"),
                        "to": segment.get("to"),
                        "stops": segment.get("stops", []),
                        "stopCount": segment.get("stop_count", len(segment.get("stops", [])))
                    })

        if not transit_segments:
            return None

        return {
            "segments": transit_segments,
            "lines": route.get("lines_used", []),
            "totalStops": route.get("total_stops", 0),
            "transfers": route.get("transfers", 0),
            "duration": route.get("estimated_duration_text")
        }

    except Exception as e:
        print(f"   ❌ Transit geometry error: {e}")
        return None


def get_coordinates_from_neo4j(location_name: str) -> Optional[tuple]:
    if not location_name:
        return None

    print(f"   🔍 Semantic lookup: '{location_name}'")

    coords = get_coordinates(location_name)

    if coords:
        return coords

    print(f"   ❌ Not found: {location_name}")
    return None


def build_route_map_data(origin: str, destination: str) -> Optional[Dict]:
    print(f"\n🗺️ Building route map: {origin} → {destination}")

    origin_coords = get_coordinates_from_neo4j(origin)
    dest_coords = get_coordinates_from_neo4j(destination)

    if not origin_coords:
        print(f"   ❌ Origin not found: {origin}")
        return None

    if not dest_coords:
        print(f"   ❌ Destination not found: {destination}")
        return None

    start_latlng = [origin_coords[1], origin_coords[0]]
    end_latlng = [dest_coords[1], dest_coords[0]]

    routes = {}

    walking = get_route_geometry_from_ors(origin_coords, dest_coords, "walking")
    if walking:
        routes["walking"] = {**walking, "color": "#00ff88"}

    cycling = get_route_geometry_from_ors(origin_coords, dest_coords, "cycling")
    if cycling:
        routes["cycling"] = {**cycling, "color": "#00ccff"}

    driving = get_route_geometry_from_ors(origin_coords, dest_coords, "driving")
    if driving:
        routes["driving"] = {**driving, "color": "#ffaa00"}

    transit = get_transit_route_geometry(origin, destination)
    if transit:
        routes["transit"] = transit

    if not routes:
        print("   ⚠️ No routes available")
        return None

    print(f"   ✅ Route map ready: {list(routes.keys())}")

    return {
        "type": "multimodal_route",
        "start": start_latlng,
        "end": end_latlng,
        "startName": origin,
        "endName": destination,
        "routes": routes,
        "defaultMode": "walking" if "walking" in routes else list(routes.keys())[0]
    }


def build_location_map(location_name: str) -> Optional[Dict]:
    print(f"\n📍 Building location map: {location_name}")

    coords = get_coordinates_from_neo4j(location_name)

    if not coords:
        return None

    info = get_location_info(location_name)

    return {
        "type": "location",
        "location": [coords[1], coords[0]],
        "name": info.get("name", location_name),
        "zoom": 17,
        "info": info
    }


def get_location_info(location_name: str) -> Dict:
    try:
        results = search_buildings(location_name, top_k=1)

        if results:
            best = results[0]
            return {
                "name": best["name"],
                "id": best["id"],
                "function": best["function"],
                "type": "Building",
                "score": best["score"]
            }

        coords = get_coordinates(location_name)
        if coords:
            with neo4j_graph.driver.session(database=neo4j_graph.database) as session:
                result = session.run("""
                    MATCH (s:Stop)
                    WHERE s.longitude = $lon AND s.latitude = $lat
                    RETURN s.name as name, s.lines as lines
                    LIMIT 1
                """, lon=coords[0], lat=coords[1])
                record = result.single()
                if record:
                    return {
                        "name": record["name"],
                        "type": "Stop",
                        "lines": record.get("lines", [])
                    }

        return {"name": location_name}

    except Exception as e:
        print(f"   ⚠️ Error getting location info: {e}")
        return {"name": location_name}


def extract_sensor_data(response_text: str, entity_type: str, location: str) -> Optional[Dict]:
    import re

    sensor_data = {
        "sensor_type": entity_type.lower() if entity_type else "info",
        "location": location,
        "entity_type": entity_type
    }

    if entity_type == "ParkingSpot" or "parking" in response_text.lower():
        parking_matches = re.findall(r'(\w+(?:\s+\w+)?)\s+has\s+(\d+)\s+free\s+space', response_text.lower())

        if parking_matches:
            total_free = 0
            total_capacity = 0
            for match in parking_matches:
                total_free += int(match[1])

            capacity_matches = re.findall(r'out of\s+(\d+)', response_text.lower())
            if capacity_matches:
                total_capacity = sum(int(c) for c in capacity_matches)
            else:
                total_capacity = 60

            sensor_data["availableSpotNumber"] = total_free
            sensor_data["totalSpotNumber"] = total_capacity
            sensor_data["sensor_type"] = "parking"
            return sensor_data

        free_match = re.search(r'(\d+)\s*(?:free|available)\s*(?:parking)?\s*(?:spaces?|spots?)?', response_text.lower())
        total_match = re.search(r'(?:out of|total of|capacity of)\s*(\d+)', response_text.lower())

        if free_match:
            sensor_data["availableSpotNumber"] = int(free_match.group(1))
            sensor_data["totalSpotNumber"] = int(total_match.group(1)) if total_match else 20
            sensor_data["sensor_type"] = "parking"
            return sensor_data

    if entity_type == "WeatherObserved" or "weather" in response_text.lower() or "temperature" in response_text.lower():
        temp_patterns = [
            r'temperature[:\s]+(-?\d+\.?\d*)',
            r'(-?\d+\.?\d*)°C',
            r'temperatures?\s+(?:of\s+)?(-?\d+\.?\d*)',
            r'(-?\d+\.?\d*)\s*degrees',
        ]

        temp = None
        for pattern in temp_patterns:
            temp_match = re.search(pattern, response_text, re.IGNORECASE)
            if temp_match:
                temp = float(temp_match.group(1))
                break

        humidity_patterns = [
            r'humidity[:\s]+(\d+)',
            r'(\d+)%\s*humidity',
            r'humidity\s+(?:of\s+)?(\d+)',
        ]

        humidity = None
        for pattern in humidity_patterns:
            humidity_match = re.search(pattern, response_text, re.IGNORECASE)
            if humidity_match:
                humidity = int(humidity_match.group(1))
                break

        wind_match = re.search(r'wind[:\s]+(\d+\.?\d*)', response_text, re.IGNORECASE)

        if temp is not None or humidity is not None:
            if temp is not None:
                sensor_data["temperature"] = temp
            if humidity is not None:
                sensor_data["relativeHumidity"] = humidity
            if wind_match:
                sensor_data["windSpeed"] = float(wind_match.group(1))
            sensor_data["sensor_type"] = "weather"
            return sensor_data

    if entity_type == "Traffic" or "traffic" in response_text.lower():
        if "clear" in response_text.lower() or "free" in response_text.lower():
            sensor_data["congestionLevel"] = "free"
        elif "moderate" in response_text.lower() or "medium" in response_text.lower():
            sensor_data["congestionLevel"] = "moderate"
        elif "heavy" in response_text.lower() or "congested" in response_text.lower():
            sensor_data["congestionLevel"] = "heavy"

        delay_match = re.search(r'(\d+)\s*(?:min|minute)', response_text.lower())
        if delay_match:
            sensor_data["expectedDelay"] = int(delay_match.group(1))

        if "congestionLevel" in sensor_data:
            sensor_data["sensor_type"] = "traffic"
            return sensor_data

    return None


async def generate_streaming_response(user_message: str, session_id: str, conversational: bool = True):
    global _current_session_id

    _touch_session(session_id)

    try:
        if session_id not in conversations:
            conversations[session_id] = []

        conversation_history = conversations[session_id]

        _current_session_id = session_id
        clear_captured_tools(session_id)

        if conversational:
            dialogue_mgr = get_dialogue_manager()

            if dialogue_mgr and dialogue_mgr.orchestrator:
                print(f"\n💬 Using conversational mode for session: {session_id}")

                orchestrator = dialogue_mgr.orchestrator
                conv_context = orchestrator._get_conversation_context(session_id)
                router_output = orchestrator.router_agent.parse_query(
                    user_message,
                    conversation_context=conv_context
                )

                print(f"   🧭 Intent: {router_output.primary_intent}")
                print(f"   📋 Dialogue action: {router_output.raw_output.get('dialogue_action', 'N/A')}")
                print(f"   ❓ Missing: {router_output.raw_output.get('missing_entities', [])}")

                dialogue_response = dialogue_mgr.process_turn(
                    session_id,
                    user_message,
                    router_output
                )

                print(f"   💬 Response type: {dialogue_response.response_type.value}")
                print(f"   🚀 Should execute: {dialogue_response.should_execute}")

                if not dialogue_response.should_execute:
                    print(f"   ❓ Asking clarification question...")

                    response_text = dialogue_response.text
                    words = response_text.split()
                    for i, word in enumerate(words):
                        token = word if i == len(words) - 1 else word + " "
                        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                        await asyncio.sleep(0.04)

                    state = get_dialogue_state(session_id)
                    dialogue_info = {
                        "response_type": dialogue_response.response_type.value,
                        "dialogue_phase": state.phase.value if state else None,
                        "choices": dialogue_response.choices,
                        "proactive_info": dialogue_response.proactive_info
                    }
                    yield f"data: {json.dumps({'type': 'dialogue_info', 'content': dialogue_info})}\n\n"

                    conversations[session_id].append({
                        "role": "user",
                        "content": user_message
                    })
                    conversations[session_id].append({
                        "role": "assistant",
                        "content": response_text
                    })

                    yield f"data: {json.dumps({'type': 'done', 'message': 'Stream complete'})}\n\n"
                    return

                print(f"   🚀 Executing with orchestrator...")

                result = orchestrator.process_query(user_message, session_id=session_id)
                response_text = result

                state = get_dialogue_state(session_id)
                proactive_info = dialogue_response.proactive_info

                map_data = None
                entities = router_output.entities

                if router_output.primary_intent in ["find_route", "get_route"]:
                    origin = entities.get("origin")
                    destination = entities.get("destination")
                    if origin and destination:
                        map_data = build_route_map_data(origin, destination)
                elif entities.get("location") or entities.get("building_name"):
                    location = entities.get("location") or entities.get("building_name")
                    if location:
                        map_data = build_location_map(location)

                words = response_text.split()
                for i, word in enumerate(words):
                    token = word if i == len(words) - 1 else word + " "
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                    await asyncio.sleep(0.04)

                if map_data:
                    print(f"   📤 Sending map data to frontend")
                    yield f"data: {json.dumps({'type': 'map_data', 'content': map_data})}\n\n"

                if proactive_info and proactive_info.get("weather"):
                    weather = proactive_info["weather"]
                    sensor_data = {
                        "sensor_type": "weather",
                        "temperature": weather.get("temperature"),
                        "conditions": weather.get("conditions"),
                        "proactive": True
                    }
                    yield f"data: {json.dumps({'type': 'sensor_data', 'content': sensor_data})}\n\n"

                dialogue_info = {
                    "response_type": "answer",
                    "dialogue_phase": state.phase.value if state else None,
                    "choices": None,
                    "proactive_info": proactive_info
                }
                yield f"data: {json.dumps({'type': 'dialogue_info', 'content': dialogue_info})}\n\n"

                yield f"data: {json.dumps({'type': 'done', 'message': 'Stream complete'})}\n\n"
                return
            else:
                print("   ⚠️ Dialogue manager not available, falling back to standard mode")

        response_text, updated_history = chat_optimized(
            user_message=user_message,
            conversation_history=conversation_history,
            tool_router=tool_router,
            parallel_executor=parallel_executor
        )

        conversations[session_id] = updated_history

        map_data = None
        sensor_data = None
        captured = get_captured_tools(session_id)

        print(f"\n📦 Captured tools: {list(captured.keys())}")

        if 'get_mobility' in captured:
            params = captured['get_mobility']
            origin = params.get('origin')
            destination = params.get('destination')
            if origin and destination:
                map_data = build_route_map_data(origin, destination)

        elif 'get_building' in captured:
            params = captured['get_building']
            building_id = params.get('building_id')
            search_query = params.get('search_query')
            location = building_id or search_query
            if location:
                if building_id:
                    location = f"Building {building_id}"
                map_data = build_location_map(location)

        elif 'get_transit_info' in captured:
            params = captured['get_transit_info']
            if params.get('query_type') == 'stop':
                stop_name = params.get('stop_name')
                if stop_name:
                    map_data = build_location_map(stop_name)

        elif 'get_landmark_info' in captured:
            params = captured['get_landmark_info']
            landmark_name = params.get('landmark_name')
            if landmark_name:
                map_data = build_location_map(landmark_name)

        elif 'query_campus_sensors' in captured:
            params = captured['query_campus_sensors']
            entity_type = params.get('entity_type', '')
            location = params.get('location', '')

            sensor_data = extract_sensor_data(response_text, entity_type, location)

        elif 'get_weather_forecast' in captured:
            sensor_data = extract_sensor_data(response_text, 'WeatherObserved', 'Magdeburg')

        words = response_text.split()
        for i, word in enumerate(words):
            token = word if i == len(words) - 1 else word + " "
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            await asyncio.sleep(0.04)

        if map_data:
            print(f"   📤 Sending map data to frontend")
            yield f"data: {json.dumps({'type': 'map_data', 'content': map_data})}\n\n"

        if sensor_data:
            print(f"   📤 Sending sensor data to frontend: {sensor_data.get('sensor_type')}")
            yield f"data: {json.dumps({'type': 'sensor_data', 'content': sensor_data})}\n\n"

        state = get_dialogue_state(session_id)
        dialogue_info = {
            "response_type": "answer",
            "dialogue_phase": state.phase.value if state else None,
            "choices": None
        }
        yield f"data: {json.dumps({'type': 'dialogue_info', 'content': dialogue_info})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'message': 'Stream complete'})}\n\n"

    except Exception as e:
        print(f"❌ Streaming error: {e}")
        import traceback
        traceback.print_exc()
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'message': 'Stream complete'})}\n\n"


def find_nearest_stop_to_coords(lat: float, lon: float) -> Optional[Dict]:
    try:
        with neo4j_graph.driver.session(database=neo4j_graph.database) as session:
            result = session.run("""
                MATCH (s:Stop)
                RETURN s.name as name,
                       coalesce(s.latitude, s.lat) as latitude,
                       coalesce(s.longitude, s.lon) as longitude
                LIMIT 5
            """)

            records = list(result)
            if records and records[0]["latitude"] is not None:
                query_result = session.run("""
                    MATCH (s:Stop)
                    WHERE coalesce(s.latitude, s.lat) IS NOT NULL
                    WITH s,
                         point({latitude: coalesce(s.latitude, s.lat),
                                longitude: coalesce(s.longitude, s.lon)}) as stopPoint,
                         point({latitude: $lat, longitude: $lon}) as userPoint
                    WITH s, point.distance(stopPoint, userPoint) as distance
                    ORDER BY distance
                    LIMIT 1
                    RETURN s.name as name, distance
                """, lat=lat, lon=lon)

                record = query_result.single()
                if record:
                    print(f"   📍 Found nearest stop via spatial query: {record['name']} ({int(record['distance'])}m)")
                    return {
                        "name": record["name"],
                        "distance": int(record["distance"])
                    }

            print("   📍 Stops don't have coordinates, using geocoding fallback")

            major_stops = [
                "Magdeburg Hauptbahnhof",
                "Magdeburg Alter Markt",
                "Magdeburg Hasselbachplatz",
                "Magdeburg Universität",
                "Magdeburg Universitätsbibliothek",
                "Magdeburg City Carré",
                "Magdeburg Reform"
            ]

            closest = None
            min_distance = float('inf')

            for stop_name in major_stops:
                stop_coords = get_coordinates(stop_name)
                if stop_coords:
                    import math
                    R = 6371000
                    lat1, lon1 = math.radians(lat), math.radians(lon)
                    lat2, lon2 = math.radians(stop_coords[1]), math.radians(stop_coords[0])

                    dlat = lat2 - lat1
                    dlon = lon2 - lon1

                    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                    c = 2 * math.asin(math.sqrt(a))
                    distance = R * c

                    if distance < min_distance:
                        min_distance = distance
                        closest = {"name": stop_name, "distance": int(distance)}

            if closest:
                print(f"   📍 Found nearest stop via geocoding fallback: {closest['name']} ({closest['distance']}m)")
            return closest

    except Exception as e:
        print(f"   ⚠️ Error finding nearest stop: {e}")
        import traceback
        traceback.print_exc()

    return None


def is_route_question_without_origin(message: str) -> bool:
    message_lower = message.lower()

    route_keywords = [
        "how do i get to", "how to get to", "how can i get to",
        "how can i go to", "how do i go to",
        "directions to", "route to", "way to",
        "how far is", "distance to",
        "take me to", "navigate to",
        "get to", "go to"
    ]

    origin_keywords = [
        "from", "starting from", "starting at",
        "i'm at", "im at", "i am at",
        "currently at", "at the"
    ]

    has_route_keyword = any(kw in message_lower for kw in route_keywords)
    has_origin = any(kw in message_lower for kw in origin_keywords)

    return has_route_keyword and not has_origin


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("templates/index.html") as f:
        return f.read()

@app.get("/api/status")
async def api_status():
    return {
        "status": "online",
        "version": "4.5.0",
        "features": ["llm_map_building", "proactive_conversation", "dialogue_manager"]
    }

@app.get("/health")
async def health():
    neo4j_ok = neo4j_graph.test_connection()
    dialogue_mgr = get_dialogue_manager()
    return {
        "status": "healthy" if neo4j_ok else "degraded",
        "neo4j": "connected" if neo4j_ok else "disconnected",
        "dialogue_manager": "ready" if dialogue_mgr else "unavailable",
        "version": "4.5.0"
    }

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    session_id = request.session_id or "default"

    nearest_stop = None
    if request.user_location:
        loc = request.user_location
        print(f"📍 User location: {loc.lat}, {loc.lon}")
        nearest_stop = find_nearest_stop_to_coords(loc.lat, loc.lon)
        if nearest_stop:
            print(f"📍 Nearest stop: {nearest_stop['name']} ({nearest_stop['distance']}m)")

    message = request.message
    if nearest_stop and is_route_question_without_origin(message):
        stop_name = nearest_stop['name'].replace("Magdeburg ", "")
        message = f"{message} (I'm currently near {stop_name})"
        print(f"📍 Modified message: {message}")

    conversational = request.conversational if request.conversational is not None else True

    print(f"\n{'='*60}")
    print(f"💬 User: {request.message}")
    if nearest_stop:
        print(f"📍 Location: near {nearest_stop['name']}")
    print(f"📱 Session: {session_id}")
    print(f"🗣️  Conversational mode: {conversational}")
    print(f"{'='*60}\n")

    try:
        if request.stream:
            return StreamingResponse(
                generate_streaming_response(message, session_id, conversational=conversational),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        else:
            global _current_session_id
            _current_session_id = session_id
            clear_captured_tools(session_id)

            if session_id not in conversations:
                conversations[session_id] = []

            if conversational:
                dialogue_mgr = get_dialogue_manager()

                if dialogue_mgr and dialogue_mgr.orchestrator:
                    orchestrator = dialogue_mgr.orchestrator
                    conv_context = orchestrator._get_conversation_context()
                    router_output = orchestrator.router_agent.parse_query(
                        message,
                        conversation_context=conv_context
                    )

                    dialogue_response = dialogue_mgr.process_turn(
                        session_id,
                        message,
                        router_output
                    )

                    state = get_dialogue_state(session_id)

                    if not dialogue_response.should_execute:
                        return {
                            "text": dialogue_response.text,
                            "session_id": session_id,
                            "type": dialogue_response.response_type.value,
                            "choices": dialogue_response.choices,
                            "dialogue_phase": state.phase.value if state else None,
                            "proactive_info": dialogue_response.proactive_info
                        }

                    response_text = orchestrator.process_query(message)

                    return {
                        "text": response_text,
                        "session_id": session_id,
                        "type": "answer",
                        "choices": None,
                        "dialogue_phase": state.phase.value if state else None,
                        "proactive_info": dialogue_response.proactive_info
                    }

            response_text, updated_history = chat_optimized(
                user_message=message,
                conversation_history=conversations[session_id],
                tool_router=tool_router,
                parallel_executor=parallel_executor
            )

            conversations[session_id] = updated_history

            state = get_dialogue_state(session_id)

            return {
                "text": response_text,
                "session_id": session_id,
                "type": "answer",
                "choices": None,
                "dialogue_phase": state.phase.value if state else None
            }

    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _destroy_session(session_id: str) -> None:
    """Remove ALL state for a session across every store."""
    with _conversations_lock:
        conversations.pop(session_id, None)
    with _dialogue_states_lock:
        dialogue_states.pop(session_id, None)
    with _captured_tool_lock:
        captured_tool_params.pop(session_id, None)

    # Clear orchestrator per-session history
    dialogue_mgr = get_dialogue_manager()
    if dialogue_mgr and dialogue_mgr.orchestrator:
        dialogue_mgr.orchestrator.reset_conversation(session_id)
    if dialogue_mgr:
        dialogue_mgr.states.pop(session_id, None)

    print(f"🗑️ Session '{session_id}' destroyed")


@app.post("/session/start")
async def session_start():
    """Call when the chat widget opens. Returns a unique session_id."""
    import uuid
    session_id = str(uuid.uuid4())
    with _conversations_lock:
        conversations[session_id] = []
    _touch_session(session_id)
    print(f"🆕 Session started: {session_id}")
    return {"session_id": session_id}


@app.post("/session/end")
async def session_end(session_id: str):
    """Call when the chat widget closes. Deletes all memory for this session."""
    _destroy_session(session_id)
    return {"status": "ok", "session_id": session_id}


@app.post("/chat/reset")
async def reset_chat(session_id: str = "default"):
    """Reset conversation but keep the session alive."""
    _destroy_session(session_id)
    with _conversations_lock:
        conversations[session_id] = []
    return {"status": "ok", "session_id": session_id}


@app.get("/chat/dialogue-state")
async def get_dialogue_state_endpoint(session_id: str = "default"):
    state = get_dialogue_state(session_id)
    return {
        "session_id": session_id,
        "phase": state.phase.value,
        "intent": state.intent,
        "gathered_info": state.gathered_info,
        "missing_info": state.missing_info,
        "turn_count": state.turn_count
    }

@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    try:
        audio_generator = elevenlabs_client.text_to_speech.convert(
            voice_id=request.voice_id or ELEVENLABS_VOICE_ID,
            text=request.text,
            model_id="eleven_turbo_v2_5"
        )

        audio_bytes = BytesIO()
        for chunk in audio_generator:
            audio_bytes.write(chunk)
        audio_bytes.seek(0)

        return StreamingResponse(audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/route")
async def test_route(origin: str, destination: str):
    map_data = build_route_map_data(origin, destination)
    return {"success": map_data is not None, "map_data": map_data}

@app.get("/location")
async def test_location(name: str):
    coords = get_coordinates_from_neo4j(name)
    if coords:
        return {"success": True, "name": name, "coords": {"lng": coords[0], "lat": coords[1]}}
    return {"success": False, "error": f"Not found: {name}"}

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting IMIQ API v4.5")
    print("   Proactive Conversational Flow + LLM-based map building")
    uvicorn.run("api:app", host="0.0.0.0", port=5000, reload=True)
