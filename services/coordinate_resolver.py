"""
Semantic coordinate resolver for place name to coordinates mapping. Uses embeddings for fuzzy matching of buildings and transit stops.
"""

import numpy as np
from typing import Optional, Tuple, List, Dict
from sentence_transformers import SentenceTransformer


class CoordinateResolver:

    def __init__(self, neo4j_graph, ors_client, magdeburg_lat: float = 52.1205,
                 magdeburg_lon: float = 11.6276, embedding_model: str = "all-MiniLM-L6-v2"):
        self.neo4j_graph = neo4j_graph
        self.ors_client = ors_client
        self.magdeburg_lat = magdeburg_lat
        self.magdeburg_lon = magdeburg_lon

        print("   Loading semantic search model...")
        self.encoder = SentenceTransformer(embedding_model)

        self._building_cache = None
        self._stop_cache = None
        self._cache_initialized = False

    def _initialize_cache(self):
        if self._cache_initialized:
            return

        print("   Building semantic search index...")

        try:
            with self.neo4j_graph.driver.session(database=self.neo4j_graph.database) as session:
                result = session.run("""
                    MATCH (b:Building)
                    WHERE b.latitude IS NOT NULL AND b.longitude IS NOT NULL
                    RETURN b.id as id,
                           b.name as name,
                           b.function as function,
                           COALESCE(b.aliases, []) as aliases,
                           b.latitude as lat,
                           b.longitude as lon
                """)

                buildings = []
                building_texts = []

                for record in result:
                    building = {
                        "id": record["id"],
                        "name": record["name"],
                        "function": record["function"],
                        "aliases": record["aliases"],
                        "lat": record["lat"],
                        "lon": record["lon"]
                    }
                    buildings.append(building)

                    building_id = record["id"] or ""
                    search_parts = [
                        record["name"] or "",
                        record["function"] or "",
                    ]
                    if building_id:
                        search_parts.append(f"building {building_id}")
                        if building_id.isdigit():
                            search_parts.append(f"building {int(building_id)}")
                    search_parts.extend(record["aliases"] or [])
                    search_text = " | ".join(filter(None, search_parts))
                    building_texts.append(search_text)

                if building_texts:
                    building_embeddings = self.encoder.encode(building_texts, normalize_embeddings=True)
                    self._building_cache = {
                        "buildings": buildings,
                        "texts": building_texts,
                        "embeddings": building_embeddings
                    }
                    print(f"   Indexed {len(buildings)} buildings")

                result = session.run("""
                    MATCH (s:Stop)
                    WHERE s.latitude IS NOT NULL AND s.longitude IS NOT NULL
                    RETURN s.name as name,
                           s.latitude as lat,
                           s.longitude as lon,
                           COALESCE(s.lines, []) as lines
                """)

                stops = []
                stop_texts = []

                for record in result:
                    stop = {
                        "name": record["name"],
                        "lat": record["lat"],
                        "lon": record["lon"],
                        "lines": record["lines"]
                    }
                    stops.append(stop)

                    name = record["name"] or ""
                    short_name = name.replace("Magdeburg ", "")
                    stop_texts.append(f"{name} | {short_name}")

                if stop_texts:
                    stop_embeddings = self.encoder.encode(stop_texts, normalize_embeddings=True)
                    self._stop_cache = {
                        "stops": stops,
                        "texts": stop_texts,
                        "embeddings": stop_embeddings
                    }
                    print(f"   Indexed {len(stops)} stops")

                self._cache_initialized = True

        except Exception as e:
            print(f"   Warning: Error building search index: {e}")
            self._cache_initialized = False

    def resolve(self, place_name: str) -> Optional[Tuple[float, float]]:
        if not place_name:
            return None

        original = place_name
        normalized = place_name.lower().strip()

        self._initialize_cache()

        building_id = self._extract_building_id(normalized)
        if building_id:
            coords = self._get_building_by_id(building_id)
            if coords:
                return coords

        coords = self._exact_stop_match(normalized)
        if coords:
            return coords

        coords = self._semantic_building_search(normalized)
        if coords:
            return coords

        coords = self._semantic_stop_search(normalized)
        if coords:
            return coords

        if self._is_likely_building(normalized, original):
            print(f"   Building not found: {place_name}")
            return None

        print(f"   Geocoding: {place_name}...")
        coords = self.ors_client.geocode(place_name, self.magdeburg_lat, self.magdeburg_lon)
        if coords:
            print(f"   Found via ORS")
            return coords

        print(f"   Could not find: {place_name}")
        return None

    def _extract_building_id(self, text: str) -> Optional[str]:
        import re

        patterns = [
            r'building\s*(\d+)',
            r'bldg\s*(\d+)',
            r'gebäude\s*(\d+)',
            r'^(\d{1,2})$',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).zfill(2)

        return None

    def _get_building_by_id(self, building_id: str) -> Optional[Tuple[float, float]]:
        try:
            with self.neo4j_graph.driver.session(database=self.neo4j_graph.database) as session:
                result = session.run("""
                    MATCH (b:Building)
                    WHERE b.id = $id
                    RETURN b.name as name, b.longitude as lon, b.latitude as lat
                    LIMIT 1
                """, id=building_id)

                record = result.single()
                if record:
                    print(f"   Found Building {building_id}: {record['name']}")
                    return (record['lon'], record['lat'])
        except Exception as e:
            print(f"   Warning: Error getting building by ID: {e}")

        return None

    def _exact_stop_match(self, normalized: str) -> Optional[Tuple[float, float]]:
        try:
            with self.neo4j_graph.driver.session(database=self.neo4j_graph.database) as session:
                search_terms = [
                    normalized,
                    f"magdeburg {normalized}",
                    normalized.replace("magdeburg ", "")
                ]

                for search in search_terms:
                    result = session.run("""
                        MATCH (s:Stop)
                        WHERE toLower(s.name) = $search
                        RETURN s.name as name, s.longitude as lon, s.latitude as lat
                        LIMIT 1
                    """, search=search)

                    record = result.single()
                    if record:
                        print(f"   Found Stop: {record['name']}")
                        return (record['lon'], record['lat'])
        except Exception as e:
            print(f"   Warning: Error in exact stop match: {e}")

        return None

    def _semantic_building_search(self, query: str, threshold: float = 0.4) -> Optional[Tuple[float, float]]:
        if not self._building_cache:
            return None

        try:
            query_embedding = self.encoder.encode(query, normalize_embeddings=True)

            similarities = np.dot(self._building_cache["embeddings"], query_embedding)

            best_idx = np.argmax(similarities)
            best_score = similarities[best_idx]

            if best_score >= threshold:
                building = self._building_cache["buildings"][best_idx]
                print(f"   Found Building (semantic, {best_score:.2f}): {building['name']}")
                return (building['lon'], building['lat'])

        except Exception as e:
            print(f"   Warning: Error in semantic building search: {e}")

        return None

    def _semantic_stop_search(self, query: str, threshold: float = 0.5) -> Optional[Tuple[float, float]]:
        if not self._stop_cache:
            return None

        try:
            query_embedding = self.encoder.encode(query, normalize_embeddings=True)

            similarities = np.dot(self._stop_cache["embeddings"], query_embedding)

            best_idx = np.argmax(similarities)
            best_score = similarities[best_idx]

            if best_score >= threshold:
                stop = self._stop_cache["stops"][best_idx]
                print(f"   Found Stop (semantic, {best_score:.2f}): {stop['name']}")
                return (stop['lon'], stop['lat'])

        except Exception as e:
            print(f"   Warning: Error in semantic stop search: {e}")

        return None

    def _is_likely_building(self, normalized: str, original: str) -> bool:
        building_keywords = ['building', 'bldg', 'gebäude', 'faculty', 'department',
                           'institute', 'center', 'centre', 'library', 'mensa']
        return any(kw in normalized for kw in building_keywords)

    def refresh_cache(self):
        self._cache_initialized = False
        self._building_cache = None
        self._stop_cache = None
        self._initialize_cache()

    def search_buildings(self, query: str, top_k: int = 5) -> List[Dict]:
        if not self._building_cache:
            self._initialize_cache()

        if not self._building_cache:
            return []

        try:
            query_embedding = self.encoder.encode(query, normalize_embeddings=True)
            similarities = np.dot(self._building_cache["embeddings"], query_embedding)

            top_indices = np.argsort(similarities)[::-1][:top_k]

            results = []
            for idx in top_indices:
                building = self._building_cache["buildings"][idx]
                results.append({
                    "id": building["id"],
                    "name": building["name"],
                    "function": building["function"],
                    "score": float(similarities[idx]),
                    "coordinates": (building["lon"], building["lat"])
                })

            return results

        except Exception as e:
            print(f"   Warning: Error searching buildings: {e}")
            return []


_resolver_instance: Optional[CoordinateResolver] = None


def initialize_resolver(neo4j_graph, ors_client, magdeburg_lat: float = 52.1205,
                       magdeburg_lon: float = 11.6276) -> CoordinateResolver:
    global _resolver_instance
    _resolver_instance = CoordinateResolver(neo4j_graph, ors_client, magdeburg_lat, magdeburg_lon)
    return _resolver_instance


def get_coordinates(place_name: str) -> Optional[Tuple[float, float]]:
    if _resolver_instance is None:
        raise RuntimeError("Coordinate resolver not initialized. Call initialize_resolver() first.")
    return _resolver_instance.resolve(place_name)


def search_buildings(query: str, top_k: int = 5) -> List[Dict]:
    if _resolver_instance is None:
        raise RuntimeError("Coordinate resolver not initialized.")
    return _resolver_instance.search_buildings(query, top_k)


if __name__ == "__main__":
    print("CoordinateResolver with Semantic Search")
    print("Requires Neo4j and ORS clients to run.")
    print("\nExample usage:")
    print("  from coordinate_resolver import initialize_resolver, get_coordinates")
    print("  initialize_resolver(neo4j_graph, ors_client)")
    print("  coords = get_coordinates('Computer Science Faculty')")
    print("  # Returns coordinates for 'Faculty of Computer Science'")
