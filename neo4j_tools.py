"""
Neo4j Transit Graph database interface for the Magdeburg Campus Assistant.
Provides methods for querying campus buildings, transit stops, routes, POIs, and sensors.
Includes semantic search for typo-tolerant building lookup and multi-transfer transit routing.
"""

from neo4j import GraphDatabase
from typing import Dict, List, Optional, Any, Tuple
import json
from difflib import SequenceMatcher
from collections import deque


class Neo4jTransitGraph:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j", verbose: bool = False):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database
        self._closed = False
        self._encoder = None
        self._building_cache = None
        self._building_embeddings = None
        self._fulltext_available = None  # None = not checked, True/False = checked
        self.verbose = verbose
        import atexit
        atexit.register(self.close)

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def close(self):
        if not self._closed and self.driver is not None:
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
                result = session.run("RETURN 1 as test")
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
                    session.run(stmt)

                result = session.run(
                    "SHOW FULLTEXT INDEXES YIELD name, state "
                    "WHERE name IN ['building_fts','stop_fts','poi_fts','landmark_fts'] "
                    "RETURN name, state"
                )
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
        if self._encoder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            self._log("   Loading semantic search for neo4j_tools...")
            self._encoder = SentenceTransformer('all-MiniLM-L6-v2')
            with self.driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (b:Building)
                    RETURN b as building, b.name as name,
                           b.latitude as latitude, b.longitude as longitude
                """)
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

    def _normalize_stop_name(self, stop_name: str) -> str:
        stop_name = stop_name.strip()
        if not stop_name.lower().startswith("magdeburg"):
            stop_name = f"Magdeburg {stop_name}"
        return stop_name

    def _normalize_line_name(self, line_name: str) -> str:
        line_name = line_name.strip()
        if line_name.replace(" ", "").isdigit():
            return line_name
        for prefix in ["Tram ", "Bus ", "Line ", "Linie "]:
            if line_name.startswith(prefix):
                line_name = line_name[len(prefix):]
                break
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
                num_result = sess.run(exact_num_query, variants=building_number_variants)
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
                exact_result = sess.run(exact_query, search_term=search_term)
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
                word_result = sess.run(word_query, search_term=search_term)
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
            alias_result = sess.run(alias_query, search_term=search_term)
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
            text_result = sess.run(text_query, search_term=search_term)
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
        result = session.run(query, building_id=building_id)
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

    def get_building_info(self, building_id: str) -> Dict:
        self._log(f"[NEO4J] get_building_info called with: '{building_id}'")
        with self.driver.session(database=self.database) as session:
            found_building = self._find_building_universal(building_id, session)
            if not found_building:
                return {
                    "success": False,
                    "searched_for": building_id,
                    "error": f"No building found matching '{building_id}'",
                    "suggestion": "Try describing what you're looking for or use building numbers 01-30"
                }
            match_type = found_building.get('match_type', 'exact')
            self._log(f"[NEO4J] ✅ Found: {found_building['name']} [match: {match_type}]")
            result = self._get_building_by_exact_id(session, found_building["id"])
            if result.get("success") and result.get("building"):
                result["building"]["match_type"] = match_type
            return result

    def find_building_by_function(self, query: str, limit: int = 10) -> Dict:
        self._log(f"[NEO4J] find_building_by_function called with: '{query}'")
        with self.driver.session(database=self.database) as session:
            buildings = []

            # Primary path: full-text search
            if self._ensure_fulltext_indexes():
                lucene_query = self._build_lucene_query(query)
                self._log(f"[NEO4J] FTS query: '{lucene_query}'")
                result = session.run("""
                    CALL db.index.fulltext.queryNodes("building_fts", $fts_query) YIELD node, score
                    RETURN node.name as name, node.function as function,
                           node.latitude as latitude, node.longitude as longitude, score
                    ORDER BY score DESC
                    LIMIT $limit
                """, fts_query=lucene_query, limit=limit)
                for record in result:
                    buildings.append({
                        "name": record["name"],
                        "function": record["function"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                    })

            # Fallback: CONTAINS search
            if not buildings:
                search_term = query.strip().lower()
                cypher = """
                    MATCH (b:Building)
                    WHERE toLower(b.name) CONTAINS $search_term
                       OR toLower(b.function) CONTAINS $search_term
                       OR toLower(b.note) CONTAINS $search_term
                       OR ANY(alias IN b.aliases WHERE toLower(alias) CONTAINS $search_term)
                       OR ANY(dept IN b.departments WHERE toLower(dept) CONTAINS $search_term)
                    RETURN b.name as name, b.function as function,
                           b.latitude as latitude, b.longitude as longitude
                    LIMIT $limit
                """
                result = session.run(cypher, search_term=search_term, limit=limit)
                for record in result:
                    buildings.append({
                        "name": record["name"],
                        "function": record["function"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                    })

            # Enrich with full building details
            for bldg in buildings:
                detail = self._get_building_by_exact_id(session, bldg["name"])
                if detail.get("success") and detail.get("building"):
                    full = detail["building"]
                    bldg["note"] = full.get("note")
                    bldg["departments"] = full.get("departments")
                    bldg["aliases"] = full.get("aliases")
                    bldg["address"] = full.get("address")
                    if detail.get("nearby_buildings"):
                        bldg["nearby_buildings"] = detail["nearby_buildings"]
                    if detail.get("sensors"):
                        bldg["sensors"] = detail["sensors"]
                    if detail.get("nearest_stops"):
                        bldg["nearest_stops"] = detail["nearest_stops"]

            if buildings:
                return {"success": True, "query": query, "count": len(buildings), "buildings": buildings}
            return {"success": False, "error": f"No buildings found matching '{query}'"}

    def _records_to_locations(self, result) -> List[Dict]:
        locations = []
        for record in result:
            loc = {
                "type": record["node_type"],
                "id": record["id"],
                "name": record["name"],
                "description": record["description"],
                "subtype": record["subtype"],
                "address": record["address"],
                "coordinates": {
                    "latitude": record["lat"],
                    "longitude": record["lon"]
                },
                "score": record.get("score", 100)
            }
            locations.append(loc)
        return locations

    def _enrich_with_street_info(self, session, locations: List[Dict]) -> List[Dict]:
        """Add street information to locations using ON_STREET relationship."""
        for loc in locations:
            loc_type = loc.get("type")
            loc_name = loc.get("name")
            if not loc_name:
                continue

            # Query ON_STREET relationship based on node type
            if loc_type == "Building":
                query = """
                    MATCH (b:Building {name: $name})-[r:ON_STREET]->(s:Street)
                    RETURN s.name as street_name, r.distance_m as distance
                    ORDER BY r.distance_m
                    LIMIT 3
                """
            elif loc_type == "Stop":
                query = """
                    MATCH (st:Stop {name: $name})-[r:ON_STREET]->(s:Street)
                    RETURN s.name as street_name, r.distance_m as distance
                    ORDER BY r.distance_m
                    LIMIT 3
                """
            elif loc_type == "POI":
                query = """
                    MATCH (p:POI {name: $name})-[r:ON_STREET]->(s:Street)
                    RETURN s.name as street_name, r.distance_m as distance
                    ORDER BY r.distance_m
                    LIMIT 3
                """
            else:
                continue

            try:
                result = session.run(query, name=loc_name)
                streets = []
                for record in result:
                    if record["street_name"]:
                        streets.append({
                            "name": record["street_name"],
                            "distance_m": record["distance"]
                        })
                if streets:
                    loc["streets"] = streets
                    loc["street"] = streets[0]["name"]
            except Exception as e:
                self._log(f"[NEO4J] ⚠️ Error getting street for {loc_name}: {e}")

        return locations

    def _enrich_buildings_with_details(self, session, locations: List[Dict]) -> List[Dict]:
        """Enrich Building-type results with full properties (function, note, departments, etc.)."""
        for loc in locations:
            if loc.get("type") != "Building":
                continue
            building_name = loc.get("name")
            if not building_name:
                continue
            try:
                detail = self._get_building_by_exact_id(session, building_name)
                if detail.get("success") and detail.get("building"):
                    bldg = detail["building"]
                    loc["function"] = bldg.get("function")
                    loc["note"] = bldg.get("note")
                    loc["departments"] = bldg.get("departments")
                    loc["aliases"] = bldg.get("aliases")
                    loc["address"] = bldg.get("address") or loc.get("address")
                    if bldg.get("fiware_type"):
                        loc["fiware_type"] = bldg["fiware_type"]
                    if detail.get("nearby_buildings"):
                        loc["nearby_buildings"] = detail["nearby_buildings"]
                    if detail.get("sensors"):
                        loc["sensors"] = detail["sensors"]
                    if detail.get("nearest_stops"):
                        loc["nearest_stops"] = detail["nearest_stops"]
                    self._log(f"[NEO4J]   Enriched building: {building_name}")
            except Exception as e:
                self._log(f"[NEO4J] ⚠️ Error enriching building {building_name}: {e}")
        return locations

    def _enrich_pois_with_details(self, session, locations: List[Dict]) -> List[Dict]:
        """Enrich POI-type results with aliases, note, and dietary_options from the database."""
        for loc in locations:
            if loc.get("type") != "POI":
                continue
            poi_name = loc.get("name")
            if not poi_name:
                continue
            try:
                query = """
                    MATCH (p:POI {name: $name})
                    RETURN p.aliases as aliases, p.note as note,
                           p.dietary_options as dietary_options,
                           p.opening_hours as opening_hours,
                           p.phone as phone, p.website as website
                """
                result = session.run(query, name=poi_name)
                record = result.single()
                if record:
                    if record["aliases"]:
                        loc["aliases"] = record["aliases"]
                    if record["note"]:
                        loc["note"] = record["note"]
                    if record["dietary_options"]:
                        loc["dietary_options"] = record["dietary_options"]
                    if record["opening_hours"]:
                        loc["opening_hours"] = record["opening_hours"]
                    if record["phone"]:
                        loc["phone"] = record["phone"]
                    if record["website"]:
                        loc["website"] = record["website"]
                    self._log(f"[NEO4J]   Enriched POI: {poi_name}")
            except Exception as e:
                self._log(f"[NEO4J] ⚠️ Error enriching POI {poi_name}: {e}")
        return locations

    # --- Full-text search (Lucene) ---

    _LUCENE_SPECIAL = set('+-&|!(){}[]^"~*?:\\/')

    @staticmethod
    def _escape_lucene(term: str) -> str:
        """Escape Lucene special characters in a search term."""
        out = []
        for ch in term:
            if ch in Neo4jTransitGraph._LUCENE_SPECIAL:
                out.append('\\')
            out.append(ch)
        return ''.join(out)

    @staticmethod
    def _build_lucene_query(search_term: str) -> str:
        """Build a Lucene query string from user input.

        - Strips stop words (EN + DE)
        - Words >= 4 chars: word~1 (fuzzy) + word^2 (exact boost)
        - Words < 4 chars: exact only (fuzzy on short words = too many false positives)
        """
        stop_words = {
            'the', 'a', 'an', 'of', 'and', 'or', 'in', 'at', 'to', 'for',
            'is', 'are', 'where', 'what', 'how', 'which', 'who', 'near',
            'der', 'die', 'das', 'ein', 'eine', 'und', 'oder', 'am', 'im',
            'von', 'zu', 'für', 'ist', 'sind', 'wo', 'was', 'wie',
        }

        raw_words = search_term.strip().lower().split()
        words = [w for w in raw_words if w not in stop_words and len(w) > 1]

        if not words:
            words = [w for w in raw_words if len(w) > 1]

        if not words:
            return Neo4jTransitGraph._escape_lucene(search_term.strip())

        parts = []
        for w in words:
            escaped = Neo4jTransitGraph._escape_lucene(w)
            if len(w) >= 4:
                parts.append(f"{escaped}~1 {escaped}^2")
            else:
                parts.append(escaped)

        return " ".join(parts)

    def _record_to_location(self, record) -> Dict:
        """Convert a single query record to a location dict."""
        return {
            "type": record["node_type"],
            "id": record["id"],
            "name": record["name"],
            "description": record["description"],
            "subtype": record["subtype"],
            "address": record["address"],
            "coordinates": {
                "latitude": record["lat"],
                "longitude": record["lon"]
            },
            "score": record.get("score", 0)
        }

    def _search_fulltext(self, session, search_term: str, limit: int) -> List[Dict]:
        """Search all node types using full-text indexes. Returns unified location list."""
        lucene_query = self._build_lucene_query(search_term)
        self._log(f"[NEO4J] FTS Lucene query: '{lucene_query}'")

        locations = []

        queries = [
            ("building_fts", """
                CALL db.index.fulltext.queryNodes("building_fts", $fts_query) YIELD node, score
                RETURN 'Building' as node_type, node.name as id, node.name as name,
                       node.function as description, null as subtype, node.address as address,
                       node.latitude as lat, node.longitude as lon, score
                LIMIT $limit
            """),
            ("stop_fts", """
                CALL db.index.fulltext.queryNodes("stop_fts", $fts_query) YIELD node, score
                RETURN 'Stop' as node_type, node.id as id, node.name as name,
                       'Transit stop' as description, node.type as subtype, null as address,
                       node.latitude as lat, node.longitude as lon, score
                LIMIT $limit
            """),
            ("poi_fts", """
                CALL db.index.fulltext.queryNodes("poi_fts", $fts_query) YIELD node, score
                RETURN 'POI' as node_type, node.fiware_id as id, node.name as name,
                       node.type as description, node.cuisine as subtype, node.address as address,
                       node.latitude as lat, node.longitude as lon, score
                LIMIT $limit
            """),
            ("landmark_fts", """
                CALL db.index.fulltext.queryNodes("landmark_fts", $fts_query) YIELD node, score
                RETURN 'Landmark' as node_type, node.id as id, node.name as name,
                       node.description as description, null as subtype, null as address,
                       node.latitude as lat, node.longitude as lon, score
                LIMIT $limit
            """),
        ]

        for index_name, cypher in queries:
            try:
                result = session.run(cypher, fts_query=lucene_query, limit=limit)
                for record in result:
                    locations.append(self._record_to_location(record))
            except Exception as e:
                self._log(f"[NEO4J] {index_name} query error: {e}")

        locations.sort(key=lambda x: x.get("score", 0), reverse=True)
        self._log(f"[NEO4J] FTS returned {len(locations)} total results")
        return locations

    # --- Legacy CONTAINS-based search (fallback) ---

    def _search_locations_exact(self, session, search_lower: str, search_term: str, limit: int) -> List[Dict]:
        query = """
            MATCH (b:Building)
            WHERE toLower(b.name) CONTAINS $search
               OR toLower(b.function) CONTAINS $search
               OR any(alias IN b.aliases WHERE toLower(alias) CONTAINS $search)
               OR toLower(COALESCE(b.note, '')) CONTAINS $search
               OR any(dept IN COALESCE(b.departments, []) WHERE toLower(dept) CONTAINS $search)
            RETURN 'Building' as node_type, b.name as id, b.name as name,
                   b.function as description, null as subtype, b.address as address,
                   b.latitude as lat, b.longitude as lon, 100 as score
            LIMIT $limit
            UNION
            MATCH (s:Stop)
            WHERE toLower(s.name) CONTAINS $search OR toLower(s.id) CONTAINS $search
            RETURN 'Stop' as node_type, s.id as id, s.name as name,
                   'Transit stop' as description, s.type as subtype, null as address,
                   s.latitude as lat, s.longitude as lon, 100 as score
            LIMIT $limit
            UNION
            MATCH (p:POI)
            WHERE toLower(p.name) CONTAINS $search
               OR toLower(p.type) CONTAINS $search
               OR toLower(p.cuisine) CONTAINS $search
            RETURN 'POI' as node_type, p.fiware_id as id, p.name as name,
                   p.type as description, p.cuisine as subtype, p.address as address,
                   p.latitude as lat, p.longitude as lon, 100 as score
            LIMIT $limit
            UNION
            MATCH (l:Landmark)
            WHERE toLower(l.name) CONTAINS $search OR toLower(l.description) CONTAINS $search
            RETURN 'Landmark' as node_type, l.id as id, l.name as name,
                   l.description as description, null as subtype, null as address,
                   l.latitude as lat, l.longitude as lon, 100 as score
            LIMIT $limit
        """
        result = session.run(query, search=search_lower, limit=limit)
        return self._records_to_locations(result)

    def _search_locations_by_words(self, session, words: List[str], limit: int) -> List[Dict]:
        if not words:
            return []

        # --- Building: word conditions and scoring ---
        bldg_conditions = " OR ".join([
            f"toLower(b.name) CONTAINS $word{i} OR toLower(b.function) CONTAINS $word{i}"
            f" OR toLower(COALESCE(b.note,'')) CONTAINS $word{i}"
            f" OR ANY(alias IN COALESCE(b.aliases,[]) WHERE toLower(alias) CONTAINS $word{i})"
            f" OR ANY(dept IN COALESCE(b.departments,[]) WHERE toLower(dept) CONTAINS $word{i})"
            for i in range(len(words))
        ])
        bldg_score_parts = []
        for i in range(len(words)):
            bldg_score_parts.append(f"CASE WHEN toLower(b.name) CONTAINS $word{i} THEN 30 ELSE 0 END")
            bldg_score_parts.append(f"CASE WHEN ANY(alias IN COALESCE(b.aliases,[]) WHERE toLower(alias) CONTAINS $word{i}) THEN 25 ELSE 0 END")
            bldg_score_parts.append(f"CASE WHEN toLower(b.function) CONTAINS $word{i} THEN 10 ELSE 0 END")
            bldg_score_parts.append(f"CASE WHEN toLower(COALESCE(b.note,'')) CONTAINS $word{i} THEN 5 ELSE 0 END")
        bldg_score_expr = " + ".join(bldg_score_parts)

        # --- Stop: word conditions and scoring ---
        stop_conditions = " OR ".join([
            f"toLower(s.name) CONTAINS $word{i} OR toLower(s.id) CONTAINS $word{i}"
            for i in range(len(words))
        ])
        stop_score_parts = []
        for i in range(len(words)):
            stop_score_parts.append(f"CASE WHEN toLower(s.name) CONTAINS $word{i} THEN 30 ELSE 0 END")
        stop_score_expr = " + ".join(stop_score_parts)

        # --- POI: word conditions and scoring ---
        poi_conditions = " OR ".join([
            f"toLower(p.name) CONTAINS $word{i} OR toLower(p.type) CONTAINS $word{i}"
            f" OR toLower(COALESCE(p.cuisine,'')) CONTAINS $word{i}"
            f" OR ANY(alias IN COALESCE(p.aliases,[]) WHERE toLower(alias) CONTAINS $word{i})"
            f" OR toLower(COALESCE(p.note,'')) CONTAINS $word{i}"
            for i in range(len(words))
        ])
        poi_score_parts = []
        for i in range(len(words)):
            poi_score_parts.append(f"CASE WHEN toLower(p.name) CONTAINS $word{i} THEN 30 ELSE 0 END")
            poi_score_parts.append(f"CASE WHEN ANY(alias IN COALESCE(p.aliases,[]) WHERE toLower(alias) CONTAINS $word{i}) THEN 25 ELSE 0 END")
            poi_score_parts.append(f"CASE WHEN toLower(p.type) CONTAINS $word{i} THEN 10 ELSE 0 END")
            poi_score_parts.append(f"CASE WHEN toLower(COALESCE(p.cuisine,'')) CONTAINS $word{i} THEN 5 ELSE 0 END")
            poi_score_parts.append(f"CASE WHEN toLower(COALESCE(p.note,'')) CONTAINS $word{i} THEN 5 ELSE 0 END")
        poi_score_expr = " + ".join(poi_score_parts)

        # --- Landmark: word conditions and scoring ---
        lmk_conditions = " OR ".join([
            f"toLower(l.name) CONTAINS $word{i} OR toLower(COALESCE(l.description,'')) CONTAINS $word{i}"
            for i in range(len(words))
        ])
        lmk_score_parts = []
        for i in range(len(words)):
            lmk_score_parts.append(f"CASE WHEN toLower(l.name) CONTAINS $word{i} THEN 30 ELSE 0 END")
            lmk_score_parts.append(f"CASE WHEN toLower(COALESCE(l.description,'')) CONTAINS $word{i} THEN 10 ELSE 0 END")
        lmk_score_expr = " + ".join(lmk_score_parts)

        query = f"""
            MATCH (b:Building)
            WHERE {bldg_conditions}
            WITH b, ({bldg_score_expr}) as score
            RETURN 'Building' as node_type, b.name as id, b.name as name,
                   b.function as description, null as subtype, b.address as address,
                   b.latitude as lat, b.longitude as lon, score
            ORDER BY score DESC
            LIMIT $limit
            UNION
            MATCH (s:Stop)
            WHERE {stop_conditions}
            WITH s, ({stop_score_expr}) as score
            RETURN 'Stop' as node_type, s.id as id, s.name as name,
                   'Transit stop' as description, s.type as subtype, null as address,
                   s.latitude as lat, s.longitude as lon, score
            ORDER BY score DESC
            LIMIT $limit
            UNION
            MATCH (p:POI)
            WHERE {poi_conditions}
            WITH p, ({poi_score_expr}) as score
            RETURN 'POI' as node_type, p.fiware_id as id, p.name as name,
                   p.type as description, p.cuisine as subtype, p.address as address,
                   p.latitude as lat, p.longitude as lon, score
            ORDER BY score DESC
            LIMIT $limit
            UNION
            MATCH (l:Landmark)
            WHERE {lmk_conditions}
            WITH l, ({lmk_score_expr}) as score
            RETURN 'Landmark' as node_type, l.id as id, l.name as name,
                   l.description as description, null as subtype, null as address,
                   l.latitude as lat, l.longitude as lon, score
            ORDER BY score DESC
            LIMIT $limit
        """
        params = {"limit": limit}
        for i, w in enumerate(words):
            params[f"word{i}"] = w
        result = session.run(query, **params)
        return self._records_to_locations(result)

    def _search_locations_single_keyword(self, session, keyword: str, limit: int) -> List[Dict]:
        query = """
            MATCH (b:Building)
            WHERE toLower(b.name) CONTAINS $keyword OR toLower(b.function) CONTAINS $keyword
               OR toLower(COALESCE(b.note, '')) CONTAINS $keyword
               OR ANY(alias IN COALESCE(b.aliases, []) WHERE toLower(alias) CONTAINS $keyword)
            RETURN 'Building' as node_type, b.name as id, b.name as name,
                   b.function as description, null as subtype, b.address as address,
                   b.latitude as lat, b.longitude as lon, 50 as score
            LIMIT $limit
            UNION
            MATCH (s:Stop)
            WHERE toLower(s.name) CONTAINS $keyword OR toLower(s.id) CONTAINS $keyword
            RETURN 'Stop' as node_type, s.id as id, s.name as name,
                   'Transit stop' as description, s.type as subtype, null as address,
                   s.latitude as lat, s.longitude as lon, 50 as score
            LIMIT $limit
            UNION
            MATCH (p:POI)
            WHERE toLower(p.name) CONTAINS $keyword
               OR toLower(p.type) CONTAINS $keyword
               OR toLower(COALESCE(p.cuisine, '')) CONTAINS $keyword
            RETURN 'POI' as node_type, p.fiware_id as id, p.name as name,
                   p.type as description, p.cuisine as subtype, p.address as address,
                   p.latitude as lat, p.longitude as lon, 50 as score
            LIMIT $limit
            UNION
            MATCH (l:Landmark)
            WHERE toLower(l.name) CONTAINS $keyword
               OR toLower(COALESCE(l.description, '')) CONTAINS $keyword
            RETURN 'Landmark' as node_type, l.id as id, l.name as name,
                   l.description as description, null as subtype, null as address,
                   l.latitude as lat, l.longitude as lon, 50 as score
            LIMIT $limit
        """
        result = session.run(query, keyword=keyword, limit=limit)
        return self._records_to_locations(result)

    def _boost_name_matches(self, locations: List[Dict], search_term: str) -> List[Dict]:
        """Post-process BM25 results with field-priority and word-specificity boosting.

        BM25 handles term rarity at the index level, but it cannot distinguish
        which *field* a match came from (name vs note). This method compensates
        by boosting name matches and penalizing common words.
        """
        stop_words = {'the', 'a', 'an', 'of', 'and', 'or', 'in', 'at', 'to', 'for', 'is', 'are', 'where', 'what', 'how', 'near'}
        search_lower = search_term.strip().lower()
        words = [w for w in search_lower.split() if w not in stop_words and len(w) > 2]

        if not words or not locations:
            return locations

        # Count how many results contain each query word (for specificity)
        word_freq = {}
        for w in words:
            count = 0
            for loc in locations:
                text = " ".join([
                    (loc.get("name") or "").lower(),
                    (loc.get("description") or "").lower(),
                    (loc.get("note") or "").lower(),
                    " ".join(loc.get("aliases") or []).lower(),
                    (loc.get("subtype") or "").lower(),
                ])
                if w in text:
                    count += 1
            word_freq[w] = count

        for loc in locations:
            name_lower = (loc.get("name") or "").lower()
            all_text = " ".join([
                name_lower,
                (loc.get("description") or "").lower(),
                (loc.get("note") or "").lower(),
                " ".join(loc.get("aliases") or []).lower(),
                (loc.get("subtype") or "").lower(),
            ])

            bonus = 0.0
            for w in words:
                if w not in all_text:
                    continue

                # Specificity: rare words get much bigger bonus
                freq = word_freq.get(w, 0)
                if freq <= 1:
                    bonus += 10.0
                elif freq <= 3:
                    bonus += 3.0
                else:
                    bonus += 0.5

                # Field priority: name matches get extra boost
                if w in name_lower:
                    bonus += 2.0

            # Full phrase in name: strong signal
            if search_lower in name_lower:
                bonus += 5.0

            loc["score"] = loc.get("score", 0) + bonus

        locations.sort(key=lambda x: x.get("score", 0), reverse=True)
        return locations

    def _search_locations_fallback(self, session, search_term: str, limit: int) -> List[Dict]:
        """Fallback search using CONTAINS when full-text indexes are unavailable."""
        search_lower = search_term.strip().lower()
        stop_words = {'the', 'a', 'an', 'of', 'and', 'or', 'in', 'at', 'to', 'for', 'is', 'are', 'where', 'what', 'how'}
        words = [w for w in search_lower.split() if w not in stop_words and len(w) > 2]

        self._log(f"[NEO4J] Fallback: Strategy 1 - Exact phrase match...")
        locations = self._search_locations_exact(session, search_lower, search_term, limit)
        if locations:
            self._log(f"[NEO4J] Fallback: Found {len(locations)} via exact match")
            return locations

        if words:
            self._log(f"[NEO4J] Fallback: Strategy 2 - Word-by-word with words: {words}")
            locations = self._search_locations_by_words(session, words, limit)
            if locations:
                self._log(f"[NEO4J] Fallback: Found {len(locations)} via word matching")
                return locations

        if words:
            self._log(f"[NEO4J] Fallback: Strategy 3 - Single keyword '{words[0]}'")
            locations = self._search_locations_single_keyword(session, words[0], limit)

        return locations

    def find_any_location(self, search_term: str, limit: int = 5) -> Dict:
        self._log(f"[NEO4J] find_any_location called with: '{search_term}'")
        fetch_limit = max(limit, 10)

        try:
            with self.driver.session(database=self.database) as session:
                locations = []

                # Primary path: full-text search (BM25 scoring + fuzzy matching)
                if self._ensure_fulltext_indexes():
                    self._log(f"[NEO4J] Using full-text search")
                    locations = self._search_fulltext(session, search_term, fetch_limit)

                # Fallback: old CONTAINS-based search
                if not locations:
                    self._log(f"[NEO4J] Falling back to CONTAINS search")
                    locations = self._search_locations_fallback(session, search_term, fetch_limit)

                if not locations:
                    self._log(f"[NEO4J] No locations found for: '{search_term}'")
                    return {
                        "success": False,
                        "error": f"No locations found matching '{search_term}'",
                        "suggestion": "Try a different search term or check spelling"
                    }

                # Enrich with relationship data
                locations = self._enrich_with_street_info(session, locations)
                locations = self._enrich_buildings_with_details(session, locations)
                locations = self._enrich_pois_with_details(session, locations)

                # Lightweight name-match boost (compensates for lack of per-field boosting in FTS)
                locations = self._boost_name_matches(locations, search_term)

                locations = locations[:limit]
                self._log(f"[NEO4J] Found {len(locations)} location(s)")
                return {"success": True, "query": search_term, "count": len(locations), "results": locations}
        except Exception as e:
            self._log(f"[NEO4J] Error in find_any_location: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_nearby_buildings(self, building_id: str, limit: int = 5) -> Dict:
        self._log(f"[NEO4J] get_nearby_buildings called with: '{building_id}'")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_id, session)
            if not found:
                return {"success": False, "error": f"Building '{building_id}' not found"}
            query = """
                MATCH (b:Building {name: $name})-[:ADJACENT_TO]-(nearby:Building)
                RETURN nearby.name as name, nearby.function as function,
                       nearby.latitude as latitude, nearby.longitude as longitude
                LIMIT $limit
            """
            result = session.run(query, name=found["name"], limit=limit)
            nearby = []
            for record in result:
                nearby.append({
                    "name": record["name"],
                    "function": record["function"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"]
                })
            return {
                "success": True,
                "building": found["name"],
                "nearby_buildings": nearby,
                "count": len(nearby)
            }

    def get_landmark_info(self, landmark_name: str) -> Dict:
        self._log(f"[NEO4J] get_landmark_info called with: '{landmark_name}'")
        search_term = landmark_name.strip().lower()
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (l:Landmark)
                WHERE toLower(l.name) CONTAINS $search_term
                   OR toLower(l.description) CONTAINS $search_term
                RETURN l.name as name, l.description as description,
                       l.latitude as latitude, l.longitude as longitude
                LIMIT 1
            """
            result = session.run(query, search_term=search_term)
            record = result.single()
            if record:
                return {
                    "success": True,
                    "landmark": {
                        "name": record["name"],
                        "description": record["description"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"]
                    }
                }
            return {"success": False, "error": f"Landmark '{landmark_name}' not found"}

    def find_places(self, query_type: str = "search", place_type: str = "all",
                    cuisine: str = None, building_id: str = None, stop_name: str = None,
                    search_term: str = None, limit: int = 5) -> Dict:
        self._log(f"[NEO4J] find_places called: type={query_type}, place_type={place_type}, cuisine={cuisine}")
        with self.driver.session(database=self.database) as session:
            if query_type == "mensa_menu":
                query = """
                    MATCH (p:POI)
                    WHERE toLower(p.name) CONTAINS 'mensa' OR toLower(p.type) = 'mensa'
                    RETURN p.name as name, p.fiware_id as fiware_id, p.type as type,
                           p.latitude as latitude, p.longitude as longitude
                    LIMIT 1
                """
                result = session.run(query)
                record = result.single()
                if record:
                    return {
                        "success": True,
                        "place": {
                            "name": record["name"],
                            "type": record["type"],
                            "latitude": record["latitude"],
                            "longitude": record["longitude"]
                        },
                        "fiware_query": {"entity_id": record["fiware_id"]}
                    }
                return {"success": False, "error": "Mensa not found"}
            if building_id:
                return self.find_places_near_building(building_id, place_type, cuisine, limit=limit)
            if cuisine:
                return self.find_places_by_cuisine(cuisine, place_type, limit)
            if search_term:
                query = """
                    MATCH (p:POI)
                    WHERE toLower(p.name) CONTAINS $search
                       OR toLower(p.type) CONTAINS $search
                       OR toLower(p.cuisine) CONTAINS $search
                    RETURN p.name as name, p.type as type, p.cuisine as cuisine,
                           p.address as address, p.latitude as latitude, p.longitude as longitude
                    LIMIT $limit
                """
                result = session.run(query, search=search_term.lower(), limit=limit)
            else:
                type_filter = "WHERE toLower(p.type) = $place_type" if place_type != "all" else ""
                query = f"""
                    MATCH (p:POI)
                    {type_filter}
                    RETURN p.name as name, p.type as type, p.cuisine as cuisine,
                           p.address as address, p.latitude as latitude, p.longitude as longitude
                    LIMIT $limit
                """
                result = session.run(query, place_type=place_type.lower(), limit=limit)
            places = []
            for record in result:
                places.append({
                    "name": record["name"],
                    "type": record["type"],
                    "cuisine": record["cuisine"],
                    "address": record["address"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"]
                })
            return {"success": True, "count": len(places), "places": places}

    def find_places_near_building(self, building_id: str, place_type: str = "all",
                                   cuisine: str = None, radius_meters: int = 1000, limit: int = 5) -> Dict:
        self._log(f"[NEO4J] find_places_near_building: {building_id}, type={place_type}, cuisine={cuisine}")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_id, session)
            if not found:
                return {"success": False, "error": f"Building '{building_id}' not found"}
            conditions = []
            params = {"building_name": found["name"], "radius": radius_meters, "limit": limit}
            if place_type and place_type != "all":
                conditions.append("toLower(p.type) = $place_type")
                params["place_type"] = place_type.lower()
            if cuisine:
                conditions.append("toLower(p.cuisine) CONTAINS $cuisine")
                params["cuisine"] = cuisine.lower()
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            query = f"""
                MATCH (b:Building {{name: $building_name}})
                MATCH (p:POI)
                {where_clause}
                WITH b, p, point.distance(
                    point({{latitude: b.latitude, longitude: b.longitude}}),
                    point({{latitude: p.latitude, longitude: p.longitude}})
                ) as distance
                WHERE distance <= $radius
                RETURN p.name as name, p.type as type, p.cuisine as cuisine,
                       p.address as address, p.latitude as latitude, p.longitude as longitude,
                       round(distance) as distance_meters
                ORDER BY distance
                LIMIT $limit
            """
            result = session.run(query, **params)
            places = []
            for record in result:
                straight_dist = record["distance_meters"]
                # Estimate walking distance (~1.4x straight-line for urban areas)
                walking_dist = round(straight_dist * 1.4)
                # Walking speed ~80m/min (about 5 km/h)
                walking_time = max(1, round(walking_dist / 80))
                places.append({
                    "name": record["name"],
                    "type": record["type"],
                    "cuisine": record["cuisine"],
                    "address": record["address"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "distance_meters": straight_dist,
                    "walking_distance_meters": walking_dist,
                    "walking_time_minutes": walking_time,
                    "walking_time_text": f"{walking_time} min walk"
                })
            return {
                "success": True,
                "building": found["name"],
                "count": len(places),
                "places": places
            }

    def find_places_by_cuisine(self, cuisine: str, place_type: str = "Restaurant", limit: int = 5) -> Dict:
        self._log(f"[NEO4J] find_places_by_cuisine: {cuisine}")
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (p:POI)
                WHERE toLower(p.cuisine) CONTAINS $cuisine
                   AND ($place_type = 'all' OR toLower(p.type) = $place_type_lower)
                RETURN p.name as name, p.type as type, p.cuisine as cuisine,
                       p.address as address, p.latitude as latitude, p.longitude as longitude
                LIMIT $limit
            """
            result = session.run(query, cuisine=cuisine.lower(), place_type=place_type,
                                place_type_lower=place_type.lower(), limit=limit)
            places = []
            for record in result:
                places.append({
                    "name": record["name"],
                    "type": record["type"],
                    "cuisine": record["cuisine"],
                    "address": record["address"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"]
                })
            return {"success": True, "cuisine": cuisine, "count": len(places), "places": places}

    def get_poi_info(self, poi_name: str) -> Dict:
        """Get detailed info about a POI including street, nearest stop, and building."""
        self._log(f"[NEO4J] get_poi_info called with: '{poi_name}'")
        search_term = poi_name.strip().lower()
        # Also create a version without spaces for matching "Worldof Pizza" style names
        search_no_spaces = search_term.replace(" ", "")

        with self.driver.session(database=self.database) as session:
            # Flexible POI search
            find_query = """
                MATCH (p:POI)
                WHERE toLower(p.name) = $search_term
                   OR toLower(p.name) CONTAINS $search_term
                   OR toLower(replace(p.name, ' ', '')) CONTAINS $search_no_spaces
                   OR $search_no_spaces CONTAINS toLower(replace(p.name, ' ', ''))
                RETURN p.name as name
                ORDER BY CASE
                    WHEN toLower(p.name) = $search_term THEN 0
                    WHEN toLower(p.name) CONTAINS $search_term THEN 1
                    ELSE 2
                END
                LIMIT 1
            """
            find_result = session.run(find_query, search_term=search_term, search_no_spaces=search_no_spaces)
            find_record = find_result.single()

            if not find_record:
                return {"success": False, "error": f"POI '{poi_name}' not found"}

            poi_exact_name = find_record["name"]
            self._log(f"[NEO4J] ✅ Found POI: {poi_exact_name}")

            # Get full POI info with relationships
            info_query = """
                MATCH (p:POI {name: $poi_name})
                OPTIONAL MATCH (p)-[onstreet:ON_STREET]->(street:Street)
                OPTIONAL MATCH (p)-[:NEAREST_STOP]->(stop:Stop)
                OPTIONAL MATCH (p)-[:NEAREST_BUILDING]->(building:Building)
                RETURN p as poi,
                       collect(DISTINCT {name: street.name, distance_m: onstreet.distance_m}) as streets,
                       collect(DISTINCT {name: stop.name, lines: stop.lines}) as nearest_stops,
                       collect(DISTINCT {name: building.name}) as nearest_buildings
            """
            result = session.run(info_query, poi_name=poi_exact_name)
            record = result.single()

            if not record:
                return {"success": False, "error": f"POI '{poi_name}' not found"}

            poi_node = dict(record["poi"])
            streets = [s for s in record["streets"] if s.get("name")]
            nearest_stops = [s for s in record["nearest_stops"] if s.get("name")]
            nearest_buildings = [b for b in record["nearest_buildings"] if b.get("name")]

            return {
                "success": True,
                "poi": poi_node,
                "name": poi_node.get("name"),
                "type": poi_node.get("type"),
                "cuisine": poi_node.get("cuisine"),
                "address": poi_node.get("address"),
                "streets": streets,
                "street": streets[0]["name"] if streets else None,
                "nearest_stops": nearest_stops,
                "nearest_stop": nearest_stops[0]["name"] if nearest_stops else None,
                "nearest_buildings": nearest_buildings,
                "nearest_building": nearest_buildings[0]["name"] if nearest_buildings else None
            }

    def find_places_near_coordinates(self, lat: float, lon: float, place_type: str = "all",
                                      cuisine: str = None, radius_meters: int = 1000, limit: int = 5) -> Dict:
        self._log(f"[NEO4J] find_places_near_coordinates: {lat}, {lon}")
        with self.driver.session(database=self.database) as session:
            conditions = []
            params = {"lat": lat, "lon": lon, "radius": radius_meters, "limit": limit}
            if place_type and place_type != "all":
                conditions.append("toLower(p.type) = $place_type")
                params["place_type"] = place_type.lower()
            if cuisine:
                conditions.append("toLower(p.cuisine) CONTAINS $cuisine")
                params["cuisine"] = cuisine.lower()
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            query = f"""
                MATCH (p:POI)
                {where_clause}
                WITH p, point.distance(
                    point({{latitude: $lat, longitude: $lon}}),
                    point({{latitude: p.latitude, longitude: p.longitude}})
                ) as distance
                WHERE distance <= $radius
                RETURN p.name as name, p.type as type, p.cuisine as cuisine,
                       p.address as address, p.latitude as latitude, p.longitude as longitude,
                       round(distance) as distance_meters
                ORDER BY distance
                LIMIT $limit
            """
            result = session.run(query, **params)
            places = []
            for record in result:
                straight_dist = record["distance_meters"]
                walking_dist = round(straight_dist * 1.4)
                walking_time = max(1, round(walking_dist / 80))
                places.append({
                    "name": record["name"],
                    "type": record["type"],
                    "cuisine": record["cuisine"],
                    "address": record["address"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "distance_meters": straight_dist,
                    "walking_distance_meters": walking_dist,
                    "walking_time_minutes": walking_time,
                    "walking_time_text": f"{walking_time} min walk"
                })
            return {"success": True, "count": len(places), "places": places}

    def get_stop_info(self, stop_name: str) -> Dict:
        self._log(f"[NEO4J] get_stop_info called with: '{stop_name}'")
        normalized = self._normalize_stop_name(stop_name)
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (s:Stop)
                WHERE toLower(s.name) CONTAINS $search OR s.name = $normalized
                RETURN s.id as id, s.name as name, s.latitude as latitude, s.longitude as longitude,
                       s.lines as lines, s.type as type
                LIMIT 1
            """
            result = session.run(query, search=stop_name.lower(), normalized=normalized)
            record = result.single()
            if record:
                return {
                    "success": True,
                    "stop": {
                        "id": record["id"],
                        "name": record["name"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                        "lines": record["lines"] or [],
                        "type": record["type"]
                    }
                }
            return {"success": False, "error": f"Stop '{stop_name}' not found"}

    def get_line_info(self, line_name: str) -> Dict:
        self._log(f"[NEO4J] get_line_info called with: '{line_name}'")
        normalized = self._normalize_line_name(line_name)
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (s1:Stop)-[r:NEXT_STOP {line: $line}]->(s2:Stop)
                WITH $line as line, collect(DISTINCT s1.name) + collect(DISTINCT s2.name) as all_stops
                UNWIND all_stops as stop_name
                WITH line, collect(DISTINCT stop_name) as stops
                RETURN line, stops, size(stops) as stop_count
            """
            result = session.run(query, line=normalized)
            record = result.single()
            if record:
                return {
                    "success": True,
                    "line": {
                        "name": record["line"],
                        "stops": record["stops"],
                        "stop_count": record["stop_count"]
                    }
                }
            return {"success": False, "error": f"Line '{line_name}' not found"}

    def get_nearest_tram_from_building(self, building_id: str) -> Dict:
        self._log(f"[NEO4J] get_nearest_tram_from_building called with: '{building_id}'")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_id, session)
            if not found:
                return {"success": False, "error": f"Building '{building_id}' not found"}
            query = """
                MATCH (b:Building {name: $name})
                MATCH (s:Stop)
                WITH b, s, point.distance(
                    point({latitude: b.latitude, longitude: b.longitude}),
                    point({latitude: s.latitude, longitude: s.longitude})
                ) as distance
                ORDER BY distance
                LIMIT 3
                RETURN s.name as name, s.lines as lines, round(distance) as distance_meters
            """
            result = session.run(query, name=found["name"])
            stops = []
            for record in result:
                stops.append({
                    "name": record["name"],
                    "lines": record["lines"] or [],
                    "distance_meters": record["distance_meters"]
                })
            return {
                "success": True,
                "building": found["name"],
                "nearest_stops": stops
            }

    def find_best_transfer_between_lines(self, line1: str, line2: str) -> Dict:
        self._log(f"[NEO4J] find_best_transfer_between_lines: {line1} <-> {line2}")
        l1 = self._normalize_line_name(line1)
        l2 = self._normalize_line_name(line2)
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (s:Stop)
                WHERE $line1 IN s.lines AND $line2 IN s.lines
                RETURN s.name as name, s.latitude as latitude, s.longitude as longitude, s.lines as lines
            """
            result = session.run(query, line1=l1, line2=l2)
            transfer_stops = []
            for record in result:
                transfer_stops.append({
                    "name": record["name"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "lines": record["lines"]
                })
            if transfer_stops:
                return {
                    "success": True,
                    "line1": l1,
                    "line2": l2,
                    "transfer_stops": transfer_stops,
                    "count": len(transfer_stops)
                }
            return {"success": False, "error": f"No transfer point found between {line1} and {line2}"}

    def find_transfer_hubs(self, min_lines: int = 2, limit: int = 10) -> Dict:
        self._log(f"[NEO4J] find_transfer_hubs called with min_lines={min_lines}")
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (s:Stop)
                WHERE size(s.lines) >= $min_lines
                RETURN s.name as name, s.lines as lines, size(s.lines) as line_count,
                       s.latitude as latitude, s.longitude as longitude
                ORDER BY line_count DESC
                LIMIT $limit
            """
            result = session.run(query, min_lines=min_lines, limit=limit)
            hubs = []
            for record in result:
                hubs.append({
                    "name": record["name"],
                    "lines": record["lines"],
                    "line_count": record["line_count"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"]
                })
            return {"success": True, "transfer_hubs": hubs, "count": len(hubs)}

    def get_directions_between_buildings(self, from_building: str, to_building: str) -> Dict:
        self._log(f"[NEO4J] get_directions_between_buildings: {from_building} -> {to_building}")
        with self.driver.session(database=self.database) as session:
            from_found = self._find_building_universal(from_building, session)
            to_found = self._find_building_universal(to_building, session)
            if not from_found:
                return {"success": False, "error": f"Origin building '{from_building}' not found"}
            if not to_found:
                return {"success": False, "error": f"Destination building '{to_building}' not found"}
            query = """
                MATCH (b1:Building {name: $from_name}), (b2:Building {name: $to_name})
                WITH b1, b2, point.distance(
                    point({latitude: b1.latitude, longitude: b1.longitude}),
                    point({latitude: b2.latitude, longitude: b2.longitude})
                ) as distance
                RETURN b1.name as from_name, b1.latitude as from_lat, b1.longitude as from_lon,
                       b2.name as to_name, b2.latitude as to_lat, b2.longitude as to_lon,
                       round(distance) as distance_meters
            """
            result = session.run(query, from_name=from_found["name"], to_name=to_found["name"])
            record = result.single()
            if record:
                walk_time_min = round(record["distance_meters"] / 80)
                return {
                    "success": True,
                    "from": {
                        "name": record["from_name"],
                        "latitude": record["from_lat"],
                        "longitude": record["from_lon"]
                    },
                    "to": {
                        "name": record["to_name"],
                        "latitude": record["to_lat"],
                        "longitude": record["to_lon"]
                    },
                    "distance_meters": record["distance_meters"],
                    "walk_time_minutes": walk_time_min
                }
            return {"success": False, "error": "Could not calculate directions"}

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
        result = session.run(stop_query,
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
        result = session.run(poi_query, exact_search=search_term, search=search_term)
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

    def get_multimodal_route(self, origin: str, destination: str) -> Dict:
        self._log(f"[NEO4J] get_multimodal_route: {origin} -> {destination}")
        with self.driver.session(database=self.database) as session:
            self._log(f"[NEO4J]   Finding origin location...")
            origin_loc = self._find_stop_or_building(origin, session)
            self._log(f"[NEO4J]   Finding destination location...")
            dest_loc = self._find_stop_or_building(destination, session)
            if not origin_loc:
                return {"success": False, "error": f"Origin '{origin}' not found"}
            if not dest_loc:
                return {"success": False, "error": f"Destination '{destination}' not found"}
            self._log(f"[NEO4J]   Origin: {origin_loc['name']} ({origin_loc['type']})")
            self._log(f"[NEO4J]   Destination: {dest_loc['name']} ({dest_loc['type']})")
            direct_distance = self._calculate_distance(
                origin_loc["latitude"], origin_loc["longitude"],
                dest_loc["latitude"], dest_loc["longitude"]
            )
            self._log(f"[NEO4J]   Direct distance: {direct_distance}m")
            if direct_distance < 400:
                walk_time = round(direct_distance / 80)
                self._log(f"[NEO4J]   Short distance - suggesting walking only")
                return {
                    "success": True,
                    "from": origin,
                    "to": destination,
                    "route": {
                        "segments": [{
                            "type": "walking",
                            "from": origin_loc["name"],
                            "to": dest_loc["name"],
                            "distance_meters": direct_distance,
                            "walk_time_minutes": walk_time
                        }],
                        "lines_used": [],
                        "total_stops": 0,
                        "transfers": 0,
                        "estimated_duration_minutes": walk_time,
                        "estimated_duration_text": f"{walk_time} min",
                        "route_type": "walking_only",
                        "note": "Distance is short, walking recommended"
                    }
                }
            origin_stop = None
            dest_stop = None
            walk_to_start = None
            walk_from_end = None
            if origin_loc["type"] == "Stop":
                origin_stop = origin_loc
            else:
                self._log(f"[NEO4J]   Finding nearest stop to origin...")
                nearest = self._find_nearest_stop(session, origin_loc["latitude"], origin_loc["longitude"])
                if nearest:
                    self._log(f"[NEO4J]   Nearest stop to origin: {nearest['name']}")
                    origin_stop = nearest
                    walk_to_start = {
                        "type": "walking",
                        "from": origin_loc["name"],
                        "to": nearest["name"],
                        "distance_meters": nearest.get("distance_meters", 0),
                        "walk_time_minutes": round(nearest.get("distance_meters", 0) / 80)
                    }
            if dest_loc["type"] == "Stop":
                dest_stop = dest_loc
            else:
                self._log(f"[NEO4J]   Finding nearest stop to destination...")
                nearest = self._find_nearest_stop(session, dest_loc["latitude"], dest_loc["longitude"])
                if nearest:
                    self._log(f"[NEO4J]   Nearest stop to destination: {nearest['name']}")
                    dest_stop = nearest
                    walk_from_end = {
                        "type": "walking",
                        "from": nearest["name"],
                        "to": dest_loc["name"],
                        "distance_meters": nearest.get("distance_meters", 0),
                        "walk_time_minutes": round(nearest.get("distance_meters", 0) / 80)
                    }
            if not origin_stop or not dest_stop:
                walk_time = round(direct_distance / 80)
                return {
                    "success": True,
                    "from": origin,
                    "to": destination,
                    "route": {
                        "segments": [{
                            "type": "walking",
                            "from": origin_loc["name"],
                            "to": dest_loc["name"],
                            "distance_meters": direct_distance,
                            "walk_time_minutes": walk_time
                        }],
                        "lines_used": [],
                        "total_stops": 0,
                        "transfers": 0,
                        "estimated_duration_minutes": walk_time,
                        "estimated_duration_text": f"{walk_time} min",
                        "route_type": "walking_only",
                        "note": "No transit stops found nearby"
                    }
                }
            if origin_stop["name"] == dest_stop["name"]:
                walk_time = round(direct_distance / 80)
                self._log(f"[NEO4J]   Same stop - walking only")
                return {
                    "success": True,
                    "from": origin,
                    "to": destination,
                    "route": {
                        "segments": [{
                            "type": "walking",
                            "from": origin_loc["name"],
                            "to": dest_loc["name"],
                            "distance_meters": direct_distance,
                            "walk_time_minutes": walk_time
                        }],
                        "lines_used": [],
                        "total_stops": 0,
                        "transfers": 0,
                        "estimated_duration_minutes": walk_time,
                        "estimated_duration_text": f"{walk_time} min",
                        "route_type": "walking_only",
                        "note": "Locations are near the same stop"
                    }
                }
            self._log(f"[NEO4J]   Finding transit route: {origin_stop['name']} -> {dest_stop['name']}...")
            transit_route = self._find_transit_route(session, origin_stop["name"], dest_stop["name"])
            self._log(f"[NEO4J]   Transit route found: {transit_route is not None}")
            if not transit_route:
                walk_time = round(direct_distance / 80)
                return {
                    "success": True,
                    "from": origin,
                    "to": destination,
                    "route": {
                        "segments": [{
                            "type": "walking",
                            "from": origin_loc["name"],
                            "to": dest_loc["name"],
                            "distance_meters": direct_distance,
                            "walk_time_minutes": walk_time
                        }],
                        "lines_used": [],
                        "total_stops": 0,
                        "transfers": 0,
                        "estimated_duration_minutes": walk_time,
                        "estimated_duration_text": f"{walk_time} min",
                        "route_type": "walking_only",
                        "note": "No transit route found between stops"
                    }
                }
            segments = []
            total_time = 0
            if walk_to_start:
                segments.append(walk_to_start)
                total_time += walk_to_start["walk_time_minutes"]
            if transit_route:
                segments.extend(transit_route.get("segments", []))
                total_time += transit_route.get("transit_time_minutes", 0)
            if walk_from_end:
                segments.append(walk_from_end)
                total_time += walk_from_end["walk_time_minutes"]
            lines_used = []
            total_stops = 0
            transfers = 0
            for seg in segments:
                if seg.get("type") == "transit":
                    if seg.get("line") and seg.get("line") not in lines_used:
                        if lines_used:
                            transfers += 1
                        lines_used.append(seg.get("line"))
                    total_stops += seg.get("stop_count", 0)
            walk_only_time = round(direct_distance / 80)
            route_type = "transit"
            if total_time > walk_only_time and direct_distance < 1500:
                route_type = "transit_optional"

            # Build step-by-step instructions for clarity
            step_by_step = []
            step_num = 1
            for seg in segments:
                if seg.get("type") == "walking":
                    dist = seg.get("distance_meters", 0)
                    walk_min = seg.get("walk_time_minutes", round(dist / 80))
                    step_by_step.append({
                        "step": step_num,
                        "type": "walk",
                        "instruction": f"Walk from {seg['from']} to {seg['to']}",
                        "from": seg["from"],
                        "to": seg["to"],
                        "distance_meters": dist,
                        "duration_minutes": walk_min
                    })
                    step_num += 1
                elif seg.get("type") == "transit":
                    board_stop = seg.get("from") or (seg.get("stops", [None])[0])
                    alight_stop = seg.get("to") or (seg.get("stops", [None])[-1])
                    step_by_step.append({
                        "step": step_num,
                        "type": "transit",
                        "instruction": f"Take {seg['line']} from {board_stop} to {alight_stop}",
                        "line": seg["line"],
                        "board_at": board_stop,
                        "alight_at": alight_stop,
                        "stops": seg.get("stop_count", len(seg.get("stops", []))),
                        "duration_minutes": seg.get("stop_count", 0) * 2
                    })
                    step_num += 1

            return {
                "success": True,
                "from": origin,
                "to": destination,
                "route": {
                    "segments": segments,
                    "step_by_step": step_by_step,
                    "lines_used": lines_used,
                    "total_stops": total_stops,
                    "transfers": transfers,
                    "estimated_duration_minutes": total_time,
                    "estimated_duration_text": f"{total_time} min",
                    "route_type": route_type
                },
                "alternative": {
                    "type": "walking",
                    "distance_meters": direct_distance,
                    "walk_time_minutes": walk_only_time
                } if route_type == "transit_optional" else None
            }

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> int:
        from math import radians, sin, cos, sqrt, atan2
        R = 6371000
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)
        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return round(R * c)

    def _find_nearest_stop(self, session, lat: float, lon: float) -> Optional[Dict]:
        self._log(f"[NEO4J]     _find_nearest_stop: lat={lat}, lon={lon}")
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
            result = session.run(query, lat=lat, lon=lon)
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

    def _find_transit_route(self, session, from_stop: str, to_stop: str) -> Optional[Dict]:
        self._log(f"[NEO4J]     _find_transit_route: {from_stop} -> {to_stop}")
        direct_route = self._find_direct_route_via_line(session, from_stop, to_stop)
        if direct_route:
            return direct_route
        self._log(f"[NEO4J]     No direct route, trying one transfer...")
        transfer_route = self._find_one_transfer_route(session, from_stop, to_stop)
        if transfer_route:
            return transfer_route
        self._log(f"[NEO4J]     No transit route found")
        return None

    def _find_direct_route_via_line(self, session, from_stop: str, to_stop: str) -> Optional[Dict]:
        self._log(f"[NEO4J]     Checking for direct route via SERVED_BY...")
        common_line_query = """
            MATCH (start:Stop {name: $from_stop})-[:SERVED_BY]->(line:Line)
            MATCH (end:Stop {name: $to_stop})-[:SERVED_BY]->(line)
            RETURN line.name as line_name
            LIMIT 1
        """
        try:
            result = session.run(common_line_query, from_stop=from_stop, to_stop=to_stop)
            record = result.single()
            if not record:
                self._log(f"[NEO4J]     No common line found")
                return None
            line_name = record["line_name"]
            self._log(f"[NEO4J]     Found common line: {line_name}")
        except Exception as e:
            self._log(f"[NEO4J]     ⚠️ Common line query failed: {e}")
            return None
        route_query = """
            MATCH path = (start:Stop {name: $from_stop})-[r:NEXT_STOP*1..50]->(end:Stop {name: $to_stop})
            WHERE all(rel in r WHERE rel.line = $line_name)
            WITH path, [s in nodes(path) | s.name] as stops
            RETURN stops, size(stops) as stop_count
            ORDER BY stop_count
            LIMIT 1
        """
        try:
            result = session.run(route_query, from_stop=from_stop, to_stop=to_stop, line_name=line_name)
            record = result.single()
            if record:
                self._log(f"[NEO4J]     ✅ Direct route found: {line_name} ({record['stop_count']} stops)")
                return {
                    "segments": [{
                        "type": "transit",
                        "line": line_name,
                        "from": from_stop,
                        "to": to_stop,
                        "stop_count": record["stop_count"],
                        "stops": record["stops"]
                    }],
                    "transit_time_minutes": record["stop_count"] * 2
                }
        except Exception as e:
            self._log(f"[NEO4J]     ⚠️ Forward route query failed: {e}")
        reverse_query = """
            MATCH path = (end:Stop {name: $to_stop})-[r:NEXT_STOP*1..50]->(start:Stop {name: $from_stop})
            WHERE all(rel in r WHERE rel.line = $line_name)
            WITH path, [s in nodes(path) | s.name] as stops
            RETURN stops, size(stops) as stop_count
            ORDER BY stop_count
            LIMIT 1
        """
        try:
            result = session.run(reverse_query, from_stop=from_stop, to_stop=to_stop, line_name=line_name)
            record = result.single()
            if record:
                stops = list(reversed(record["stops"]))
                self._log(f"[NEO4J]     ✅ Reverse route found: {line_name} ({record['stop_count']} stops)")
                return {
                    "segments": [{
                        "type": "transit",
                        "line": line_name,
                        "from": from_stop,
                        "to": to_stop,
                        "stop_count": record["stop_count"],
                        "stops": stops
                    }],
                    "transit_time_minutes": record["stop_count"] * 2
                }
        except Exception as e:
            self._log(f"[NEO4J]     ⚠️ Reverse route query failed: {e}")
        return None

    def _find_one_transfer_route(self, session, from_stop: str, to_stop: str) -> Optional[Dict]:
        self._log(f"[NEO4J]     Finding transfer points via SERVED_BY...")
        transfer_query = """
            MATCH (start:Stop {name: $from_stop})-[:SERVED_BY]->(line1:Line)
            MATCH (end:Stop {name: $to_stop})-[:SERVED_BY]->(line2:Line)
            WHERE line1 <> line2
            MATCH (transfer:Stop)-[:SERVED_BY]->(line1)
            MATCH (transfer)-[:SERVED_BY]->(line2)
            RETURN line1.name as from_line,
                   line2.name as to_line,
                   transfer.name as transfer_stop
            LIMIT 10
        """
        try:
            result = session.run(transfer_query, from_stop=from_stop, to_stop=to_stop)
            transfers = list(result)
            if not transfers:
                self._log(f"[NEO4J]     No transfer points found")
                return None
            self._log(f"[NEO4J]     Found {len(transfers)} transfer options")
        except Exception as e:
            self._log(f"[NEO4J]     ⚠️ Transfer query failed: {e}")
            return None
        best_route = None
        best_total = float('inf')
        for transfer_option in transfers:
            from_line = transfer_option["from_line"]
            to_line = transfer_option["to_line"]
            transfer_stop = transfer_option["transfer_stop"]
            self._log(f"[NEO4J]     Trying transfer at {transfer_stop}: {from_line} -> {to_line}")
            seg1 = self._get_segment_stops(session, from_stop, transfer_stop, from_line)
            if not seg1:
                continue
            seg2 = self._get_segment_stops(session, transfer_stop, to_stop, to_line)
            if not seg2:
                continue
            total_stops = len(seg1) + len(seg2) - 1
            if total_stops < best_total:
                best_total = total_stops
                all_stops = seg1 + seg2[1:]
                self._log(f"[NEO4J]     ✅ Transfer route found: {from_line} -> {to_line} at {transfer_stop} ({total_stops} stops)")
                best_route = {
                    "segments": [
                        {
                            "type": "transit",
                            "line": from_line,
                            "from": seg1[0],
                            "to": seg1[-1],
                            "stop_count": len(seg1),
                            "stops": seg1
                        },
                        {
                            "type": "transit",
                            "line": to_line,
                            "from": seg2[0],
                            "to": seg2[-1],
                            "stop_count": len(seg2),
                            "stops": seg2
                        }
                    ],
                    "transit_time_minutes": total_stops * 2 + 3
                }
        return best_route

    def _get_segment_stops(self, session, from_stop: str, to_stop: str, line_name: str) -> Optional[List[str]]:
        forward_query = """
            MATCH path = (start:Stop {name: $from_stop})-[r:NEXT_STOP*1..50]->(end:Stop {name: $to_stop})
            WHERE all(rel in r WHERE rel.line = $line_name)
            WITH [s in nodes(path) | s.name] as stops
            RETURN stops
            ORDER BY size(stops)
            LIMIT 1
        """
        try:
            result = session.run(forward_query, from_stop=from_stop, to_stop=to_stop, line_name=line_name)
            record = result.single()
            if record:
                return record["stops"]
        except Exception as e:
            self._log(f"[NEO4J] Forward segment query failed: {e}")
        reverse_query = """
            MATCH path = (end:Stop {name: $to_stop})-[r:NEXT_STOP*1..50]->(start:Stop {name: $from_stop})
            WHERE all(rel in r WHERE rel.line = $line_name)
            WITH [s in nodes(path) | s.name] as stops
            RETURN stops
            ORDER BY size(stops)
            LIMIT 1
        """
        try:
            result = session.run(reverse_query, from_stop=from_stop, to_stop=to_stop, line_name=line_name)
            record = result.single()
            if record:
                return list(reversed(record["stops"]))
        except Exception as e:
            self._log(f"[NEO4J] Reverse segment query failed: {e}")
        return None

    def _get_common_lines(self, session, stop1_name: str, stop2_name: str) -> List[str]:
        query = """
            MATCH (s1:Stop {name: $stop1}), (s2:Stop {name: $stop2})
            WITH s1.lines as lines1, s2.lines as lines2
            WHERE lines1 IS NOT NULL AND lines2 IS NOT NULL
            RETURN [line IN lines1 WHERE line IN lines2] as common_lines
        """
        try:
            result = session.run(query, stop1=stop1_name, stop2=stop2_name)
            record = result.single()
            if record and record["common_lines"]:
                return record["common_lines"]
        except Exception as e:
            self._log(f"[NEO4J]     ⚠️ Common lines query failed: {e}")
        return []

    def get_line_route(self, line_name: str, direction: str = "both") -> Dict:
        self._log(f"[NEO4J] get_line_route called: line={line_name}, direction={direction}")
        normalized = self._normalize_line_name(line_name)
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH path = (start:Stop)-[:NEXT_STOP*{line: $line}]->(end:Stop)
                WHERE NOT ()-[:NEXT_STOP {line: $line}]->(start)
                  AND NOT (end)-[:NEXT_STOP {line: $line}]->()
                WITH path, length(path) as path_length
                ORDER BY path_length DESC
                LIMIT 1
                RETURN [n IN nodes(path) | {name: n.name, lat: n.latitude, lon: n.longitude}] as stops,
                       length(path) as stop_count
            """
            try:
                result = session.run(query, line=normalized)
                record = result.single()
                if record:
                    return {
                        "success": True,
                        "line": normalized,
                        "stops": record["stops"],
                        "stop_count": record["stop_count"]
                    }
            except Exception as e:
                self._log(f"[NEO4J] ⚠️ Line route query failed: {e}")
            query_fallback = """
                MATCH (s1:Stop)-[r:NEXT_STOP {line: $line}]->(s2:Stop)
                WITH collect(DISTINCT s1.name) + collect(DISTINCT s2.name) as all_stops
                UNWIND all_stops as stop_name
                WITH collect(DISTINCT stop_name) as unique_stops
                RETURN unique_stops as stops, size(unique_stops) as stop_count
            """
            try:
                result = session.run(query_fallback, line=normalized)
                record = result.single()
                if record and record["stops"]:
                    return {
                        "success": True,
                        "line": normalized,
                        "stops": record["stops"],
                        "stop_count": record["stop_count"],
                        "note": "Stop order may not be sequential"
                    }
            except Exception as e:
                self._log(f"[NEO4J] ⚠️ Line route fallback query failed: {e}")
            return {"success": False, "error": f"Line '{line_name}' not found or has no stops"}

    def get_all_lines(self) -> Dict:
        self._log("[NEO4J] get_all_lines called")
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH ()-[r:NEXT_STOP]->()
                WITH DISTINCT r.line as line
                WHERE line IS NOT NULL
                RETURN collect(line) as lines
            """
            try:
                result = session.run(query)
                record = result.single()
                if record:
                    return {
                        "success": True,
                        "lines": sorted(record["lines"]),
                        "count": len(record["lines"])
                    }
            except Exception as e:
                self._log(f"[NEO4J] ⚠️ Get all lines query failed: {e}")
            return {"success": False, "error": "Failed to retrieve lines"}

    def list_all_sensors(self) -> Dict:
        self._log("[NEO4J] list_all_sensors called")
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (s:Sensor)
                RETURN s.id as id, s.name as name, s.type as type, s.fiware_id as fiware_id,
                       s.latitude as latitude, s.longitude as longitude
            """
            result = session.run(query)
            sensors = []
            type_counts = {}
            for record in result:
                sensor = {
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"],
                    "fiware_id": record["fiware_id"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"]
                }
                sensors.append(sensor)
                sensor_type = record["type"] or "Unknown"
                type_counts[sensor_type] = type_counts.get(sensor_type, 0) + 1
            return {
                "success": True,
                "total_count": len(sensors),
                "by_type": type_counts,
                "sensors": sensors
            }

    def list_sensors_by_type(self, sensor_type: str) -> Dict:
        self._log(f"[NEO4J] list_sensors_by_type called with: '{sensor_type}'")
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (s:Sensor)
                WHERE toLower(s.type) = $sensor_type
                RETURN s.id as id, s.name as name, s.type as type, s.fiware_id as fiware_id,
                       s.latitude as latitude, s.longitude as longitude
            """
            result = session.run(query, sensor_type=sensor_type.lower())
            sensors = []
            for record in result:
                sensors.append({
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"],
                    "fiware_id": record["fiware_id"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"]
                })
            return {
                "success": True,
                "sensor_type": sensor_type,
                "count": len(sensors),
                "sensors": sensors
            }

    def get_sensor_for_location(self, location_name: str, sensor_type: str = None) -> Optional[Dict]:
        self._log(f"[NEO4J] get_sensor_for_location: '{location_name}', type={sensor_type}")
        with self.driver.session(database=self.database) as session:
            type_filter = "AND toLower(s.type) = $sensor_type" if sensor_type else ""
            query = f"""
                MATCH (s:Sensor)
                WHERE toLower(s.name) CONTAINS $search OR toLower(s.id) CONTAINS $search
                {type_filter}
                RETURN s.id as id, s.name as name, s.type as type, s.fiware_id as fiware_id,
                       s.latitude as latitude, s.longitude as longitude
                LIMIT 1
            """
            params = {"search": location_name.lower()}
            if sensor_type:
                params["sensor_type"] = sensor_type.lower()
            result = session.run(query, **params)
            record = result.single()
            if record:
                return {
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"],
                    "fiware_id": record["fiware_id"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"]
                }
            return None

    def get_sensor_near_building(self, building_id: str, sensor_type: str = None) -> Dict:
        self._log(f"[NEO4J] get_sensor_near_building: '{building_id}', type={sensor_type}")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_id, session)
            if not found:
                return {"success": False, "error": f"Building '{building_id}' not found"}
            type_filter = "WHERE toLower(s.type) = $sensor_type" if sensor_type else ""
            query = f"""
                MATCH (b:Building {{name: $building_name}})
                MATCH (s:Sensor)
                {type_filter}
                WITH b, s, point.distance(
                    point({{latitude: b.latitude, longitude: b.longitude}}),
                    point({{latitude: s.latitude, longitude: s.longitude}})
                ) as distance
                ORDER BY distance
                LIMIT 1
                RETURN s.id as id, s.name as name, s.type as type, s.fiware_id as fiware_id,
                       s.latitude as latitude, s.longitude as longitude, round(distance) as distance_meters
            """
            params = {"building_name": found["name"]}
            if sensor_type:
                params["sensor_type"] = sensor_type.lower()
            result = session.run(query, **params)
            record = result.single()
            if record:
                return {
                    "success": True,
                    "building": found["name"],
                    "sensor": {
                        "id": record["id"],
                        "name": record["name"],
                        "type": record["type"],
                        "fiware_id": record["fiware_id"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                        "distance_meters": record["distance_meters"]
                    }
                }
            return {"success": False, "error": f"No sensor found near '{building_id}'"}

    def get_all_sensors_near_building(self, building_id: str, sensor_type: str = None, limit: int = 10) -> Dict:
        self._log(f"[NEO4J] get_all_sensors_near_building: '{building_id}', type={sensor_type}")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_id, session)
            if not found:
                return {"success": False, "error": f"Building '{building_id}' not found"}
            type_filter = "WHERE toLower(s.type) = $sensor_type" if sensor_type else ""
            query = f"""
                MATCH (b:Building {{name: $building_name}})
                MATCH (s:Sensor)
                {type_filter}
                WITH b, s, point.distance(
                    point({{latitude: b.latitude, longitude: b.longitude}}),
                    point({{latitude: s.latitude, longitude: s.longitude}})
                ) as distance
                ORDER BY distance
                LIMIT $limit
                RETURN s.id as id, s.name as name, s.type as type, s.fiware_id as fiware_id,
                       s.latitude as latitude, s.longitude as longitude, round(distance) as distance_meters
            """
            params = {"building_name": found["name"], "limit": limit}
            if sensor_type:
                params["sensor_type"] = sensor_type.lower()
            result = session.run(query, **params)
            sensors = []
            for record in result:
                sensors.append({
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"],
                    "fiware_id": record["fiware_id"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "distance_meters": record["distance_meters"]
                })
            return {
                "success": True,
                "building": found["name"],
                "count": len(sensors),
                "sensors": sensors
            }

    def get_nearest_sensor(self, latitude: float, longitude: float,
                           sensor_type: str = None, radius: int = 1000) -> Dict:
        self._log(f"[NEO4J] get_nearest_sensor: {latitude}, {longitude}, type={sensor_type}")
        with self.driver.session(database=self.database) as session:
            type_filter = "WHERE toLower(s.type) = $sensor_type" if sensor_type else ""
            query = f"""
                MATCH (s:Sensor)
                {type_filter}
                WITH s, point.distance(
                    point({{latitude: $lat, longitude: $lon}}),
                    point({{latitude: s.latitude, longitude: s.longitude}})
                ) as distance
                WHERE distance <= $radius
                ORDER BY distance
                LIMIT 1
                RETURN s.id as id, s.name as name, s.type as type, s.fiware_id as fiware_id,
                       s.latitude as latitude, s.longitude as longitude, round(distance) as distance_meters
            """
            params = {"lat": latitude, "lon": longitude, "radius": radius}
            if sensor_type:
                params["sensor_type"] = sensor_type.lower()
            result = session.run(query, **params)
            record = result.single()
            if record:
                return {
                    "success": True,
                    "sensor": {
                        "id": record["id"],
                        "name": record["name"],
                        "type": record["type"],
                        "fiware_id": record["fiware_id"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                        "distance_meters": record["distance_meters"]
                    }
                }
            return {"success": False, "error": "No sensor found within radius"}

    # ==================== PROXIMITY & NEARBY FUNCTIONS ====================

    def get_distance_between_locations(self, location1: str, location2: str) -> Dict:
        """Alias for check_proximity - Get distance between two locations."""
        return self.check_proximity(location1, location2)

    def is_near(self, location1: str, location2: str) -> Dict:
        """Alias for check_proximity - Check if two locations are near each other."""
        return self.check_proximity(location1, location2)

    def check_proximity(self, location1: str, location2: str) -> Dict:
        """Check if two locations are near each other using NEARBY relationship or distance calculation."""
        self._log(f"[NEO4J] check_proximity: '{location1}' <-> '{location2}'")
        with self.driver.session(database=self.database) as session:
            # First, find both locations
            loc1 = self._find_stop_or_building(location1, session)
            loc2 = self._find_stop_or_building(location2, session)

            if not loc1:
                return {"success": False, "error": f"Location '{location1}' not found"}
            if not loc2:
                return {"success": False, "error": f"Location '{location2}' not found"}

            loc1_name = loc1["name"]
            loc2_name = loc2["name"]
            loc1_type = loc1["type"]
            loc2_type = loc2["type"]

            # Check if there's a direct NEARBY relationship
            nearby_result = None
            if loc1_type == "Building" and loc2_type == "POI":
                query = """
                    MATCH (b:Building {name: $loc1})-[r:NEARBY]->(p:POI {name: $loc2})
                    RETURN r.distance_m as distance, r.walk_time_min as walk_time, r.tier as tier, r.category as category
                """
                result = session.run(query, loc1=loc1_name, loc2=loc2_name)
                nearby_result = result.single()
            elif loc1_type == "POI" and loc2_type == "Building":
                query = """
                    MATCH (b:Building {name: $loc2})-[r:NEARBY]->(p:POI {name: $loc1})
                    RETURN r.distance_m as distance, r.walk_time_min as walk_time, r.tier as tier, r.category as category
                """
                result = session.run(query, loc1=loc1_name, loc2=loc2_name)
                nearby_result = result.single()
            elif loc1_type == "Stop" and loc2_type == "POI":
                query = """
                    MATCH (s:Stop {name: $loc1})-[r:NEARBY]->(p:POI {name: $loc2})
                    RETURN r.distance_m as distance, r.walk_time_min as walk_time, r.tier as tier, r.category as category
                """
                result = session.run(query, loc1=loc1_name, loc2=loc2_name)
                nearby_result = result.single()
            elif loc1_type == "Building" and loc2_type == "Building":
                # Check ACCESSIBLE_ROUTE or ADJACENT_TO
                query = """
                    MATCH (b1:Building {name: $loc1})-[r:ACCESSIBLE_ROUTE|ADJACENT_TO]-(b2:Building {name: $loc2})
                    RETURN type(r) as rel_type, r.distance_m as distance, r.walk_time_min as walk_time, r.tier as tier
                    LIMIT 1
                """
                result = session.run(query, loc1=loc1_name, loc2=loc2_name)
                nearby_result = result.single()

            if nearby_result:
                distance = nearby_result.get("distance") or 0
                walk_time = nearby_result.get("walk_time") or round(distance * 1.4 / 80)
                tier = nearby_result.get("tier") or ("close" if distance < 200 else "near" if distance < 500 else "reachable")
                return {
                    "success": True,
                    "is_nearby": True,
                    "location1": {"name": loc1_name, "type": loc1_type},
                    "location2": {"name": loc2_name, "type": loc2_type},
                    "distance_meters": distance,
                    "walk_time_minutes": walk_time,
                    "tier": tier,
                    "relationship_found": True
                }

            # Calculate straight-line distance if no relationship found
            if loc1.get("latitude") is not None and loc2.get("latitude") is not None:
                distance = self._calculate_distance(
                    loc1["latitude"], loc1["longitude"],
                    loc2["latitude"], loc2["longitude"]
                )
                walk_dist = round(distance * 1.4)
                walk_time = max(1, round(walk_dist / 80))
                is_nearby = distance < 500

                return {
                    "success": True,
                    "is_nearby": is_nearby,
                    "location1": {"name": loc1_name, "type": loc1_type},
                    "location2": {"name": loc2_name, "type": loc2_type},
                    "distance_meters": distance,
                    "walking_distance_meters": walk_dist,
                    "walk_time_minutes": walk_time,
                    "tier": "close" if distance < 200 else "near" if distance < 500 else "far",
                    "relationship_found": False,
                    "note": "Distance calculated, no direct NEARBY relationship"
                }

            return {"success": False, "error": "Could not determine proximity"}

    def find_nearby_pois_graph(self, building_name: str, category: str = None, tier: str = None, limit: int = 10) -> Dict:
        """Find POIs near a building using the pre-computed NEARBY relationship."""
        self._log(f"[NEO4J] find_nearby_pois_graph: {building_name}, category={category}, tier={tier}")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_name, session)
            if not found:
                return {"success": False, "error": f"Building '{building_name}' not found"}

            conditions = []
            params = {"building_name": found["name"], "limit": limit}
            if category:
                conditions.append("r.category = $category")
                params["category"] = category.lower()
            if tier:
                conditions.append("r.tier = $tier")
                params["tier"] = tier.lower()
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            query = f"""
                MATCH (b:Building {{name: $building_name}})-[r:NEARBY]->(p:POI)
                {where_clause}
                RETURN p.name as name, p.type as type, p.cuisine as cuisine, p.address as address,
                       p.latitude as latitude, p.longitude as longitude,
                       r.distance_m as distance_meters, r.walk_time_min as walk_time_minutes,
                       r.tier as tier, r.rank as rank, r.category as category
                ORDER BY r.rank, r.distance_m
                LIMIT $limit
            """
            result = session.run(query, **params)
            pois = []
            for record in result:
                pois.append({
                    "name": record["name"],
                    "type": record["type"],
                    "cuisine": record["cuisine"],
                    "address": record["address"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "distance_meters": record["distance_meters"],
                    "walk_time_minutes": record["walk_time_minutes"],
                    "walk_time_text": f"{record['walk_time_minutes']} min walk" if record["walk_time_minutes"] else None,
                    "tier": record["tier"],
                    "rank": record["rank"],
                    "category": record["category"]
                })
            return {
                "success": True,
                "building": found["name"],
                "count": len(pois),
                "pois": pois
            }

    def find_nearby_pois_from_stop(self, stop_name: str, category: str = None, tier: str = None, limit: int = 10) -> Dict:
        """Find POIs near a stop using the pre-computed NEARBY relationship."""
        self._log(f"[NEO4J] find_nearby_pois_from_stop: {stop_name}, category={category}, tier={tier}")
        with self.driver.session(database=self.database) as session:
            normalized = self._normalize_stop_name(stop_name)
            conditions = []
            params = {"stop_name": normalized, "search": stop_name.lower(), "limit": limit}
            if category:
                conditions.append("r.category = $category")
                params["category"] = category.lower()
            if tier:
                conditions.append("r.tier = $tier")
                params["tier"] = tier.lower()
            where_clause = "AND " + " AND ".join(conditions) if conditions else ""

            query = f"""
                MATCH (s:Stop)-[r:NEARBY]->(p:POI)
                WHERE (s.name = $stop_name OR toLower(s.name) CONTAINS $search) {where_clause}
                RETURN s.name as stop_name, p.name as name, p.type as type, p.cuisine as cuisine,
                       p.address as address, p.latitude as latitude, p.longitude as longitude,
                       r.distance_m as distance_meters, r.walk_time_min as walk_time_minutes,
                       r.tier as tier, r.rank as rank, r.category as category
                ORDER BY r.rank, r.distance_m
                LIMIT $limit
            """
            result = session.run(query, **params)
            pois = []
            stop_found = None
            for record in result:
                stop_found = record["stop_name"]
                pois.append({
                    "name": record["name"],
                    "type": record["type"],
                    "cuisine": record["cuisine"],
                    "address": record["address"],
                    "distance_meters": record["distance_meters"],
                    "walk_time_minutes": record["walk_time_minutes"],
                    "walk_time_text": f"{record['walk_time_minutes']} min walk" if record["walk_time_minutes"] else None,
                    "tier": record["tier"],
                    "rank": record["rank"],
                    "category": record["category"]
                })
            if not pois:
                return {"success": False, "error": f"No POIs found near stop '{stop_name}'"}
            return {
                "success": True,
                "stop": stop_found,
                "count": len(pois),
                "pois": pois
            }

    # ==================== ACCESSIBLE ROUTE FUNCTIONS ====================

    def get_accessible_route(self, from_building: str, to_building: str) -> Dict:
        """Get wheelchair accessible route between two buildings using ACCESSIBLE_ROUTE relationship."""
        self._log(f"[NEO4J] get_accessible_route: {from_building} -> {to_building}")
        with self.driver.session(database=self.database) as session:
            from_found = self._find_building_universal(from_building, session)
            to_found = self._find_building_universal(to_building, session)

            if not from_found:
                return {"success": False, "error": f"Building '{from_building}' not found"}
            if not to_found:
                return {"success": False, "error": f"Building '{to_building}' not found"}

            # Check direct accessible route
            query = """
                MATCH (b1:Building {name: $from_name})-[r:ACCESSIBLE_ROUTE]->(b2:Building {name: $to_name})
                RETURN r.distance_m as distance, r.walk_time_min as walk_time, r.tier as tier
            """
            result = session.run(query, from_name=from_found["name"], to_name=to_found["name"])
            record = result.single()

            if record:
                return {
                    "success": True,
                    "accessible": True,
                    "from_building": from_found["name"],
                    "to_building": to_found["name"],
                    "distance_meters": record["distance"],
                    "walk_time_minutes": record["walk_time"],
                    "tier": record["tier"],
                    "route_type": "direct"
                }

            # Try reverse direction
            query_reverse = """
                MATCH (b1:Building {name: $to_name})-[r:ACCESSIBLE_ROUTE]->(b2:Building {name: $from_name})
                RETURN r.distance_m as distance, r.walk_time_min as walk_time, r.tier as tier
            """
            result = session.run(query_reverse, from_name=from_found["name"], to_name=to_found["name"])
            record = result.single()

            if record:
                return {
                    "success": True,
                    "accessible": True,
                    "from_building": from_found["name"],
                    "to_building": to_found["name"],
                    "distance_meters": record["distance"],
                    "walk_time_minutes": record["walk_time"],
                    "tier": record["tier"],
                    "route_type": "direct_reverse"
                }

            # Try to find a path through intermediate buildings
            query_path = """
                MATCH path = (b1:Building {name: $from_name})-[:ACCESSIBLE_ROUTE*1..3]-(b2:Building {name: $to_name})
                WITH path, [r in relationships(path) | r.distance_m] as distances,
                     [r in relationships(path) | r.walk_time_min] as times,
                     [n in nodes(path) | n.name] as building_names
                RETURN building_names,
                       reduce(total = 0, d in distances | total + d) as total_distance,
                       reduce(total = 0, t in times | total + t) as total_time
                ORDER BY total_distance
                LIMIT 1
            """
            result = session.run(query_path, from_name=from_found["name"], to_name=to_found["name"])
            record = result.single()

            if record:
                return {
                    "success": True,
                    "accessible": True,
                    "from_building": from_found["name"],
                    "to_building": to_found["name"],
                    "distance_meters": record["total_distance"],
                    "walk_time_minutes": record["total_time"],
                    "route_type": "via_buildings",
                    "path": record["building_names"]
                }

            return {
                "success": True,
                "accessible": False,
                "from_building": from_found["name"],
                "to_building": to_found["name"],
                "message": "No wheelchair accessible route found between these buildings"
            }

    def get_all_accessible_buildings(self, from_building: str, max_tier: str = "near") -> Dict:
        """Get all buildings accessible from a building via wheelchair-accessible routes."""
        self._log(f"[NEO4J] get_all_accessible_buildings: {from_building}, max_tier={max_tier}")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(from_building, session)
            if not found:
                return {"success": False, "error": f"Building '{from_building}' not found"}

            tier_filter = ""
            if max_tier == "close":
                tier_filter = "AND r.tier = 'close'"
            elif max_tier == "near":
                tier_filter = "AND r.tier IN ['close', 'near']"

            query = f"""
                MATCH (b:Building {{name: $building_name}})-[r:ACCESSIBLE_ROUTE]->(other:Building)
                WHERE true {tier_filter}
                RETURN other.name as name, other.function as function,
                       r.distance_m as distance, r.walk_time_min as walk_time, r.tier as tier
                ORDER BY r.distance_m
            """
            result = session.run(query, building_name=found["name"])
            buildings = []
            for record in result:
                buildings.append({
                    "name": record["name"],
                    "function": record["function"],
                    "distance_meters": record["distance"],
                    "walk_time_minutes": record["walk_time"],
                    "tier": record["tier"]
                })
            return {
                "success": True,
                "from_building": found["name"],
                "count": len(buildings),
                "accessible_buildings": buildings
            }

    # ==================== WALKING DISTANCE FUNCTIONS ====================

    def get_walking_connections(self, stop_name: str, max_walk_time: int = 10) -> Dict:
        """Get stops within walking distance using WALKING_DISTANCE relationship."""
        self._log(f"[NEO4J] get_walking_connections: {stop_name}, max_walk={max_walk_time}min")
        with self.driver.session(database=self.database) as session:
            normalized = self._normalize_stop_name(stop_name)
            query = """
                MATCH (s:Stop)-[r:WALKING_DISTANCE]-(other:Stop)
                WHERE (s.name = $stop_name OR toLower(s.name) CONTAINS $search)
                  AND r.walk_time_minutes <= $max_walk
                RETURN s.name as from_stop, other.name as to_stop, other.lines as lines,
                       r.distance_meters as distance, r.walk_time_minutes as walk_time, r.category as category
                ORDER BY r.walk_time_minutes
            """
            result = session.run(query, stop_name=normalized, search=stop_name.lower(), max_walk=max_walk_time)
            connections = []
            from_stop = None
            for record in result:
                from_stop = record["from_stop"]
                connections.append({
                    "stop": record["to_stop"],
                    "lines": record["lines"],
                    "distance_meters": record["distance"],
                    "walk_time_minutes": record["walk_time"],
                    "category": record["category"]
                })
            if not connections:
                return {"success": False, "error": f"No walking connections found for '{stop_name}'"}
            return {
                "success": True,
                "from_stop": from_stop,
                "count": len(connections),
                "walking_connections": connections
            }

    # ==================== SPATIAL RELATIONSHIP FUNCTIONS ====================

    def get_building_borders(self, building_name: str) -> Dict:
        """Get what borders a building (streets, other buildings, areas) using BORDERED_BY."""
        self._log(f"[NEO4J] get_building_borders: {building_name}")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_name, session)
            if not found:
                return {"success": False, "error": f"Building '{building_name}' not found"}

            query = """
                MATCH (b:Building {name: $building_name})-[r:BORDERED_BY]->(other)
                RETURN labels(other)[0] as type, other.name as name, r.side as side, r.note as note
                ORDER BY labels(other)[0], r.side
            """
            result = session.run(query, building_name=found["name"])
            borders = {"streets": [], "buildings": [], "areas": [], "pois": []}
            for record in result:
                border_info = {
                    "name": record["name"],
                    "side": record["side"],
                    "note": record["note"]
                }
                node_type = record["type"].lower()
                if node_type == "street":
                    borders["streets"].append(border_info)
                elif node_type == "building":
                    borders["buildings"].append(border_info)
                elif node_type == "area":
                    borders["areas"].append(border_info)
                elif node_type == "poi":
                    borders["pois"].append(border_info)

            return {
                "success": True,
                "building": found["name"],
                "borders": borders
            }

    def get_buildings_in_direction(self, building_name: str, direction: str) -> Dict:
        """Get buildings in a specific direction (north/south/east/west) from a building using BORDERED_BY."""
        self._log(f"[NEO4J] get_buildings_in_direction: {building_name} -> {direction}")
        direction = direction.lower().strip()
        valid_directions = ["north", "south", "east", "west"]
        if direction not in valid_directions:
            return {"success": False, "error": f"Invalid direction '{direction}'. Use: {valid_directions}"}

        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_name, session)
            if not found:
                return {"success": False, "error": f"Building '{building_name}' not found"}

            # Query for buildings bordered on the specified side
            query = """
                MATCH (b:Building {name: $building_name})-[r:BORDERED_BY {side: $direction}]->(other:Building)
                RETURN other.name as name, other.function as function, r.note as note
                UNION
                MATCH (other:Building)-[r:BORDERED_BY]->(b:Building {name: $building_name})
                WHERE r.side = CASE $direction
                    WHEN 'north' THEN 'south'
                    WHEN 'south' THEN 'north'
                    WHEN 'east' THEN 'west'
                    WHEN 'west' THEN 'east'
                END
                RETURN other.name as name, other.function as function, r.note as note
            """
            result = session.run(query, building_name=found["name"], direction=direction)
            buildings = []
            for record in result:
                buildings.append({
                    "name": record["name"],
                    "function": record["function"],
                    "note": record["note"]
                })

            if not buildings:
                return {
                    "success": True,
                    "building": found["name"],
                    "direction": direction,
                    "buildings": [],
                    "message": f"No buildings found to the {direction} of {found['name']}"
                }

            return {
                "success": True,
                "building": found["name"],
                "direction": direction,
                "buildings": buildings
            }

    def what_is_north_of(self, building_name: str) -> Dict:
        """Get buildings north of a building."""
        return self.get_buildings_in_direction(building_name, "north")

    def what_is_south_of(self, building_name: str) -> Dict:
        """Get buildings south of a building."""
        return self.get_buildings_in_direction(building_name, "south")

    def what_is_east_of(self, building_name: str) -> Dict:
        """Get buildings east of a building."""
        return self.get_buildings_in_direction(building_name, "east")

    def what_is_west_of(self, building_name: str) -> Dict:
        """Get buildings west of a building."""
        return self.get_buildings_in_direction(building_name, "west")

    def get_street_intersections(self, street_name: str) -> Dict:
        """Get streets that intersect with a given street using INTERSECTS relationship."""
        self._log(f"[NEO4J] get_street_intersections: {street_name}")
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (s:Street)-[r:INTERSECTS]-(other:Street)
                WHERE toLower(s.name) CONTAINS $search
                RETURN s.name as street, other.name as intersects_with
                ORDER BY other.name
            """
            result = session.run(query, search=street_name.lower())
            intersections = []
            street_found = None
            for record in result:
                street_found = record["street"]
                intersections.append(record["intersects_with"])

            if not street_found:
                return {"success": False, "error": f"Street '{street_name}' not found"}
            return {
                "success": True,
                "street": street_found,
                "intersections": intersections,
                "count": len(intersections)
            }

    def get_building_spatial_relations(self, building_name: str) -> Dict:
        """Get all spatial relationships for a building (FACES, CONTIGUOUS_TO, SURROUNDED_BY, etc.)."""
        self._log(f"[NEO4J] get_building_spatial_relations: {building_name}")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_name, session)
            if not found:
                return {"success": False, "error": f"Building '{building_name}' not found"}

            query = """
                MATCH (b:Building {name: $building_name})
                OPTIONAL MATCH (b)-[faces:FACES]->(area:Area)
                OPTIONAL MATCH (b)-[contig:CONTIGUOUS_TO]-(contig_bldg:Building)
                OPTIONAL MATCH (b)-[surr_by:SURROUNDED_BY]->(surr_bldg:Building)
                OPTIONAL MATCH (b)-[surr:SURROUNDS]->(inner_bldg:Building)
                OPTIONAL MATCH (b)-[looks:LOOKS_ALIKE]-(similar_bldg:Building)
                OPTIONAL MATCH (b)-[same:SAME_STRUCTURE]-(same_bldg:Building)
                OPTIONAL MATCH (b)-[conn:CONNECTED_INTERNALLY]-(conn_bldg:Building)
                RETURN
                    collect(DISTINCT {area: area.name, side: faces.side}) as faces_areas,
                    collect(DISTINCT {building: contig_bldg.name, has_passage: contig.has_passage}) as contiguous,
                    collect(DISTINCT surr_bldg.name) as surrounded_by,
                    collect(DISTINCT inner_bldg.name) as surrounds,
                    collect(DISTINCT {building: similar_bldg.name, description: looks.description}) as looks_alike,
                    collect(DISTINCT same_bldg.name) as same_structure,
                    collect(DISTINCT {building: conn_bldg.name, type: conn.type}) as connected_internally
            """
            result = session.run(query, building_name=found["name"])
            record = result.single()

            return {
                "success": True,
                "building": found["name"],
                "spatial_relations": {
                    "faces_areas": [f for f in record["faces_areas"] if f.get("area")],
                    "contiguous_to": [c for c in record["contiguous"] if c.get("building")],
                    "surrounded_by": [s for s in record["surrounded_by"] if s],
                    "surrounds": [s for s in record["surrounds"] if s],
                    "looks_alike": [l for l in record["looks_alike"] if l.get("building")],
                    "same_structure": [s for s in record["same_structure"] if s],
                    "connected_internally": [c for c in record["connected_internally"] if c.get("building")]
                }
            }

    # ==================== LANDMARK FUNCTIONS ====================

    def get_building_landmarks(self, building_name: str) -> Dict:
        """Get landmarks associated with a building using HAS_LANDMARK, BEHIND_LANDMARK, VIEWS."""
        self._log(f"[NEO4J] get_building_landmarks: {building_name}")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_name, session)
            if not found:
                return {"success": False, "error": f"Building '{building_name}' not found"}

            query = """
                MATCH (b:Building {name: $building_name})
                OPTIONAL MATCH (b)-[has:HAS_LANDMARK]->(has_lm:Landmark)
                OPTIONAL MATCH (b)-[behind:BEHIND_LANDMARK]->(behind_lm:Landmark)
                OPTIONAL MATCH (b)-[views:VIEWS]->(views_lm:Landmark)
                RETURN
                    collect(DISTINCT {name: has_lm.name, side: has.side, position: has.position}) as has_landmarks,
                    collect(DISTINCT {name: behind_lm.name, description: behind.description}) as behind_landmarks,
                    collect(DISTINCT {name: views_lm.name, side: views.side}) as views_landmarks
            """
            result = session.run(query, building_name=found["name"])
            record = result.single()

            return {
                "success": True,
                "building": found["name"],
                "landmarks": {
                    "has": [l for l in record["has_landmarks"] if l.get("name")],
                    "behind": [l for l in record["behind_landmarks"] if l.get("name")],
                    "views": [l for l in record["views_landmarks"] if l.get("name")]
                }
            }

    # ==================== INFRASTRUCTURE FUNCTIONS ====================

    def get_building_infrastructure(self, building_name: str) -> Dict:
        """Get infrastructure connections for a building (cooling, etc.)."""
        self._log(f"[NEO4J] get_building_infrastructure: {building_name}")
        with self.driver.session(database=self.database) as session:
            found = self._find_building_universal(building_name, session)
            if not found:
                return {"success": False, "error": f"Building '{building_name}' not found"}

            query = """
                MATCH (b:Building {name: $building_name})
                OPTIONAL MATCH (b)-[provides:PROVIDES_COOLING_TO]->(cooled:Building)
                OPTIONAL MATCH (b)-[receives:RECEIVES_COOLING_FROM]->(provider:Building)
                RETURN
                    collect(DISTINCT {building: cooled.name, source: provides.source}) as provides_cooling_to,
                    collect(DISTINCT {building: provider.name, source: receives.source}) as receives_cooling_from
            """
            result = session.run(query, building_name=found["name"])
            record = result.single()

            return {
                "success": True,
                "building": found["name"],
                "infrastructure": {
                    "provides_cooling_to": [p for p in record["provides_cooling_to"] if p.get("building")],
                    "receives_cooling_from": [r for r in record["receives_cooling_from"] if r.get("building")]
                }
            }

    # ==================== AREA FUNCTIONS ====================

    def get_area_info(self, area_name: str) -> Dict:
        """Get information about an area including what it contains."""
        self._log(f"[NEO4J] get_area_info: {area_name}")
        with self.driver.session(database=self.database) as session:
            query = """
                MATCH (a:Area)
                WHERE toLower(a.name) CONTAINS $search
                OPTIONAL MATCH (a)-[:CONTAINS]->(landmark:Landmark)
                OPTIONAL MATCH (a)-[:BORDERED_BY]->(building:Building)
                OPTIONAL MATCH (facing:Building)-[:FACES]->(a)
                RETURN a.name as name, a.description as description,
                       a.latitude as latitude, a.longitude as longitude,
                       collect(DISTINCT landmark.name) as landmarks,
                       collect(DISTINCT building.name) as bordered_by_buildings,
                       collect(DISTINCT facing.name) as buildings_facing
            """
            result = session.run(query, search=area_name.lower())
            record = result.single()

            if not record or not record["name"]:
                return {"success": False, "error": f"Area '{area_name}' not found"}

            return {
                "success": True,
                "area": {
                    "name": record["name"],
                    "description": record["description"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "contains_landmarks": [l for l in record["landmarks"] if l],
                    "bordered_by_buildings": [b for b in record["bordered_by_buildings"] if b],
                    "buildings_facing": [b for b in record["buildings_facing"] if b]
                }
            }

    # ==================== SENSOR RELATIONSHIP FUNCTIONS ====================

    def get_sensor_nearby_pois(self, sensor_name: str = None, sensor_type: str = None) -> Dict:
        """Get POIs near sensors using NEARBY_POI relationship."""
        self._log(f"[NEO4J] get_sensor_nearby_pois: sensor={sensor_name}, type={sensor_type}")
        with self.driver.session(database=self.database) as session:
            conditions = []
            if sensor_name:
                conditions.append("toLower(s.name) CONTAINS $sensor_name")
            if sensor_type:
                conditions.append("toLower(s.type) = $sensor_type")
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            query = f"""
                MATCH (s:Sensor)-[r:NEARBY_POI]->(p:POI)
                {where_clause}
                RETURN s.name as sensor_name, s.type as sensor_type,
                       p.name as poi_name, p.type as poi_type, r.distance_m as distance
                ORDER BY s.name, r.distance_m
            """
            params = {}
            if sensor_name:
                params["sensor_name"] = sensor_name.lower()
            if sensor_type:
                params["sensor_type"] = sensor_type.lower()

            result = session.run(query, **params)
            sensor_pois = {}
            for record in result:
                sname = record["sensor_name"]
                if sname not in sensor_pois:
                    sensor_pois[sname] = {"type": record["sensor_type"], "pois": []}
                sensor_pois[sname]["pois"].append({
                    "name": record["poi_name"],
                    "type": record["poi_type"],
                    "distance_meters": record["distance"]
                })

            return {
                "success": True,
                "count": len(sensor_pois),
                "sensors": sensor_pois
            }

    def get_sensor_nearby_stops(self, sensor_name: str = None, sensor_type: str = None) -> Dict:
        """Get stops near sensors using NEARBY_STOP relationship."""
        self._log(f"[NEO4J] get_sensor_nearby_stops: sensor={sensor_name}, type={sensor_type}")
        with self.driver.session(database=self.database) as session:
            conditions = []
            if sensor_name:
                conditions.append("toLower(s.name) CONTAINS $sensor_name")
            if sensor_type:
                conditions.append("toLower(s.type) = $sensor_type")
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            query = f"""
                MATCH (s:Sensor)-[r:NEARBY_STOP]->(st:Stop)
                {where_clause}
                RETURN s.name as sensor_name, s.type as sensor_type,
                       st.name as stop_name, st.lines as lines, r.distance_m as distance
                ORDER BY s.name, r.distance_m
            """
            params = {}
            if sensor_name:
                params["sensor_name"] = sensor_name.lower()
            if sensor_type:
                params["sensor_type"] = sensor_type.lower()

            result = session.run(query, **params)
            sensor_stops = {}
            for record in result:
                sname = record["sensor_name"]
                if sname not in sensor_stops:
                    sensor_stops[sname] = {"type": record["sensor_type"], "stops": []}
                sensor_stops[sname]["stops"].append({
                    "name": record["stop_name"],
                    "lines": record["lines"],
                    "distance_meters": record["distance"]
                })

            return {
                "success": True,
                "count": len(sensor_stops),
                "sensors": sensor_stops
            }
