"""
OpenRouteService client for route calculation and geocoding. Provides walking, cycling, and driving routes with distance and duration.
"""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple


class ORSClient:

    def __init__(self, api_key: str, base_url: str = "https://api.openrouteservice.org",
                 http_timeout: int = 10):
        self.api_key = api_key
        self.base_url = base_url
        self.http_timeout = http_timeout

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": api_key,
            "Content-Type": "application/json"
        })

        self.profiles = {
            "walking": "foot-walking",
            "cycling": "cycling-regular",
            "driving": "driving-car",
            "wheelchair": "wheelchair"
        }

    def geocode(self, place_name: str, focus_lat: float = 52.1205,
                focus_lon: float = 11.6276) -> Optional[Tuple[float, float]]:
        try:
            response = self.session.get(
                f"{self.base_url}/geocode/search",
                params={
                    "api_key": self.api_key,
                    "text": f"{place_name}, Magdeburg, Germany",
                    "size": 1,
                    "focus.point.lat": focus_lat,
                    "focus.point.lon": focus_lon,
                    "boundary.country": "DE"
                },
                timeout=self.http_timeout
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("features"):
                    coords = data["features"][0]["geometry"]["coordinates"]
                    return (coords[0], coords[1])
            return None
        except Exception as e:
            print(f"ORS Geocoding error: {e}")
            return None

    def get_route(self, start_coords: Tuple[float, float], end_coords: Tuple[float, float],
                  profile: str = "walking") -> Optional[Dict]:
        ors_profile = self.profiles.get(profile, "foot-walking")

        try:
            response = self.session.post(
                f"{self.base_url}/v2/directions/{ors_profile}",
                json={
                    "coordinates": [list(start_coords), list(end_coords)],
                    "instructions": False,
                    "geometry": True
                },
                timeout=self.http_timeout
            )

            if response.status_code == 200:
                data = response.json()

                if not data.get("routes"):
                    return {"success": False, "error": "No routes found"}

                route = data["routes"][0]

                summary = route.get("summary", {})
                if not summary and "properties" in route:
                    summary = route["properties"].get("summary", {})

                distance_m = summary.get("distance", 0)
                duration_s = summary.get("duration", 0)

                geometry = route.get("geometry", {})

                if distance_m >= 1000:
                    distance_str = f"{distance_m/1000:.1f} km"
                else:
                    distance_str = f"{int(distance_m)} m"

                if duration_s >= 3600:
                    hours = int(duration_s // 3600)
                    mins = int((duration_s % 3600) // 60)
                    duration_str = f"{hours}h {mins}min"
                else:
                    duration_str = f"{int(duration_s // 60)} min"

                return {
                    "success": True,
                    "profile": profile,
                    "distance": distance_str,
                    "distance_meters": distance_m,
                    "duration": duration_str,
                    "duration_seconds": duration_s,
                    "geometry": geometry,
                    "summary": summary
                }
            else:
                return {"success": False, "error": f"ORS API error: {response.status_code}"}

        except Exception as e:
            print(f"ORS route error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def get_route_with_directions(self, start_coords: Tuple[float, float],
                                    end_coords: Tuple[float, float],
                                    profile: str = "driving",
                                    max_steps: int = 4) -> Optional[Dict]:
        ors_profile = self.profiles.get(profile, "driving-car")

        try:
            response = self.session.post(
                f"{self.base_url}/v2/directions/{ors_profile}",
                json={
                    "coordinates": [list(start_coords), list(end_coords)],
                    "instructions": True,
                    "geometry": True,
                    "language": "en"
                },
                timeout=self.http_timeout
            )

            if response.status_code == 200:
                data = response.json()

                if not data.get("routes"):
                    return {"success": False, "error": "No routes found"}

                route = data["routes"][0]
                summary = route.get("summary", {})

                distance_m = summary.get("distance", 0)
                duration_s = summary.get("duration", 0)

                if distance_m >= 1000:
                    distance_str = f"{distance_m/1000:.1f} km"
                else:
                    distance_str = f"{int(distance_m)} m"

                if duration_s >= 3600:
                    hours = int(duration_s // 3600)
                    mins = int((duration_s % 3600) // 60)
                    duration_str = f"{hours}h {mins}min"
                else:
                    duration_str = f"{int(duration_s // 60)} min"

                directions = []
                streets_on_route = []
                segments = route.get("segments", [])

                for segment in segments:
                    steps = segment.get("steps", [])
                    for step in steps:
                        instruction = step.get("instruction", "")
                        name = step.get("name", "")
                        step_distance = step.get("distance", 0)
                        step_type = step.get("type", 0)

                        if name and name not in streets_on_route and name != "-":
                            streets_on_route.append(name)

                        if step_distance < 50 and step_type != 10:
                            continue

                        if step_distance >= 1000:
                            dist_str = f"{step_distance/1000:.1f} km"
                        elif step_distance > 0:
                            dist_str = f"{int(step_distance)} m"
                        else:
                            dist_str = ""

                        directions.append({
                            "instruction": instruction,
                            "street": name,
                            "distance": dist_str,
                            "distance_meters": step_distance,
                            "type": step_type
                        })

                if len(directions) > max_steps:
                    simplified = [directions[0]]

                    middle_steps = sorted(directions[1:-1],
                                         key=lambda x: x["distance_meters"],
                                         reverse=True)[:max_steps - 2]
                    middle_indices = [directions.index(s) for s in middle_steps]
                    middle_steps = [directions[i] for i in sorted(middle_indices)]
                    simplified.extend(middle_steps)

                    if directions[-1] not in simplified:
                        simplified.append(directions[-1])

                    directions = simplified

                return {
                    "success": True,
                    "profile": profile,
                    "distance": distance_str,
                    "distance_meters": distance_m,
                    "duration": duration_str,
                    "duration_seconds": duration_s,
                    "directions": directions,
                    "directions_text": [d["instruction"] + (f" ({d['distance']})" if d["distance"] else "")
                                        for d in directions],
                    "streets_on_route": streets_on_route
                }
            else:
                return {"success": False, "error": f"ORS API error: {response.status_code}"}

        except Exception as e:
            print(f"ORS directions error: {e}")
            return {"success": False, "error": str(e)}

    def get_multi_modal_routes(self, start_coords: Tuple[float, float],
                                end_coords: Tuple[float, float],
                                profiles: List[str] = None) -> Dict:
        if profiles is None:
            profiles = ["walking", "cycling", "driving"]

        results = {}
        with ThreadPoolExecutor(max_workers=len(profiles)) as executor:
            future_to_profile = {
                executor.submit(self.get_route, start_coords, end_coords, profile): profile
                for profile in profiles
            }
            for future in as_completed(future_to_profile):
                profile = future_to_profile[future]
                try:
                    results[profile] = future.result(timeout=15)
                except Exception as e:
                    results[profile] = {"success": False, "error": str(e)}
        return results

    def close(self):
        self.session.close()


if __name__ == "__main__":
    import os

    api_key = os.getenv("ORS_API_KEY", "")
    if not api_key:
        print("Set ORS_API_KEY environment variable")
        exit(1)

    client = ORSClient(api_key)

    coords = client.geocode("Hauptbahnhof")
    print(f"Hauptbahnhof coordinates: {coords}")

    if coords:
        magdeburg_center = (11.6399, 52.1315)
        route = client.get_route(magdeburg_center, coords, "walking")
        print(f"Walking route: {route}")
        if route and route.get("success"):
            print(f"  Distance: {route['distance']}")
            print(f"  Duration: {route['duration']}")
            if route.get("geometry"):
                coords_count = len(route['geometry'].get('coordinates', []))
                print(f"  Geometry: {coords_count} points")

    client.close()
