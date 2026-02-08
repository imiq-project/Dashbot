"""
FIWARE Context Broker client for real-time IoT sensor data. Queries weather, parking, traffic, air quality, and room sensors using NGSIv2 API.
"""

import requests
from typing import Dict, List, Optional, Any, Union


class FIWAREClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers['x-api-key'] = self.api_key

    def query_entities(
        self,
        entity_type: str,
        entity_id: Optional[str] = None,
        id_pattern: Optional[str] = None,
        q: Optional[str] = None,
        mq: Optional[str] = None,
        georel: Optional[str] = None,
        geometry: Optional[str] = None,
        coords: Optional[str] = None,
        attrs: Optional[Union[str, List[str]]] = None,
        metadata: Optional[Union[str, List[str]]] = None,
        order_by: Optional[str] = None,
        limit: Union[int, str] = 20,
        offset: Union[int, str] = 0,
        options: Optional[Union[str, List[str]]] = None
    ) -> Dict[str, Any]:

        limit = int(limit) if isinstance(limit, str) else limit
        offset = int(offset) if isinstance(offset, str) else offset

        params = {
            "type": entity_type,
            "limit": str(min(limit, 1000))
        }

        if entity_id:
            params["id"] = entity_id
        elif id_pattern:
            params["idPattern"] = id_pattern

        if q:
            params["q"] = q
        if mq:
            params["mq"] = mq

        if georel and geometry and coords:
            params["georel"] = georel
            params["geometry"] = geometry
            params["coords"] = coords

        if attrs:
            params["attrs"] = ','.join(attrs) if isinstance(attrs, list) else attrs
        if metadata:
            params["metadata"] = ','.join(metadata) if isinstance(metadata, list) else metadata

        if order_by:
            params["orderBy"] = order_by
        if offset > 0:
            params["offset"] = str(offset)

        if options:
            if isinstance(options, list):
                params["options"] = ','.join(options)
            else:
                params["options"] = options
        else:
            params["options"] = "count,keyValues"

        url = f"{self.base_url}/entities"

        try:
            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                entities = response.json()
                total_count = response.headers.get("Fiware-Total-Count")

                return {
                    "success": True,
                    "entities": entities,
                    "count": int(total_count) if total_count else len(entities),
                    "returned": len(entities),
                    "entity_type": entity_type,
                    "params": params
                }
            else:
                return {
                    "success": False,
                    "error": f"FIWARE returned status {response.status_code}",
                    "details": response.text,
                    "params": params
                }

        except requests.exceptions.Timeout:
            return {"success": False, "error": "FIWARE query timed out"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "Could not connect to FIWARE"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def get_entity_by_id(self, entity_id: str, attrs: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/entities/{entity_id}"
        params = {}

        if attrs:
            params["attrs"] = attrs

        try:
            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                return {
                    "success": True,
                    "entity": response.json()
                }
            elif response.status_code == 404:
                return {
                    "success": False,
                    "error": "Entity not found",
                    "entity_id": entity_id
                }
            else:
                return {
                    "success": False,
                    "error": f"FIWARE returned status {response.status_code}",
                    "details": response.text
                }

        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}

    def query_sensor_by_coordinates(
        self,
        latitude: float,
        longitude: float,
        sensor_type: str,
        radius: int = 500,
        attrs: Optional[str] = None
    ) -> Dict[str, Any]:
        print(f"[FIWARE] Geo-query: type={sensor_type}, coords=({latitude}, {longitude}), radius={radius}m")

        type_mapping = {
            "Weather": "Weather",
            "Parking": "Parking",
            "Traffic": "Traffic",
            "AirQuality": "AirQuality",
            "Room": "Room",
            "Vehicle": "Vehicle",
            "POI": "POI"
        }
        fiware_type = type_mapping.get(sensor_type, sensor_type)

        params = {
            "type": fiware_type,
            "georel": f"near;maxDistance:{radius}",
            "geometry": "point",
            "coords": f"{latitude},{longitude}",
            "limit": "1",
            "options": "keyValues"
        }

        if attrs:
            params["attrs"] = attrs

        url = f"{self.base_url}/entities"

        try:
            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                entities = response.json()

                if entities:
                    entity = entities[0]
                    print(f"[FIWARE] Found sensor: {entity.get('id', 'unknown')}")
                    return {
                        "success": True,
                        "entity_type": fiware_type,
                        "entity": entity,
                        "query_location": {
                            "latitude": latitude,
                            "longitude": longitude
                        }
                    }
                else:
                    print(f"[FIWARE] No sensor found within {radius}m")
                    return {
                        "success": False,
                        "error": f"No {fiware_type} sensor found within {radius}m of ({latitude}, {longitude})"
                    }
            else:
                return {
                    "success": False,
                    "error": f"FIWARE returned status {response.status_code}",
                    "details": response.text
                }

        except requests.exceptions.Timeout:
            return {"success": False, "error": "FIWARE query timed out"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "Could not connect to FIWARE"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def get_weather(self, limit: int = 5) -> Dict[str, Any]:
        return self.query_entities(
            entity_type="Weather",
            limit=limit,
            options="keyValues"
        )

    def get_parking(self, limit: int = 10) -> Dict[str, Any]:
        return self.query_entities(
            entity_type="Parking",
            limit=limit,
            options="keyValues"
        )

    def get_traffic(self, limit: int = 10) -> Dict[str, Any]:
        return self.query_entities(
            entity_type="Traffic",
            limit=limit,
            options="keyValues"
        )

    def close(self):
        self.session.close()
