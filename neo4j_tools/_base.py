"""Neo4jBase: core infrastructure for the Neo4j Transit Graph.

Provides connection management, semantic search initialization,
building/stop lookup helpers, distance calculation, and location resolution.
All other mixin classes inherit from Neo4jBase.

The driver is injected (shared singleton from mcp_servers/neo4j_server.py)
rather than created per instance — see `neo4j_tools.get_default_driver()`.
"""

from neo4j import GraphDatabase, Query
from typing import Dict, List, Optional, Any
from models import Coordinates


_DEFAULT_QUERY_TIMEOUT = 8.0


def _q(cypher: str, timeout: float = _DEFAULT_QUERY_TIMEOUT) -> Query:
    """Wrap a Cypher string in a Query object with a per-query timeout."""
    return Query(cypher, timeout=timeout)


class Neo4jBase:
    def __init__(self, uri: str = None, username: str = None, password: str = None,
                 database: str = "neo4j", verbose: bool = False, encoder=None,
                 driver=None):
        """Accepts either an injected `driver` (preferred — shared singleton) or
        (uri, username, password) kwargs as a legacy fallback. When a driver is
        injected we do NOT own it and must not close it in __del__ / close()."""
        if driver is not None:
            self.driver = driver
            self._owns_driver = False
        else:
            # Legacy path: callers still creating their own driver.
            # Prefer `get_default_driver()` from the `neo4j_tools` package.
            if uri is None:
                from neo4j_tools import get_default_driver
                self.driver = get_default_driver()
                self._owns_driver = False
            else:
                self.driver = GraphDatabase.driver(
                    uri, auth=(username, password),
                    connection_acquisition_timeout=5.0,
                    connection_timeout=3.0,
                    max_connection_pool_size=50,
                )
                self._owns_driver = True

        self.database = database
        self._closed = False
        self._encoder = encoder
        self._building_cache = None
        self._building_embeddings = None
        self._stop_cache = None
        self._stop_embeddings = None
        self._fulltext_available = None  # None = not checked, True/False = checked
        self._line_cache = None  # Cached set of line names from Neo4j
        self.verbose = verbose
        import atexit
        atexit.register(self.close)

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def close(self):
        # Only close if we own the driver — a shared singleton must outlive us.
        if not self._closed and self.driver is not None and getattr(self, "_owns_driver", False):
            try:
                self.driver.close()
                self._closed = True
            except Exception:
                pass

    def __del__(self):
        self.close()

    def test_connection(self) -> bool:
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(_q("RETURN 1 as test"))
                return result.single()["test"] == 1
        except Exception as e:
            print(f"Neo4j connection test failed: {e}")
            return False

    def _ensure_fulltext_indexes(self) -> bool:
        """Create full-text indexes if they don't exist. Returns True if available."""
        if self._fulltext_available is not None:
            return self._fulltext_available

        index_statements = [
            'CREATE FULLTEXT INDEX building_fts IF NOT EXISTS FOR (b:Building) ON EACH [b.name, b.function, b.note, b.address, b.aliases, b.departments]',
            'CREATE FULLTEXT INDEX stop_fts IF NOT EXISTS FOR (s:Stop) ON EACH [s.name, s.id]',
            'CREATE FULLTEXT INDEX poi_fts IF NOT EXISTS FOR (p:POI) ON EACH [p.name, p.type, p.cuisine, p.aliases, p.note, p.address]',
            'CREATE FULLTEXT INDEX landmark_fts IF NOT EXISTS FOR (l:Landmark) ON EACH [l.name, l.description]',
        ]

        try:
            with self.driver.session(database=self.database) as session:
                for stmt in index_statements:
                    session.run(_q(stmt, timeout=15.0))

                result = session.run(_q(
                    "SHOW FULLTEXT INDEXES YIELD name, state "
                    "WHERE name IN ['building_fts','stop_fts','poi_fts','landmark_fts'] "
                    "RETURN name, state",
                    timeout=15.0,
                ))
                states = {r["name"]: r["state"] for r in result}
                if states:
                    self._fulltext_available = True
                    self._log(f"[NEO4J] Full-text indexes: {states}")
                else:
                    self._fulltext_available = False
                    self._log("[NEO4J] Full-text indexes not found after creation")

        except Exception as e:
            self._log(f"[NEO4J] Full-text indexes not available: {e}")
            self._fulltext_available = False

        return self._fulltext_available

    def _init_semantic_search(self):
        if self._building_cache is not None:
            return
        if self._encoder is None:
            self._log("   Warning: no encoder provided, loading all-MiniLM-L6-v2...")
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer('all-MiniLM-L6-v2')
        try:
            import numpy as np
            self._log("   Building semantic search index for neo4j_tools...")
            with self.driver.session(database=self.database) as session:
                result = session.run(_q("""
                    MATCH (b:Building)
                    RETURN b as building, b.name as name,
                           b.latitude as latitude, b.longitude as longitude
                """, timeout=15.0))
                self._building_cache = []
                building_texts = []
                for record in result:
                    building_node = dict(record["building"])
                    building = {
                        "id": record["name"],
                        "name": record["name"] or "",
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                        "all_properties": building_node
                    }
                    self._building_cache.append(building)
                    text_parts = []
                    for key, value in building_node.items():
                        if value is None:
                            continue
                        if key in ['latitude', 'longitude']:
                            continue
                        if isinstance(value, list):
                            text_parts.append(" ".join(str(v) for v in value if v))
                        elif isinstance(value, str):
                            text_parts.append(value)
                    search_text = " | ".join(filter(None, text_parts))
                    building_texts.append(search_text)
                self._building_embeddings = self._encoder.encode(building_texts, normalize_embeddings=True)
                self._log(f"   Building cache ready: {len(self._building_cache)} buildings")
        except Exception as e:
            self._log(f"   Semantic search init failed: {e}")
            self._encoder = None
            self._semantic_search_failed = True

    def _semantic_building_search(self, query: str, threshold: float = 0.45) -> Optional[Dict]:
        self._init_semantic_search()
        if self._encoder is None or getattr(self, '_semantic_search_failed', False):
            return None
        try:
            import numpy as np
            query_embedding = self._encoder.encode(query, normalize_embeddings=True)
            similarities = np.dot(self._building_embeddings, query_embedding)
            best_idx = np.argmax(similarities)
            best_score = similarities[best_idx]
            if best_score >= threshold:
                building = self._building_cache[best_idx]
                self._log(f"   Semantic match: '{query}' -> {building['name']} (score: {best_score:.2f})")
                return {
                    "id": building["id"],
                    "name": building["name"],
                    "latitude": building.get("latitude"),
                    "longitude": building.get("longitude"),
                    "score": float(best_score),
                    "match_type": "semantic"
                }
            return None
        except Exception as e:
            self._log(f"   Semantic search error: {e}")
            return None

    def _init_semantic_stop_search(self):
        if self._stop_cache is not None:
            return
        if self._encoder is None:
            return
        try:
            import numpy as np
            self._log("   Building semantic stop search index...")
            with self.driver.session(database=self.database) as session:
                result = session.run(_q("""
                    MATCH (s:Stop)
                    WHERE s.latitude IS NOT NULL AND s.longitude IS NOT NULL
                    RETURN s.name as name, s.latitude as latitude,
                           s.longitude as longitude, COALESCE(s.lines, []) as lines
                """, timeout=15.0))
                self._stop_cache = []
                stop_texts = []
                for record in result:
                    stop = {
                        "name": record["name"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                        "lines": record["lines"]
                    }
                    self._stop_cache.append(stop)
                    name = record["name"] or ""
                    short_name = name.replace("Magdeburg ", "")
                    stop_texts.append(f"{name} | {short_name}")
                self._stop_embeddings = self._encoder.encode(stop_texts, normalize_embeddings=True)
                self._log(f"   Stop cache ready: {len(self._stop_cache)} stops")
        except Exception as e:
            self._log(f"   Semantic stop search init failed: {e}")
            self._stop_cache = None
            self._stop_embeddings = None

    def _semantic_stop_search(self, query: str, threshold: float = 0.5) -> Optional[Dict]:
        self._init_semantic_stop_search()
        if self._stop_cache is None or self._stop_embeddings is None:
            return None
        try:
            import numpy as np
            query_embedding = self._encoder.encode(query, normalize_embeddings=True)
            similarities = np.dot(self._stop_embeddings, query_embedding)
            best_idx = np.argmax(similarities)
            best_score = similarities[best_idx]
            if best_score >= threshold:
                stop = self._stop_cache[best_idx]
                self._log(f"   Semantic stop match: '{query}' -> {stop['name']} (score: {best_score:.2f})")
                return {
                    "type": "Stop",
                    "name": stop["name"],
                    "latitude": stop["latitude"],
                    "longitude": stop["longitude"],
                    "lines": stop["lines"],
                    "score": float(best_score),
                    "match_type": "semantic"
                }
            return None
        except Exception as e:
            self._log(f"   Semantic stop search error: {e}")
            return None

    def _normalize_stop_name(self, stop_name: str) -> str:
        stop_name = stop_name.strip()
        if not stop_name.lower().startswith("magdeburg"):
            stop_name = f"Magdeburg {stop_name}"
        return stop_name

    def _init_line_cache(self):
        """Load all distinct line names from Neo4j once."""
        if self._line_cache is not None:
            return
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(_q(
                    "MATCH ()-[r:NEXT_STOP]->() "
                    "WITH DISTINCT r.line as line WHERE line IS NOT NULL "
                    "RETURN collect(line) as lines",
                    timeout=15.0,
                ))
                record = result.single()
                self._line_cache = set(record["lines"]) if record else set()
                self._log(f"[NEO4J] Line cache loaded: {len(self._line_cache)} lines")
        except Exception as e:
            self._log(f"[NEO4J] Line cache init failed: {e}")
            self._line_cache = set()

    def _normalize_line_name(self, line_name: str) -> str:
        """Resolve user input to the exact line name stored in Neo4j.

        Neo4j stores lines as 'Tram 2', 'Bus 45', etc. User/LLM may send
        'Tram 2', 'Line 2', 'Linie 2', or just '2'. This method maps any
        of those forms to the canonical Neo4j value.
        """
        line_name = line_name.strip()
        self._init_line_cache()

        # Exact match (e.g., "Tram 2" already correct)
        if line_name in self._line_cache:
            return line_name

        # Case-insensitive exact match
        lower_map = {l.lower(): l for l in self._line_cache}
        if line_name.lower() in lower_map:
            return lower_map[line_name.lower()]

        # Strip generic prefixes to get the number/identifier
        number = line_name
        for prefix in ["Tram ", "tram ", "Bus ", "bus ", "Line ", "line ", "Linie ", "linie "]:
            if line_name.startswith(prefix):
                number = line_name[len(prefix):]
                break

        # Try standard prefixes with the extracted number
        for prefix in ["Tram", "Bus"]:
            candidate = f"{prefix} {number}"
            if candidate in self._line_cache:
                return candidate

        # Case-insensitive suffix match (handles "9" matching "Tram 9")
        for cached_line in self._line_cache:
            if cached_line.lower().endswith(f" {number.lower()}"):
                return cached_line

        # Nothing matched — return as-is and let the query fail gracefully
        self._log(f"[NEO4J] ⚠️ Could not resolve line name '{line_name}' to any known line")
        return line_name

    def _find_building_universal(self, search_input: str, session=None) -> Optional[Dict]:
        self._log(f"[NEO4J] 🔍 _find_building_universal: searching for '{search_input}'")
        search_term = search_input.strip().lower()
        original_search = search_term
        for prefix in ["building ", "bldg ", "gebäude ", "magdeburg ", "ovgu ", "the "]:
            if search_term.startswith(prefix):
                search_term = search_term[len(prefix):]
                break

        # For numeric searches, create exact building name variants
        is_numeric_search = search_term.isdigit()
        building_number_variants = []
        if is_numeric_search:
            # Create variants: "building 3", "building 03", "3", "03"
            num = int(search_term)
            building_number_variants = [
                f"building {num:02d}",  # "building 03"
                f"building {num}",       # "building 3"
                search_term.zfill(2),    # "03"
                search_term              # "3"
            ]

        def do_search(sess):
            # For numeric searches, use EXACT matching only to prevent "3" matching "30"
            if is_numeric_search:
                exact_num_query = """
                    MATCH (b:Building)
                    WHERE toLower(b.name) IN $variants
                       OR ANY(alias IN b.aliases WHERE toLower(alias) IN $variants)
                    RETURN b.name as name, b.latitude as latitude, b.longitude as longitude, 'exact_number_match' as match_type
                    LIMIT 1
                """
                num_result = sess.run(_q(exact_num_query), variants=building_number_variants)
                num_record = num_result.single()
                if num_record:
                    self._log(f"[NEO4J] ✅ Found via exact number match: {num_record['name']}")
                    return {
                        "id": num_record["name"],
                        "name": num_record["name"],
                        "latitude": num_record["latitude"],
                        "longitude": num_record["longitude"],
                        "match_type": "exact"
                    }
                # If no exact numeric match, fall through to semantic search
                self._log(f"[NEO4J] No exact numeric match for '{search_term}', trying semantic...")
            else:
                # For non-numeric searches, first try exact name match
                exact_query = """
                    MATCH (b:Building)
                    WHERE toLower(b.name) = $search_term
                    RETURN b.name as name, b.latitude as latitude, b.longitude as longitude, 'exact_match' as match_type
                    LIMIT 1
                """
                exact_result = sess.run(_q(exact_query), search_term=search_term)
                exact_record = exact_result.single()
                if exact_record:
                    self._log(f"[NEO4J] ✅ Found via exact name match: {exact_record['name']}")
                    return {
                        "id": exact_record["name"],
                        "name": exact_record["name"],
                        "latitude": exact_record["latitude"],
                        "longitude": exact_record["longitude"],
                        "match_type": "exact"
                    }

                # Then try word-boundary CONTAINS (search term must be a complete word in the name)
                # This prevents "mensa" from matching "Mensa Herrenkrug" POI over campus Mensa building
                word_query = """
                    MATCH (b:Building)
                    WHERE toLower(b.name) CONTAINS $search_term
                    RETURN b.name as name, b.latitude as latitude, b.longitude as longitude, 'contains_match' as match_type
                    ORDER BY size(b.name)
                    LIMIT 1
                """
                word_result = sess.run(_q(word_query), search_term=search_term)
                word_record = word_result.single()
                if word_record:
                    self._log(f"[NEO4J] ✅ Found via contains match: {word_record['name']}")
                    return {
                        "id": word_record["name"],
                        "name": word_record["name"],
                        "latitude": word_record["latitude"],
                        "longitude": word_record["longitude"],
                        "match_type": "contains_match"
                    }

            # Check aliases with exact match only (no CONTAINS for aliases)
            alias_query = """
                MATCH (b:Building)
                WHERE ANY(alias IN b.aliases WHERE toLower(alias) = $search_term)
                RETURN b.name as name, b.latitude as latitude, b.longitude as longitude, 'alias_match' as match_type
                LIMIT 1
            """
            alias_result = sess.run(_q(alias_query), search_term=search_term)
            alias_record = alias_result.single()
            if alias_record:
                self._log(f"[NEO4J] ✅ Found via alias match: {alias_record['name']}")
                return {
                    "id": alias_record["name"],
                    "name": alias_record["name"],
                    "latitude": alias_record["latitude"],
                    "longitude": alias_record["longitude"],
                    "match_type": "exact"
                }
            text_query = """
                MATCH (b:Building)
                WHERE toLower(b.function) CONTAINS $search_term
                   OR toLower(b.note) CONTAINS $search_term
                   OR (b.departments IS NOT NULL AND ANY(dept IN b.departments WHERE toLower(dept) CONTAINS $search_term))
                RETURN b.name as name, b.latitude as latitude, b.longitude as longitude, 'property_match' as match_type
                LIMIT 1
            """
            text_result = sess.run(_q(text_query), search_term=search_term)
            text_record = text_result.single()
            if text_record:
                self._log(f"[NEO4J] ✅ Found via property search: {text_record['name']}")
                return {
                    "id": text_record["name"],
                    "name": text_record["name"],
                    "latitude": text_record["latitude"],
                    "longitude": text_record["longitude"],
                    "match_type": "property"
                }
            self._log(f"[NEO4J] No exact match, trying semantic search for '{search_term}'...")
            semantic_result = self._semantic_building_search(search_term)
            if semantic_result:
                return semantic_result
            if search_term != original_search:
                semantic_result = self._semantic_building_search(original_search)
                if semantic_result:
                    return semantic_result
            return None

        if session:
            return do_search(session)
        else:
            with self.driver.session(database=self.database) as new_session:
                return do_search(new_session)

    def _get_building_by_exact_id(self, session, building_id: str) -> Dict:
        query = """
            MATCH (b:Building)
            WHERE b.name = $building_id
            OPTIONAL MATCH (b)-[:ADJACENT_TO]-(nearby:Building)
            OPTIONAL MATCH (b)-[onstreet:ON_STREET]->(street:Street)
            OPTIONAL MATCH (b)-[:ACCESSIBLE_STOP]->(stop:Stop)
            OPTIONAL MATCH (sensor:Sensor)-[:NEAR_BUILDING]->(b)
            RETURN b as building,
                   collect(DISTINCT {name: nearby.name, type: 'Building'}) as nearby_buildings,
                   collect(DISTINCT {name: street.name, distance_m: onstreet.distance_m}) as streets,
                   collect(DISTINCT {name: sensor.name, type: sensor.type}) as sensors,
                   collect(DISTINCT {name: stop.name, lines: stop.lines}) as nearest_stops
        """
        result = session.run(_q(query), building_id=building_id)
        record = result.single()
        if not record:
            return {"success": False, "error": f"Building '{building_id}' not found"}
        building_node = dict(record["building"])
        streets = [s for s in record["streets"] if s.get("name")]
        return {
            "success": True,
            "building": building_node,
            "streets": streets,
            "street": streets[0]["name"] if streets else None,
            "nearby_buildings": [n for n in record["nearby_buildings"] if n.get("name")],
            "sensors": [s for s in record["sensors"] if s.get("name")],
            "nearest_stops": [s for s in record["nearest_stops"] if s.get("name")]
        }

    def _find_stop_or_building(self, location_name: str, session) -> Optional[Dict]:
        self._log(f"[NEO4J]   _find_stop_or_building: '{location_name}'")
        search_term = location_name.strip().lower()

        # Clean up stop-related suffixes for better matching
        # e.g., "opernhaus tram stop" -> "opernhaus"
        stop_search = search_term
        for suffix in [" tram stop", " bus stop", " train stop", " station", " stop", " haltestelle"]:
            if stop_search.endswith(suffix):
                stop_search = stop_search[:-len(suffix)].strip()
                break
        # Also remove "magdeburg" prefix if present (will try with and without)
        stop_search_no_prefix = stop_search
        for prefix in ["magdeburg ", "md "]:
            if stop_search_no_prefix.startswith(prefix):
                stop_search_no_prefix = stop_search_no_prefix[len(prefix):]
                break

        # 1. Check Stops - try multiple search variants
        stop_query = """
            MATCH (s:Stop)
            WHERE toLower(s.name) = $exact_search
               OR toLower(s.name) = $clean_search
               OR toLower(s.name) = $with_magdeburg
               OR toLower(s.name) CONTAINS $stop_core
            RETURN 'Stop' as type, s.name as name, s.latitude as latitude, s.longitude as longitude, s.lines as lines
            ORDER BY CASE
                WHEN toLower(s.name) = $exact_search THEN 0
                WHEN toLower(s.name) = $clean_search THEN 1
                WHEN toLower(s.name) = $with_magdeburg THEN 2
                ELSE 3
            END
            LIMIT 1
        """
        result = session.run(_q(stop_query),
                           exact_search=search_term,
                           clean_search=stop_search,
                           with_magdeburg=f"magdeburg {stop_search_no_prefix}",
                           stop_core=stop_search_no_prefix)
        record = result.single()
        if record:
            self._log(f"[NEO4J]   ✅ Found as Stop: {record['name']}")
            return {
                "type": "Stop",
                "name": record["name"],
                "latitude": record["latitude"],
                "longitude": record["longitude"],
                "lines": record["lines"]
            }

        # 1b. Semantic stop search (handles compound words like "Altermarkt" -> "Alter Markt")
        self._log(f"[NEO4J]   Trying semantic stop search...")
        semantic_stop = self._semantic_stop_search(location_name)
        if semantic_stop:
            self._log(f"[NEO4J]   ✅ Found as Stop (semantic): {semantic_stop['name']}")
            return semantic_stop

        # 2. Check Buildings FIRST (campus buildings take priority over POIs)
        # This ensures "mensa" matches campus Mensa (Building 27) not "Mensa Herrenkrug" POI
        self._log(f"[NEO4J]   Not a stop, checking buildings...")
        building = self._find_building_universal(location_name, session)
        if building:
            self._log(f"[NEO4J]   ✅ Found as Building: {building['name']}")
            return {
                "type": "Building",
                "name": building["name"],
                "latitude": building["latitude"],
                "longitude": building["longitude"]
            }

        # 3. Check POIs - only if no building found (for restaurants, cafes, etc.)
        self._log(f"[NEO4J]   Not a building, checking POIs...")
        poi_query = """
            MATCH (p:POI)
            WHERE toLower(p.name) = $exact_search
               OR toLower(p.name) CONTAINS $search
            RETURN 'POI' as type, p.name as name, p.latitude as latitude, p.longitude as longitude,
                   p.category as category, p.cuisine as cuisine
            ORDER BY CASE WHEN toLower(p.name) = $exact_search THEN 0 ELSE 1 END
            LIMIT 1
        """
        result = session.run(_q(poi_query), exact_search=search_term, search=search_term)
        record = result.single()
        if record:
            self._log(f"[NEO4J]   ✅ Found as POI: {record['name']} ({record['category']})")
            return {
                "type": "POI",
                "name": record["name"],
                "latitude": record["latitude"],
                "longitude": record["longitude"],
                "category": record.get("category"),
                "cuisine": record.get("cuisine")
            }

        # 4. Fallback to find_any_location (fuzzy + word-by-word matching)
        self._log(f"[NEO4J]   Trying fuzzy fallback for: {location_name}")
        fallback = self.find_any_location(location_name, limit=1)
        if fallback.get("success") and fallback.get("results"):
            loc = fallback["results"][0]
            coords = loc.get("coordinates", {})
            lat = coords.get("latitude") or loc.get("latitude")
            lon = coords.get("longitude") or loc.get("longitude")
            if lat and lon:
                loc_type = loc.get("type", "Building")
                self._log(f"[NEO4J]   ✅ Found via fuzzy fallback: {loc['name']} ({loc_type})")
                return {
                    "type": loc_type,
                    "name": loc["name"],
                    "latitude": lat,
                    "longitude": lon
                }

        self._log(f"[NEO4J]   ❌ Location not found: {location_name}")
        return None

    def calculate_distance(self, point1: Coordinates, point2: Coordinates) -> int:
        """Haversine distance in meters between two Coordinates."""
        from math import radians, sin, cos, sqrt, atan2
        R = 6371000
        lat1_rad = radians(point1.lat)
        lat2_rad = radians(point2.lat)
        delta_lat = radians(point2.lat - point1.lat)
        delta_lon = radians(point2.lon - point1.lon)
        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return round(R * c)

    _calculate_distance = calculate_distance

    def find_nearest_stop(self, coords: Coordinates) -> Optional[Dict]:
        """Find the nearest transit stop to the given coordinates.
        Returns dict with name, lines, latitude, longitude, distance_meters or None.
        """
        with self.driver.session(database=self.database) as session:
            return self._find_nearest_stop(session, coords)

    def _find_nearest_stop(self, session, coords: Coordinates) -> Optional[Dict]:
        self._log(f"[NEO4J]     _find_nearest_stop: lat={coords.lat}, lon={coords.lon}")
        query = """
            MATCH (s:Stop)
            WITH s, point.distance(
                point({latitude: $lat, longitude: $lon}),
                point({latitude: s.latitude, longitude: s.longitude})
            ) as distance
            ORDER BY distance
            LIMIT 1
            RETURN s.name as name, s.lines as lines, s.latitude as latitude, s.longitude as longitude,
                   round(distance) as distance_meters
        """
        try:
            result = session.run(_q(query), lat=coords.lat, lon=coords.lon)
            record = result.single()
            if record:
                self._log(f"[NEO4J]     ✅ Nearest stop: {record['name']} ({record['distance_meters']}m)")
                return {
                    "name": record["name"],
                    "lines": record["lines"] or [],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "distance_meters": record["distance_meters"]
                }
            self._log(f"[NEO4J]     ❌ No stops found")
        except Exception as e:
            self._log(f"[NEO4J]     ⚠️ Error finding nearest stop: {e}")
        return None
