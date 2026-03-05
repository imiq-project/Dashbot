"""
Legacy location resolver for campus locations. Maps location names to coordinates and sensor IDs.
"""

import numpy as np
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer


class LocationResolver:
    def __init__(self, neo4j_graph):
        self.neo4j_graph = neo4j_graph
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')

    def resolve_location(
        self,
        user_query: str,
        sensor_types: Optional[List[str]] = None,
        threshold: float = 0.5
    ) -> Dict:
        normalized_query = user_query.lower().strip()

        direct_result = self._direct_neo4j_match(normalized_query, sensor_types)
        if direct_result and direct_result.get("success"):
            return direct_result

        semantic_result = self._semantic_search(normalized_query, sensor_types, threshold)
        return semantic_result

    def _direct_neo4j_match(self, query: str, sensor_types: Optional[List[str]] = None) -> Dict:
        try:
            with self.neo4j_graph.driver.session(database=self.neo4j_graph.database) as session:

                entity_type_filter = None
                if sensor_types:
                    sensor_to_entity = {
                        "weather": "WeatherObserved",
                        "parking": "ParkingSpot",
                        "traffic": "Traffic",
                        "room": "Room"
                    }
                    entity_types = [sensor_to_entity.get(st) for st in sensor_types if st in sensor_to_entity]
                    if entity_types:
                        entity_type_filter = entity_types[0]

                cypher_query = """
                    MATCH (b:Building)
                    OPTIONAL MATCH (b)-[:HAS_SENSOR]->(s:Sensor)
                    WHERE (
                        toLower(b.name) CONTAINS $query
                        OR toLower(b.id) = $query
                        OR any(alias IN b.aliases WHERE toLower(alias) CONTAINS $query)
                    )
                    """

                if entity_type_filter:
                    cypher_query += " AND (s IS NULL OR s.entity_type = $entity_type)"

                cypher_query += """
                    RETURN DISTINCT
                        b.name as location_name,
                        b.id as display_name,
                        collect(DISTINCT s.id) as entity_ids,
                        b.latitude as lat,
                        b.longitude as lon
                    LIMIT 1
                """

                params = {"query": query}
                if entity_type_filter:
                    params["entity_type"] = entity_type_filter

                result = session.run(cypher_query, **params)
                record = result.single()

                if record:
                    entity_ids_dict = {}
                    for sensor_id in record["entity_ids"]:
                        if sensor_id:
                            if "Weather" in sensor_id:
                                entity_ids_dict["WeatherObserved"] = sensor_id
                            elif "Parking" in sensor_id:
                                entity_ids_dict["ParkingSpot"] = sensor_id
                            elif "Traffic" in sensor_id:
                                entity_ids_dict["Traffic"] = sensor_id

                    return {
                        "success": True,
                        "locations": [{
                            "location_name": record["location_name"],
                            "display_name": f"Building {record['display_name']}",
                            "entity_ids": entity_ids_dict,
                            "id_pattern": f".*{record['display_name']}.*",
                            "coordinates": {
                                "lat": record["lat"],
                                "lon": record["lon"]
                            },
                            "similarity": 1.0,
                            "matched_term": query
                        }],
                        "query": query,
                        "found_count": 1
                    }

        except Exception as e:
            print(f"   Warning: Neo4j direct match error: {e}")

        return {"success": False}

    def _semantic_search(self, query: str, sensor_types: Optional[List[str]] = None, threshold: float = 0.5) -> Dict:
        try:
            with self.neo4j_graph.driver.session(database=self.neo4j_graph.database) as session:
                result = session.run("""
                    MATCH (b:Building)
                    OPTIONAL MATCH (b)-[:HAS_SENSOR]->(s:Sensor)
                    RETURN b.id as id,
                           b.name as name,
                           COALESCE(b.aliases, []) as aliases,
                           b.latitude as lat,
                           b.longitude as lon,
                           collect(DISTINCT s) as sensors
                """)

                buildings = list(result)

            if not buildings:
                return {
                    "success": False,
                    "message": "No buildings found in Neo4j",
                    "query": query
                }

            search_terms = []
            term_to_building = {}

            for building in buildings:
                building_id = building["id"]
                terms = [building["name"]] + building["aliases"]

                for term in terms:
                    term_lower = term.lower()
                    if term_lower not in term_to_building:
                        search_terms.append(term_lower)
                        term_to_building[term_lower] = building

            if not search_terms:
                return {
                    "success": False,
                    "message": "No search terms available",
                    "query": query
                }

            query_embedding = self.encoder.encode([query.lower()])[0]
            search_embeddings = self.encoder.encode(search_terms)

            similarities = np.dot(search_embeddings, query_embedding)

            top_indices = np.where(similarities > threshold)[0]

            if len(top_indices) == 0:
                return {
                    "success": False,
                    "message": "No matching location found",
                    "query": query
                }

            top_indices = top_indices[np.argsort(-similarities[top_indices])]

            seen_buildings = set()
            results = []

            for idx in top_indices:
                matched_term = search_terms[idx]
                building = term_to_building[matched_term]
                building_id = building["id"]

                if building_id not in seen_buildings:
                    seen_buildings.add(building_id)

                    entity_ids = {}
                    for sensor in building["sensors"]:
                        if sensor:
                            sensor_node = dict(sensor)
                            sensor_id = sensor_node.get("id")
                            sensor_type = sensor_node.get("entity_type")

                            if sensor_types:
                                sensor_to_entity = {
                                    "weather": "WeatherObserved",
                                    "parking": "ParkingSpot",
                                    "traffic": "Traffic",
                                    "room": "Room"
                                }
                                wanted_types = [sensor_to_entity.get(st) for st in sensor_types]
                                if sensor_type in wanted_types:
                                    entity_ids[sensor_type] = sensor_id
                            else:
                                entity_ids[sensor_type] = sensor_id

                    if entity_ids or not sensor_types:
                        results.append({
                            "location_name": building["name"],
                            "display_name": f"Building {building_id}",
                            "entity_ids": entity_ids,
                            "id_pattern": f".*{building_id}.*",
                            "coordinates": {
                                "lat": building["lat"],
                                "lon": building["lon"]
                            },
                            "similarity": float(similarities[idx]),
                            "matched_term": matched_term
                        })

            return {
                "success": True,
                "locations": results,
                "query": query,
                "found_count": len(results)
            }

        except Exception as e:
            print(f"   Warning: Semantic search error: {e}")
            return {
                "success": False,
                "message": f"Search error: {str(e)}",
                "query": query
            }

    def format_for_llm(self, resolution_result: Dict) -> str:
        if not resolution_result["success"]:
            return resolution_result.get("message", "Location not found")

        if not resolution_result["locations"]:
            return "No matching locations found."

        lines = [f"Found {resolution_result['found_count']} location(s):\n"]

        for loc in resolution_result["locations"]:
            lines.append(f"**{loc['display_name']}** ({loc['location_name']})")
            lines.append(f"   Match confidence: {loc['similarity']:.2%}")

            if loc["entity_ids"]:
                lines.append(f"   Available sensors:")
                for entity_type, entity_id in loc["entity_ids"].items():
                    lines.append(f"      {entity_type}: `{entity_id}`")

            lines.append(f"   Coordinates: {loc['coordinates']['lat']}, {loc['coordinates']['lon']}")
            lines.append("")

        return "\n".join(lines)


_resolver = None

def get_resolver() -> LocationResolver:
    global _resolver
    return _resolver


def initialize_resolver(neo4j_graph):
    global _resolver
    _resolver = LocationResolver(neo4j_graph)
    return _resolver


def resolve_campus_location(user_query: str, sensor_types: Optional[List[str]] = None) -> dict:
    resolver = get_resolver()

    if resolver is None:
        return {
            "success": False,
            "message": "Location resolver not initialized"
        }

    result = resolver.resolve_location(user_query, sensor_types)

    if not result["success"] or not result["locations"]:
        return {
            "success": False,
            "message": "No specific location found in query.",
            "suggestion": "Query all entities without location filter."
        }

    best_match = result["locations"][0]
    entity_ids = best_match.get("entity_ids", {})

    sensor_to_entity = {
        "weather": "WeatherObserved",
        "parking": "ParkingSpot",
        "traffic": "Traffic",
        "room": "Room"
    }

    entity_id = None
    if sensor_types:
        for sensor_type in sensor_types:
            entity_type = sensor_to_entity.get(sensor_type)
            if entity_type and entity_ids.get(entity_type):
                entity_id = entity_ids[entity_type]
                break

    return {
        "success": True,
        "location_name": best_match["location_name"],
        "display_name": best_match["display_name"],
        "entity_id": entity_id,
        "id_pattern": best_match["id_pattern"],
        "coordinates": best_match["coordinates"],
        "similarity": best_match["similarity"],
        "all_entity_ids": entity_ids
    }
