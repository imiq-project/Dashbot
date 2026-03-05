"""
Main application module for the Magdeburg Campus Assistant.
Provides the core chat functionality with tool routing and multi-agent orchestration.
Integrates FIWARE, Neo4j, OpenRouteService, and TomTom clients for campus information,
transit routing, weather, and mobility services.
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import string
import random
import requests
import re
import time
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from clients import FIWAREClient, TomTomClient, ORSClient
from tools import TOOLS, SYSTEM_PROMPT, ParallelToolExecutor, SmartToolRouter, TOOL_DESCRIPTIONS
from services import KnowledgeBase, resolve_campus_location, get_coordinates
from neo4j_tools import Neo4jTransitGraph
from config import (
    FIWARE_BASE_URL,
    FIWARE_API_KEY,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    NEO4J_URI,
    NEO4J_USERNAME,
    NEO4J_PASSWORD,
    NEO4J_DATABASE,
    ORS_API_KEY,
    ORS_BASE_URL,
    TOMTOM_API_KEY,
    TOMTOM_TIMEOUT,
    MODEL,
    KNOWLEDGE_DIR,
    MAX_CONVERSATION_HISTORY,
    MAX_TOOL_ITERATIONS,
    HTTP_TIMEOUT,
    MAGDEBURG_LAT,
    MAGDEBURG_LON,
    ENABLE_AGENTIC_MODE
)

from openai import OpenAI
__all__ = [
    'chat', 'chat_optimized', 'chat_agentic',
    'SmartToolRouter', 'ParallelToolExecutor', 'KnowledgeBase',
    'TOOLS', 'TOOL_DESCRIPTIONS', 'KNOWLEDGE_DIR',
    'neo4j_graph', 'fiware_client', 'ors_client', 'tomtom_client',
    'orchestrator'
]


client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
fiware_client = FIWAREClient(FIWARE_BASE_URL, FIWARE_API_KEY)
neo4j_graph = Neo4jTransitGraph(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)
tomtom_client = TomTomClient(TOMTOM_API_KEY, TOMTOM_TIMEOUT)
ors_client = ORSClient(ORS_API_KEY, ORS_BASE_URL, HTTP_TIMEOUT)

from services import initialize_resolver
initialize_resolver(neo4j_graph, ors_client, MAGDEBURG_LAT, MAGDEBURG_LON)

orchestrator = None

if ENABLE_AGENTIC_MODE:
    try:
        from orchestrator import create_orchestrator
        print("Initializing multi-agent orchestrator...")
        orchestrator = create_orchestrator(
            llm_client=client,
            neo4j_graph=neo4j_graph,
            fiware_client=fiware_client,
            ors_client=ors_client,
            tomtom_client=tomtom_client,
            verbose=False
        )
        print("Multi-agent mode ENABLED (with proactive context)")
    except Exception as e:
        print(f"  Failed to initialize orchestrator: {e}")
        print("   Falling back to traditional mode")
        orchestrator = None
else:
    print(" Multi-agent mode DISABLED (using traditional mode)")


def generate_tool_call_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=9))

def strip_thinking(text: str) -> str:
    if not text:
        return text
    return re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL).strip()

def parse_tool_calls_from_text(text: str) -> list:
    if not text:
        return []
    tool_calls = []
    pattern = r'<tool_call>\s*(\{.*?\})\s*(?:</tool_call>|$)'
    matches = re.findall(pattern, text, flags=re.DOTALL)
    for match in matches:
        try:
            data = json.loads(match)
            if "name" in data:
                tool_calls.append({
                    "id": generate_tool_call_id(),
                    "type": "function",
                    "function": {"name": data.get("name"), "arguments": json.dumps(data.get("arguments", {}))}
                })
        except json.JSONDecodeError:
            continue
    return tool_calls

def get_weather_forecast(days=3):
    WEATHER_CODES = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
        55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        80: "Slight rain showers", 81: "Moderate rain showers", 95: "Thunderstorm"
    }

    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": MAGDEBURG_LAT, "longitude": MAGDEBURG_LON,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode,precipitation_probability_max",
                "timezone": "Europe/Berlin", "forecast_days": max(1, min(days, 7))
            },
            timeout=HTTP_TIMEOUT
        )

        if response.status_code != 200:
            return json.dumps({"success": False, "error": "Weather service unavailable"})

        data = response.json()
        daily = data.get("daily", {})

        if not daily or not daily.get("time"):
            return json.dumps({"success": False, "error": "No forecast data"})

        forecasts = []
        for i in range(len(daily["time"])):
            date_obj = datetime.strptime(daily["time"][i], "%Y-%m-%d")
            forecasts.append({
                "date": daily["time"][i], "day": date_obj.strftime("%A"),
                "high": round(daily["temperature_2m_max"][i], 1),
                "low": round(daily["temperature_2m_min"][i], 1),
                "rain_chance": daily.get("precipitation_probability_max", [None])[i],
                "condition": WEATHER_CODES.get(daily["weathercode"][i], "Unknown")
            })

        return json.dumps({"success": True, "forecasts": forecasts}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


knowledge_base: KnowledgeBase = None

def execute_tool_call(tool_name: str, arguments: dict) -> str:
    global knowledge_base

    result = None

    try:
        if tool_name == "search_knowledge":
            query = arguments.get("query", "")
            if not query:
                result = json.dumps({"success": False, "error": "No query provided"})
            elif knowledge_base is None:
                result = json.dumps({"success": False, "error": "Knowledge base not initialized"})
            else:
                search_results = knowledge_base.search(query, top_k=3, threshold=0.20)
                print(f"   Knowledge search: '{query}' -> {len(search_results)} results")
                if search_results:
                    result = json.dumps({"success": True, "results": search_results, "query": query}, indent=2)
                else:
                    search_results = knowledge_base.search(query, top_k=3, threshold=0.15)
                    print(f"   Retry with lower threshold -> {len(search_results)} results")
                    if search_results:
                        result = json.dumps({"success": True, "results": search_results, "query": query}, indent=2)
                    else:
                        result = json.dumps({"success": False, "message": "No relevant information found", "query": query})

        elif tool_name == "get_mobility":
            origin = arguments.get("origin")
            destination = arguments.get("destination")
            modes = arguments.get("modes", ["walking", "cycling", "driving", "transit"])

            if not origin or not destination:
                result = json.dumps({"success": False, "error": "Both origin and destination required"})
            else:
                print(f"   Resolving locations...")
                origin_coords = get_coordinates(origin)
                dest_coords = get_coordinates(destination)
                traffic_info = None
                if origin_coords and dest_coords and "driving" in modes:
                    try:
                        print(f"   Checking traffic...")
                        traffic_check = tomtom_client.check_route_traffic(
                            (origin_coords[1], origin_coords[0]),
                            (dest_coords[1], dest_coords[0])
                        )
                        if traffic_check.get("success"):
                            traffic_info = traffic_check
                            traffic_delay = traffic_check.get("traffic_delay_minutes", 0)
                            print(f"   Traffic: {traffic_check.get('recommendation')} ({traffic_delay} min delay)")
                    except Exception as e:
                        print(f"   Traffic check failed: {e}")

                mobility_result = {"success": True, "origin": origin, "destination": destination, "options": {}}
                ors_modes = [m for m in modes if m in ["walking", "cycling", "driving"]]
                if ors_modes and origin_coords and dest_coords:
                    print(f"   Getting ORS routes...")
                    ors_routes = ors_client.get_multi_modal_routes(origin_coords, dest_coords, ors_modes)
                    for mode in ors_modes:
                        if mode in ors_routes and ors_routes[mode].get("success"):
                            r = ors_routes[mode]
                            option = {
                                "emoji": {"walking": "walking", "cycling": "cycling", "driving": "driving"}.get(mode, ""),
                                "distance": r["distance"],
                                "distance_meters": r["distance_meters"],
                                "duration": r["duration"],
                                "duration_seconds": r["duration_seconds"],
                                "available": True
                            }

                            if mode == "driving" and traffic_info:
                                traffic_delay = traffic_info.get("traffic_delay_minutes", 0)
                                option["traffic_delay_minutes"] = traffic_delay
                                option["traffic_status"] = traffic_info.get("recommendation", "unknown")
                                option["traffic_message"] = traffic_info.get("message", "")

                                base_duration_sec = r["duration_seconds"]
                                traffic_duration_sec = base_duration_sec + (traffic_delay * 60)

                                if traffic_duration_sec >= 3600:
                                    hours = int(traffic_duration_sec // 3600)
                                    mins = int((traffic_duration_sec % 3600) // 60)
                                    option["duration_with_traffic"] = f"{hours}h {mins}min"
                                else:
                                    option["duration_with_traffic"] = f"{int(traffic_duration_sec // 60)} min"

                                incidents = traffic_info.get("incidents", [])
                                if incidents:
                                    option["traffic_incidents"] = []
                                    for inc in incidents[:5]:
                                        option["traffic_incidents"].append({
                                            "type": inc.get("type", "unknown"),
                                            "description": inc.get("description", "Traffic incident"),
                                            "severity": inc.get("severity", "unknown"),
                                            "delay_minutes": inc.get("delay_minutes", 0),
                                            "location": inc.get("from", "") or inc.get("to", ""),
                                            "road": ", ".join(inc.get("road_numbers", [])) if inc.get("road_numbers") else ""
                                        })
                                    option["incident_count"] = traffic_info.get("incident_count", len(incidents))

                                route_data = traffic_info.get("route", {})
                                if route_data:
                                    option["traffic_details"] = {
                                        "tomtom_distance": route_data.get("distance", ""),
                                        "tomtom_travel_time": route_data.get("travel_time", ""),
                                        "departure_time": route_data.get("departure_time", ""),
                                        "arrival_time": route_data.get("arrival_time", ""),
                                        "has_significant_traffic": route_data.get("has_significant_traffic", False)
                                    }

                            mobility_result["options"][mode] = option
                        else:
                            mobility_result["options"][mode] = {"available": False, "error": ors_routes.get(mode, {}).get("error", "Not available")}

                if "transit" in modes:
                    print(f"   Getting transit route...")
                    try:
                        print(f"   DEBUG: Calling get_multimodal_route('{origin}', '{destination}')")
                        transit_data = neo4j_graph.get_multimodal_route(origin, destination)

                        print(f"   DEBUG: transit_data = {transit_data.get('success') if transit_data else 'None'}")
                        if transit_data and not transit_data.get("success"):
                            print(f"   DEBUG: Error: {transit_data.get('error', 'Unknown error')}")

                        if transit_data and transit_data.get("success"):
                            route_info = transit_data.get("route", {})
                            segments = route_info.get("segments", [])
                            lines_used = route_info.get("lines_used", [])
                            total_stops = route_info.get("total_stops", 0)
                            transfers = route_info.get("transfers", 0)

                            estimated_duration_min = route_info.get("estimated_duration_minutes")
                            estimated_duration_text = route_info.get("estimated_duration_text")

                            print(f"   DEBUG: estimated_duration_minutes = {estimated_duration_min}")
                            print(f"   DEBUG: estimated_duration_text = {estimated_duration_text}")
                            print(f"   DEBUG: total_stops = {total_stops}, transfers = {transfers}")
                            print(f"   DEBUG: segments = {len(segments)} segments")

                            transit_segments = [s for s in segments if s.get("type") == "transit"]
                            walking_segments = [s for s in segments if s.get("type") == "walking"]

                            transit_option = {
                                "emoji": "transit",
                                "available": True,
                                "total_stops": total_stops,
                                "transfers": transfers
                            }

                            if estimated_duration_min is not None:
                                transit_option["duration_minutes"] = estimated_duration_min
                                transit_option["estimated_duration"] = estimated_duration_text or f"{estimated_duration_min} min"

                            if walking_segments:
                                total_walk_dist = sum(s.get("distance_meters", 0) for s in walking_segments)
                                total_walk_time = sum(s.get("walk_time_minutes", 0) for s in walking_segments)
                                if total_walk_dist > 0:
                                    transit_option["walking_distance_meters"] = total_walk_dist
                                    transit_option["walking_time_minutes"] = total_walk_time

                            if transfers == 0 and transit_segments:
                                first_segment = transit_segments[0]
                                line_name = first_segment.get("line", lines_used[0] if lines_used else "Unknown")
                                stop_count = first_segment.get("stop_count", total_stops)
                                from_stop = first_segment.get("from")
                                to_stop = first_segment.get("to")

                                transit_option["type"] = "direct"
                                transit_option["line"] = line_name
                                transit_option["stops"] = stop_count
                                transit_option["from_stop"] = from_stop
                                transit_option["to_stop"] = to_stop

                                desc_parts = [f"Take {line_name}"]
                                if from_stop:
                                    desc_parts.append(f"from {from_stop}")
                                if to_stop:
                                    desc_parts.append(f"to {to_stop}")
                                desc_parts.append(f"({stop_count} stops)")

                                if walking_segments:
                                    final_walk = walking_segments[-1]
                                    walk_time = final_walk.get("walk_time_minutes", 0)
                                    walk_dist = final_walk.get("distance_meters", 0)
                                    if walk_time > 0:
                                        desc_parts.append(f"then walk {walk_time} min ({walk_dist}m)")

                                transit_option["description"] = " ".join(desc_parts)

                            elif transfers > 0:
                                transit_option["type"] = "transfer"
                                transit_option["lines"] = lines_used

                                if transit_segments:
                                    transit_option["from_stop"] = transit_segments[0].get("from")
                                    transit_option["to_stop"] = transit_segments[-1].get("to")

                                desc_parts = [f"{' -> '.join(lines_used)} ({total_stops} stops, {transfers} transfer{'s' if transfers > 1 else ''})"]

                                if walking_segments:
                                    total_walk_time = sum(s.get("walk_time_minutes", 0) for s in walking_segments)
                                    if total_walk_time > 0:
                                        desc_parts.append(f"+ {total_walk_time} min walk")

                                transit_option["description"] = " ".join(desc_parts)

                            if transit_data.get("from"):
                                transit_option["route_from"] = transit_data.get("from")
                            if transit_data.get("to"):
                                transit_option["route_to"] = transit_data.get("to")

                            mobility_result["options"]["transit"] = transit_option
                        else:
                            mobility_result["options"]["transit"] = {"available": False, "error": transit_data.get("error", "No route found") if transit_data else "Query failed"}
                    except Exception as e:
                        mobility_result["options"]["transit"] = {"available": False, "error": str(e)}

                available = {k: v for k, v in mobility_result["options"].items() if v.get("available")}
                if available:
                    fastest = min([(k, v.get("duration_seconds", float('inf'))) for k, v in available.items() if v.get("duration_seconds")], key=lambda x: x[1], default=(None, None))
                    if fastest[0]:
                        mobility_result["fastest"] = {"mode": fastest[0], "duration": available[fastest[0]]["duration"]}

                if traffic_info:
                    traffic_summary = {
                        "status": traffic_info.get("recommendation", "unknown"),
                        "delay_minutes": traffic_info.get("traffic_delay_minutes", 0),
                        "incident_count": traffic_info.get("incident_count", 0),
                        "message": traffic_info.get("message", "")
                    }

                    incidents = traffic_info.get("incidents", [])
                    if incidents:
                        traffic_summary["incidents_summary"] = []
                        for inc in incidents[:5]:
                            inc_desc = f"{inc.get('type', 'incident')}"
                            if inc.get("from"):
                                inc_desc += f" near {inc.get('from')}"
                            if inc.get("road_numbers"):
                                inc_desc += f" on {', '.join(inc.get('road_numbers', []))}"
                            if inc.get("delay_minutes", 0) > 0:
                                inc_desc += f" ({inc.get('delay_minutes')} min delay)"
                            traffic_summary["incidents_summary"].append(inc_desc)

                    mobility_result["traffic_info"] = traffic_summary

                    if traffic_info.get("traffic_delay_minutes", 0) > 10:
                        mobility_result["traffic_warning"] = traffic_info.get("message")
                        mobility_result["suggest_transit"] = True
                    elif traffic_info.get("traffic_delay_minutes", 0) > 5:
                        mobility_result["traffic_notice"] = f"Moderate traffic: {traffic_info.get('traffic_delay_minutes', 0)} min delay expected"

                result = json.dumps(mobility_result, indent=2)

        elif tool_name == "find_places":
            query_type = arguments.get("query_type", "search")
            place_type = arguments.get("place_type", "all")
            cuisine = arguments.get("cuisine")
            building_id = arguments.get("building_id")
            stop_name = arguments.get("stop_name")
            search_term = arguments.get("search_term")
            limit = arguments.get("limit", 5)

            print(f"   Finding places: {query_type}, type={place_type}, cuisine={cuisine}")

            places_result = neo4j_graph.find_places(
                query_type=query_type,
                place_type=place_type,
                cuisine=cuisine,
                building_id=building_id,
                stop_name=stop_name,
                search_term=search_term,
                limit=limit
            )

            if query_type == "mensa_menu" and places_result.get("success"):
                fiware_info = places_result.get("fiware_query", {})
                entity_id = fiware_info.get("entity_id")

                if entity_id:
                    print(f"   Fetching menu from FIWARE: {entity_id}")
                    try:
                        menu_data = fiware_client.get_entity_by_id(entity_id, attrs="todaysMenu")
                        if menu_data.get("success"):
                            entity = menu_data.get("entity", {})
                            todays_menu = entity.get("todaysMenu")

                            if isinstance(todays_menu, dict):
                                todays_menu = todays_menu.get("value", todays_menu)

                            if todays_menu:
                                places_result["todays_menu"] = todays_menu
                                print(f"   Got menu with {len(todays_menu) if isinstance(todays_menu, list) else 1} items")
                    except Exception as e:
                        print(f"   Menu fetch failed: {e}")
                        places_result["menu_error"] = str(e)

            result = json.dumps(places_result, indent=2, ensure_ascii=False)

        elif tool_name == "query_campus_sensors":
            entity_type = arguments.get("entity_type")
            location = arguments.get("location")

            print(f"   Querying sensors: {entity_type} at {location or 'all locations'}")

            query_params = {"entity_type": entity_type, "limit": 10}

            if entity_type == "Traffic":
                query_params["attrs"] = "intensity,congestionLevel,vehicleCount,pedestrians,cyclists,avgSpeed"
            elif entity_type == "AirQuality":
                query_params["attrs"] = "pm10,pm25,no2,o3"

            if location:
                sensor_type_map = {
                    "WeatherObserved": "WeatherObserved",
                    "ParkingSpot": "ParkingSpot",
                    "Traffic": "Traffic",
                    "Room": "Room",
                    "AirQuality": "AirQuality"
                }
                sensor_type = sensor_type_map.get(entity_type)

                sensor_info = neo4j_graph.get_sensor_for_location(location, sensor_type)

                if sensor_info and sensor_info.get("fiware_id"):
                    query_params["entity_id"] = sensor_info["fiware_id"]
                    print(f"   Found sensor via Neo4j: {sensor_info['fiware_id']}")
                else:
                    sensor_type_lower = {"WeatherObserved": "weather", "ParkingSpot": "parking",
                                        "Traffic": "traffic", "Room": "room", "AirQuality": "air"}.get(entity_type)
                    location_result = resolve_campus_location(location, sensor_types=[sensor_type_lower])

                    if isinstance(location_result, dict) and location_result.get("success"):
                        if location_result.get("entity_id"):
                            query_params["entity_id"] = location_result["entity_id"]
                        elif location_result.get("id_pattern"):
                            query_params["id_pattern"] = location_result["id_pattern"]

            data = fiware_client.query_entities(**query_params)
            result = json.dumps(data, indent=2)


        elif tool_name == "get_weather_forecast":
            result = get_weather_forecast(arguments.get("days", 3))

        elif tool_name == "get_building":
            query_type = arguments.get("query_type", "info")
            building_id = arguments.get("building_id")
            search_query = arguments.get("search_query")

            if query_type == "info" and building_id:
                data = neo4j_graph.get_building_info(building_id)
            elif query_type == "search" and search_query:
                data = neo4j_graph.find_building_by_function(search_query)
            elif query_type == "nearby" and building_id:
                data = neo4j_graph.get_nearby_buildings(building_id)
            else:
                data = {"success": False, "error": f"Invalid parameters for {query_type}"}
            result = json.dumps(data, indent=2)

        elif tool_name == "get_transit_info":
            query_type = arguments.get("query_type")
            if query_type == "stop":
                data = neo4j_graph.get_stop_info(arguments.get("stop_name", ""))
            elif query_type == "line":
                data = neo4j_graph.get_line_info(arguments.get("line_name", ""))
            elif query_type == "transfers":
                data = neo4j_graph.find_best_transfer_between_lines(arguments.get("line1", ""), arguments.get("line2", ""))
            elif query_type == "nearest_from_building":
                data = neo4j_graph.get_nearest_tram_from_building(arguments.get("building_id", ""))
            elif query_type == "transfer_hubs":
                data = neo4j_graph.find_transfer_hubs(min_lines=2, limit=10)
            else:
                data = {"success": False, "error": f"Unknown query_type: {query_type}"}
            result = json.dumps(data, indent=2)

        elif tool_name == "get_landmark_info":
            data = neo4j_graph.get_landmark_info(arguments.get("landmark_name", ""))
            result = json.dumps(data, indent=2)

        else:
            result = json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        print(f"   Tool execution error in {tool_name}: {e}")
        import traceback
        traceback.print_exc()
        result = json.dumps({"success": False, "error": str(e)})

    return result or json.dumps({"success": False, "error": "No result"})


def chat(user_message: str, conversation_history: list = None,
         tool_router: SmartToolRouter = None,
         parallel_executor: ParallelToolExecutor = None) -> tuple:

    if conversation_history is None:
        conversation_history = []

    if len(conversation_history) > MAX_CONVERSATION_HISTORY:
        conversation_history = conversation_history[-MAX_CONVERSATION_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    print(f"\n{'='*60}")
    print(f"[MONO-AGENT] User: {user_message}")
    print(f"{'='*60}")

    start_routing = time.time()
    relevant_tools, tool_scores = tool_router.get_relevant_tools(user_message, top_k=4)
    routing_time = time.time() - start_routing

    sorted_scores = sorted(tool_scores.items(), key=lambda x: -x[1])
    best_tool = sorted_scores[0][0] if sorted_scores else "none"
    max_score = sorted_scores[0][1] if sorted_scores else 0
    should_force_tools = max_score >= 0.25

    print(f"\n-- INTENT (embedding similarity) {'-'*28}")
    print(f"  Best match: {best_tool} ({max_score:.3f}) -> {'Tools required' if should_force_tools else 'Chat mode'}")
    print(f"  All scores:")
    for name, score in sorted_scores:
        print(f"    {name}: {score:.3f}")
    print(f"  Routing time: {routing_time*1000:.0f} ms")

    iteration = 0
    total_tool_calls = 0
    all_entities = {}
    final_response = ""
    total_start = time.time()
    tool_exec_total = 0.0

    while iteration < MAX_TOOL_ITERATIONS:
        iteration += 1

        try:
            if not relevant_tools or not should_force_tools:
                tool_choice_setting = None
                tools_to_send = None
            else:
                tool_choice_setting = "required" if iteration == 1 else "auto"
                tools_to_send = relevant_tools

            response = client.chat.completions.create(
                model=MODEL, messages=messages, tools=tools_to_send,
                tool_choice=tool_choice_setting, timeout=90
            )

        except Exception as e:
            print(f"API Error: {e}")
            return "Sorry, I encountered an error.", conversation_history

        assistant_message = response.choices[0].message

        native_tool_calls = assistant_message.tool_calls or []
        text_tool_calls = parse_tool_calls_from_text(assistant_message.content) if not native_tool_calls and assistant_message.content else []
        all_tool_calls = native_tool_calls or text_tool_calls

        if all_tool_calls:
            print(f"\n-- TOOL CALLS (iteration {iteration}) {'-'*24}")

            tool_calls_list = []
            for tc in all_tool_calls:
                if isinstance(tc, dict):
                    tool_calls_list.append(tc)
                else:
                    tool_calls_list.append({
                        "id": tc.id or generate_tool_call_id(),
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    })

            for tc in tool_calls_list:
                total_tool_calls += 1
                fn_name = tc["function"]["name"]
                fn_args = tc["function"]["arguments"]
                args_preview = fn_args[:80] + "..." if len(fn_args) > 80 else fn_args
                print(f"  {fn_name}({args_preview})")

                try:
                    parsed_args = json.loads(fn_args)
                    for k, v in parsed_args.items():
                        if v is not None and v != "":
                            all_entities[k] = v
                except (json.JSONDecodeError, TypeError):
                    pass

            messages.append({"role": "assistant", "content": assistant_message.content or "", "tool_calls": tool_calls_list})

            exec_start = time.time()
            import APP as _self_module
            tool_results = parallel_executor.execute_batch(tool_calls_list, _self_module.execute_tool_call)
            exec_time = time.time() - exec_start
            tool_exec_total += exec_time
            print(f"  Execution: {exec_time:.2f}s")

            messages.extend(tool_results)
            continue
        else:
            final_response = strip_thinking(assistant_message.content or "")
            final_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL).strip()
            break

    if not final_response:
        final_response = "I couldn't complete that request."

    total_time = time.time() - total_start

    if all_entities:
        print(f"\n-- ENTITIES (from tool args) {'-'*28}")
        for k, v in all_entities.items():
            val_str = str(v) if not isinstance(v, list) else ", ".join(str(x) for x in v)
            print(f"  {k:20s} {val_str}")

    print(f"\n-- RESPONSE {'-'*45}")
    print(f"  Length:  {len(final_response)} chars")
    preview = final_response[:80].replace('\n', ' ')
    print(f"  Preview: {preview}{'...' if len(final_response) > 80 else ''}")

    print(f"\n-- LATENCY {'-'*46}")
    print(f"  Routing:        {routing_time*1000:>6.0f} ms")
    print(f"  Tool execution: {tool_exec_total*1000:>6.0f} ms  ({iteration} iteration(s), {total_tool_calls} tool call(s))")
    print(f"  Total:          {total_time*1000:>6.0f} ms")
    print(f"{'='*60}")

    conversation_history.append({"role": "user", "content": user_message})
    conversation_history.append({"role": "assistant", "content": final_response})

    return final_response, conversation_history

chat_optimized = chat


def chat_agentic(user_message: str, conversation_history: list = None,
                 session_id: str = "cli_session") -> tuple:
    global orchestrator

    if orchestrator is None:
        print("Orchestrator not available, using traditional mode")
        return chat(user_message, conversation_history, tool_router, parallel_executor)

    if conversation_history is None:
        conversation_history = []

    if len(conversation_history) > MAX_CONVERSATION_HISTORY:
        conversation_history = conversation_history[-MAX_CONVERSATION_HISTORY:]

    try:
        response = orchestrator.process_query(user_message)

        print(f"\nAssistant: {response}")

        conversation_history.append({"role": "user", "content": user_message})
        conversation_history.append({"role": "assistant", "content": response})

        return response, conversation_history

    except Exception as e:
        print(f"Orchestrator error: {e}")
        import traceback
        traceback.print_exc()

        print("   Falling back to traditional mode...")
        return chat(user_message, conversation_history, tool_router, parallel_executor)


if __name__ == "__main__":
    print("=" * 60)
    print("MAGDEBURG ASSISTANT v4.0")
    print("=" * 60)

    print("\nInitializing...")

    print("Testing Neo4j...")
    if neo4j_graph.test_connection():
        print("Neo4j connected")
    else:
        print("Neo4j failed")

    print("Testing ORS...")
    try:
        test_coords = ors_client.geocode("Hauptbahnhof")
        if test_coords:
            print(f"ORS connected")
        else:
            print("ORS: geocoding returned no results")
    except Exception as e:
        print(f"ORS failed: {e}")

    tool_router = SmartToolRouter(
        tools=TOOLS,
        model_name="BAAI/bge-base-en-v1.5",
        tool_descriptions=TOOL_DESCRIPTIONS
    )

    knowledge_base = KnowledgeBase(KNOWLEDGE_DIR, tool_router.embedder, model_name=tool_router.model_name)
    parallel_executor = ParallelToolExecutor(max_workers=5)
    kb_stats = knowledge_base.get_stats()

    if orchestrator is not None:
        orchestrator.knowledge_base = knowledge_base
        print("Knowledge base attached to orchestrator")
    print("\n" + "=" * 60)
    print(f"Knowledge: {kb_stats['total_chunks']} chunks from {kb_stats['total_documents']} docs")
    print(f"Tools: {len(TOOLS)}")
    print("=" * 60)
    print("Ready! Type 'quit' to exit, 'debug <query>' to debug tool selection.\n")

    conversation_history = []

    try:
        while True:
            user_input = input("You: ").strip()

            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("Goodbye!")
                break

            if not user_input:
                continue

            if user_input.lower().startswith("debug "):
                query = user_input[6:]
                tool_router.debug_query(query)
                continue

            try:
                if ENABLE_AGENTIC_MODE and orchestrator:
                    response, conversation_history = chat_agentic(
                        user_input, conversation_history
                    )
                else:
                    response, conversation_history = chat(
                        user_input, conversation_history, tool_router, parallel_executor)
            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
                import traceback
                traceback.print_exc()

    finally:
        neo4j_graph.close()
        fiware_client.close()
        ors_client.close()
        tomtom_client.close()

        print("Connections closed.")
