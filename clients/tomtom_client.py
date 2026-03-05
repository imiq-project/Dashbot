"""
TomTom Traffic API client for real-time traffic data. Provides traffic flow, incidents, congestion levels, and traffic-aware driving routes with turn-by-turn directions.
"""

import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class TomTomClient:

    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.tomtom.com"

        self.session = requests.Session()
        self.session.params = {"key": api_key}

    def get_traffic_flow(self, lat: float, lon: float, zoom: int = 10) -> Dict:
        try:
            url = f"{self.base_url}/traffic/services/4/flowSegmentData/absolute/{zoom}/json"

            params = {
                "point": f"{lat},{lon}",
                "unit": "KMPH"
            }

            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                flow_data = data.get("flowSegmentData", {})

                current_speed = flow_data.get("currentSpeed", 0)
                free_flow_speed = flow_data.get("freeFlowSpeed", 0)
                current_travel_time = flow_data.get("currentTravelTime", 0)
                free_flow_travel_time = flow_data.get("freeFlowTravelTime", 0)
                confidence = flow_data.get("confidence", 0)
                road_closure = flow_data.get("roadClosure", False)

                if free_flow_speed > 0:
                    speed_ratio = current_speed / free_flow_speed
                    if speed_ratio >= 0.9:
                        congestion_level = "free"
                    elif speed_ratio >= 0.7:
                        congestion_level = "light"
                    elif speed_ratio >= 0.5:
                        congestion_level = "moderate"
                    elif speed_ratio >= 0.3:
                        congestion_level = "heavy"
                    else:
                        congestion_level = "severe"
                else:
                    congestion_level = "unknown"

                delay_seconds = current_travel_time - free_flow_travel_time
                delay_minutes = max(0, delay_seconds // 60)

                return {
                    "success": True,
                    "current_speed_kmh": current_speed,
                    "free_flow_speed_kmh": free_flow_speed,
                    "current_travel_time_sec": current_travel_time,
                    "free_flow_travel_time_sec": free_flow_travel_time,
                    "delay_minutes": delay_minutes,
                    "congestion_level": congestion_level,
                    "confidence": confidence,
                    "road_closure": road_closure,
                    "coordinates": {"lat": lat, "lon": lon}
                }
            else:
                return {
                    "success": False,
                    "error": f"TomTom API error: {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Traffic flow request failed: {str(e)}"
            }

    def get_traffic_incidents(self, bbox: Tuple[float, float, float, float]) -> Dict:
        try:
            min_lon, min_lat, max_lon, max_lat = bbox
            bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"

            url = f"{self.base_url}/traffic/services/5/incidentDetails"

            params = {
                "bbox": bbox_str,
                "fields": "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,events{description,code,iconCategory},startTime,endTime,from,to,length,delay,roadNumbers,timeValidity}}}",
                "language": "en-US",
                "categoryFilter": "0,1,2,3,4,5,6,7,8,9,10,11,14",
                "timeValidityFilter": "present"
            }

            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                incidents_list = []

                for incident in data.get("incidents", []):
                    props = incident.get("properties", {})
                    geometry = incident.get("geometry", {})

                    icon_category = props.get("iconCategory", 0)
                    incident_types = {
                        0: "unknown",
                        1: "accident",
                        2: "fog",
                        3: "dangerous_conditions",
                        4: "rain",
                        5: "ice",
                        6: "jam",
                        7: "lane_closed",
                        8: "road_closed",
                        9: "road_works",
                        10: "wind",
                        11: "flooding",
                        14: "broken_down_vehicle"
                    }
                    incident_type = incident_types.get(icon_category, "other")

                    events = props.get("events", [])
                    description = events[0].get("description", "Traffic incident") if events else "Traffic incident"

                    delay = props.get("delay") or 0
                    if delay < 60:
                        severity = "minor"
                    elif delay < 300:
                        severity = "moderate"
                    else:
                        severity = "major"

                    coords = geometry.get("coordinates", [[0, 0]])
                    if coords and len(coords) > 0:
                        lon, lat = coords[0]
                    else:
                        lon, lat = 0, 0

                    incidents_list.append({
                        "type": incident_type,
                        "description": description,
                        "severity": severity,
                        "delay_seconds": delay,
                        "delay_minutes": delay // 60,
                        "from": props.get("from", ""),
                        "to": props.get("to", ""),
                        "length_meters": props.get("length", 0),
                        "road_numbers": props.get("roadNumbers", []),
                        "location": {"lat": lat, "lon": lon}
                    })

                return {
                    "success": True,
                    "incident_count": len(incidents_list),
                    "incidents": incidents_list
                }
            else:
                return {
                    "success": False,
                    "error": f"TomTom API error: {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Traffic incidents request failed: {str(e)}"
            }

    def get_route_with_traffic(self, start_coords: Tuple[float, float],
                                end_coords: Tuple[float, float],
                                mode: str = "car") -> Dict:
        try:
            start_lat, start_lon = start_coords
            end_lat, end_lon = end_coords

            locations = f"{start_lat},{start_lon}:{end_lat},{end_lon}"

            url = f"{self.base_url}/routing/1/calculateRoute/{locations}/json"

            params = {
                "traffic": "true",
                "travelMode": mode,
                "routeType": "fastest",
                "departAt": "now"
            }

            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()

                if "routes" in data and len(data["routes"]) > 0:
                    route = data["routes"][0]
                    summary = route.get("summary", {})

                    distance_meters = summary.get("lengthInMeters", 0)
                    travel_time_sec = summary.get("travelTimeInSeconds", 0)
                    traffic_delay_sec = summary.get("trafficDelayInSeconds", 0)
                    departure_time = summary.get("departureTime", "")
                    arrival_time = summary.get("arrivalTime", "")

                    if distance_meters >= 1000:
                        distance_str = f"{distance_meters/1000:.1f} km"
                    else:
                        distance_str = f"{int(distance_meters)} m"

                    travel_time_min = travel_time_sec // 60
                    if travel_time_min >= 60:
                        hours = travel_time_min // 60
                        mins = travel_time_min % 60
                        time_str = f"{hours}h {mins}min"
                    else:
                        time_str = f"{travel_time_min} min"

                    traffic_delay_min = traffic_delay_sec // 60

                    has_traffic = traffic_delay_min > 5

                    return {
                        "success": True,
                        "distance": distance_str,
                        "distance_meters": distance_meters,
                        "travel_time": time_str,
                        "travel_time_seconds": travel_time_sec,
                        "traffic_delay_minutes": traffic_delay_min,
                        "has_significant_traffic": has_traffic,
                        "departure_time": departure_time,
                        "arrival_time": arrival_time,
                        "mode": mode
                    }
                else:
                    return {
                        "success": False,
                        "error": "No route found"
                    }
            else:
                return {
                    "success": False,
                    "error": f"TomTom Routing API error: {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Routing request failed: {str(e)}"
            }

    def get_driving_route_with_directions(
        self,
        start_coords: Tuple[float, float],
        end_coords: Tuple[float, float],
        max_steps: int = 6
    ) -> Dict:
        try:
            start_lat, start_lon = start_coords
            end_lat, end_lon = end_coords

            locations = f"{start_lat},{start_lon}:{end_lat},{end_lon}"
            url = f"{self.base_url}/routing/1/calculateRoute/{locations}/json"

            params = {
                "traffic": "true",
                "travelMode": "car",
                "routeType": "fastest",
                "instructionsType": "text",
                "language": "en-US",
                "routeRepresentation": "polyline",
                "computeTravelTimeFor": "all"
            }

            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()

                if "routes" not in data or len(data["routes"]) == 0:
                    return {"success": False, "error": "No route found"}

                route = data["routes"][0]
                summary = route.get("summary", {})

                distance_meters = summary.get("lengthInMeters", 0)
                travel_time_sec = summary.get("travelTimeInSeconds", 0)
                traffic_delay_sec = summary.get("trafficDelayInSeconds", 0)
                departure_time = summary.get("departureTime", "")
                arrival_time = summary.get("arrivalTime", "")

                if distance_meters >= 1000:
                    distance_str = f"{distance_meters/1000:.1f} km"
                else:
                    distance_str = f"{int(distance_meters)} m"

                travel_time_min = travel_time_sec // 60
                if travel_time_min >= 60:
                    hours = travel_time_min // 60
                    mins = travel_time_min % 60
                    duration_str = f"{hours}h {mins}min"
                else:
                    duration_str = f"{int(travel_time_min)} min"

                traffic_delay_min = traffic_delay_sec // 60

                guidance = route.get("guidance", {})
                instructions = guidance.get("instructions", [])

                directions = []
                streets_on_route = []

                for inst in instructions:
                    street = inst.get("street", "")
                    road_numbers = inst.get("roadNumbers", [])
                    message = inst.get("message", "")
                    maneuver = inst.get("maneuver", "")
                    point = inst.get("point", {})
                    distance_offset = inst.get("routeOffsetInMeters", 0)

                    step = {
                        "instruction": message,
                        "street": street,
                        "road_numbers": road_numbers,
                        "maneuver": maneuver,
                        "coordinates": {
                            "lat": point.get("latitude"),
                            "lon": point.get("longitude")
                        } if point else None,
                        "distance_from_start": distance_offset
                    }
                    directions.append(step)

                    if street and street not in streets_on_route:
                        streets_on_route.append(street)

                if len(directions) > max_steps:
                    simplified = [directions[0]]

                    major_maneuvers = ["TURN_RIGHT", "TURN_LEFT", "TAKE_EXIT",
                                       "ROUNDABOUT_RIGHT", "ROUNDABOUT_LEFT", "MAKE_UTURN"]
                    middle = [d for d in directions[1:-1] if d["maneuver"] in major_maneuvers]

                    simplified.extend(middle[:max_steps-2])

                    if directions[-1] not in simplified:
                        simplified.append(directions[-1])

                    directions = simplified

                directions_text = []
                for d in directions:
                    text = d["instruction"]
                    if d.get("street") and d["maneuver"] != "ARRIVE_RIGHT" and d["maneuver"] != "ARRIVE_LEFT" and d["maneuver"] != "ARRIVE":
                        pass
                    directions_text.append(text)

                if traffic_delay_min > 15:
                    traffic_status = "heavy_traffic"
                    traffic_message = f"Heavy traffic! Expect {traffic_delay_min} min delay."
                elif traffic_delay_min > 5:
                    traffic_status = "moderate_traffic"
                    traffic_message = f"Moderate traffic. Expect {traffic_delay_min} min delay."
                else:
                    traffic_status = "clear"
                    traffic_message = "Traffic is clear."

                return {
                    "success": True,
                    "source": "tomtom",
                    "distance": distance_str,
                    "distance_meters": distance_meters,
                    "duration": duration_str,
                    "duration_seconds": travel_time_sec,
                    "traffic_delay_minutes": traffic_delay_min,
                    "traffic_status": traffic_status,
                    "traffic_message": traffic_message,
                    "departure_time": departure_time,
                    "arrival_time": arrival_time,
                    "directions": directions,
                    "directions_text": directions_text,
                    "streets_on_route": streets_on_route,
                    "mode": "driving"
                }
            else:
                return {
                    "success": False,
                    "error": f"TomTom Routing API error: {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Driving route request failed: {str(e)}"
            }

    def check_route_traffic(self, start_coords: Tuple[float, float],
                           end_coords: Tuple[float, float]) -> Dict:
        try:
            route_data = self.get_route_with_traffic(start_coords, end_coords)

            if not route_data.get("success"):
                return route_data

            start_lat, start_lon = start_coords
            end_lat, end_lon = end_coords

            min_lat = min(start_lat, end_lat) - 0.01
            max_lat = max(start_lat, end_lat) + 0.01
            min_lon = min(start_lon, end_lon) - 0.01
            max_lon = max(start_lon, end_lon) + 0.01

            incidents_data = self.get_traffic_incidents((min_lon, min_lat, max_lon, max_lat))

            traffic_delay = route_data.get("traffic_delay_minutes", 0)
            incident_count = incidents_data.get("incident_count", 0) if incidents_data.get("success") else 0

            if traffic_delay > 15:
                recommendation = "heavy_traffic"
                message = f"Heavy traffic! Expect {traffic_delay} min delay. Consider public transit."
            elif traffic_delay > 5:
                recommendation = "moderate_traffic"
                message = f"Moderate traffic. Expect {traffic_delay} min delay."
            else:
                recommendation = "clear"
                message = "Traffic is clear."

            return {
                "success": True,
                "recommendation": recommendation,
                "message": message,
                "traffic_delay_minutes": traffic_delay,
                "incident_count": incident_count,
                "incidents": incidents_data.get("incidents", [])[:3],
                "route": route_data
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Traffic check failed: {str(e)}"
            }

    def close(self):
        self.session.close()


if __name__ == "__main__":
    import os
    API_KEY = os.getenv("TOMTOM_API_KEY", "")
    client = TomTomClient(API_KEY)

    magdeburg_center = (52.1315, 11.6399)
    ovgu_campus = (52.1404, 11.6404)

    print("Testing TomTom Traffic API...")
    print("=" * 60)

    print("\n1. Traffic Flow at Magdeburg Center:")
    flow = client.get_traffic_flow(*magdeburg_center)
    if flow["success"]:
        print(f"   Congestion: {flow['congestion_level']}")
        print(f"   Current Speed: {flow['current_speed_kmh']} km/h")
        print(f"   Free Flow Speed: {flow['free_flow_speed_kmh']} km/h")
        print(f"   Delay: {flow['delay_minutes']} minutes")
    else:
        print(f"   Error: {flow['error']}")

    print("\n2. Traffic Incidents in Magdeburg:")
    bbox = (11.59, 52.09, 11.69, 52.17)
    incidents = client.get_traffic_incidents(bbox)
    if incidents["success"]:
        print(f"   Found {incidents['incident_count']} incidents")
        for inc in incidents["incidents"][:3]:
            print(f"   - {inc['type']}: {inc['description']}")
    else:
        print(f"   Error: {incidents['error']}")

    print("\n3. Route from Center to OVGU:")
    route = client.get_route_with_traffic(magdeburg_center, ovgu_campus)
    if route["success"]:
        print(f"   Distance: {route['distance']}")
        print(f"   Time: {route['travel_time']}")
        print(f"   Traffic Delay: {route['traffic_delay_minutes']} minutes")
    else:
        print(f"   Error: {route['error']}")

    print("\n4. Smart Traffic Check:")
    check = client.check_route_traffic(magdeburg_center, ovgu_campus)
    if check["success"]:
        print(f"   {check['message']}")
        print(f"   Recommendation: {check['recommendation']}")
    else:
        print(f"   Error: {check['error']}")

    client.close()
    print("\n" + "=" * 60)
    print("Tests complete!")
