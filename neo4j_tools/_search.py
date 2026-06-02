"""Search and location lookup mixin for Neo4j transit graph."""

from typing import Dict, List, Optional
from models import Coordinates


# Allow-list of valid POI.type values accepted for filtering. Cypher does not
# support binding labels/property literals in certain positions (and the
# values here flow into string-built query fragments via f-strings), so any
# user-supplied place_type must be validated against this set before use.
_VALID_PLACE_TYPES = frozenset({
    "all",
    "restaurant", "cafe", "bar", "pub", "fast_food", "food_court",
    "mensa", "canteen", "bakery", "ice_cream",
    "shop", "supermarket", "kiosk", "convenience",
    "pharmacy", "atm", "bank", "post_office",
    "library", "museum", "theatre", "cinema",
    "parking", "bicycle_parking", "fuel",
    "hotel", "hostel",
})


class SearchMixin:

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

            # Enrich with full building details in ONE query (was N+1).
            if buildings:
                names = [b["name"] for b in buildings]
                enrich = session.run("""
                    UNWIND $names AS name
                    MATCH (b:Building {name: name})
                    OPTIONAL MATCH (b)-[:ADJACENT_TO]-(nearby:Building)
                    OPTIONAL MATCH (b)-[onstreet:ON_STREET]->(street:Street)
                    OPTIONAL MATCH (b)-[:ACCESSIBLE_STOP]->(stop:Stop)
                    OPTIONAL MATCH (sensor:Sensor)-[:NEAR_BUILDING]->(b)
                    RETURN b.name AS name, b.note AS note, b.departments AS departments,
                           b.aliases AS aliases, b.address AS address,
                           collect(DISTINCT {name: nearby.name}) AS nearby_buildings,
                           collect(DISTINCT {name: street.name, distance_m: onstreet.distance_m}) AS streets,
                           collect(DISTINCT {name: stop.name, lines: stop.lines}) AS nearest_stops,
                           collect(DISTINCT {name: sensor.name, type: sensor.type}) AS sensors
                """, names=names)
                by_name = {}
                for rec in enrich:
                    by_name[rec["name"]] = rec
                for bldg in buildings:
                    rec = by_name.get(bldg["name"])
                    if not rec:
                        continue
                    bldg["note"] = rec["note"]
                    bldg["departments"] = rec["departments"]
                    bldg["aliases"] = rec["aliases"]
                    bldg["address"] = rec["address"]
                    nearby = [n for n in rec["nearby_buildings"] if n.get("name")]
                    if nearby:
                        bldg["nearby_buildings"] = nearby
                    sensors = [s for s in rec["sensors"] if s.get("name")]
                    if sensors:
                        bldg["sensors"] = sensors
                    stops = [s for s in rec["nearest_stops"] if s.get("name")]
                    if stops:
                        bldg["nearest_stops"] = stops

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

    def _enrich_locations_bulk(self, session, locations: List[Dict]) -> List[Dict]:
        """Enrich a mixed list of locations (Building/Stop/POI/Landmark) with
        relationship data — streets, nearby buildings, sensors, stops, etc. —
        in ONE round-trip per node type (was N+1 per location previously).

        Fills fields like: street, streets, note, departments, aliases,
        fiware_type, nearby_buildings, sensors, nearest_stops, dietary_options,
        opening_hours, phone, website.
        """
        if not locations:
            return locations

        by_type: Dict[str, Dict[str, Dict]] = {"Building": {}, "Stop": {}, "POI": {}}
        for loc in locations:
            t = loc.get("type")
            n = loc.get("name")
            if t in by_type and n:
                by_type[t][n] = loc

        # --- Buildings: details + streets + nearby + sensors + stops ---
        if by_type["Building"]:
            names = list(by_type["Building"].keys())
            try:
                rows = session.run("""
                    UNWIND $names AS name
                    MATCH (b:Building {name: name})
                    OPTIONAL MATCH (b)-[onstreet:ON_STREET]->(street:Street)
                    OPTIONAL MATCH (b)-[:ADJACENT_TO]-(nearby:Building)
                    OPTIONAL MATCH (b)-[:ACCESSIBLE_STOP]->(stop:Stop)
                    OPTIONAL MATCH (sensor:Sensor)-[:NEAR_BUILDING]->(b)
                    RETURN b.name AS name,
                           b.function AS function, b.note AS note,
                           b.departments AS departments, b.aliases AS aliases,
                           b.address AS address, b.fiware_type AS fiware_type,
                           collect(DISTINCT {name: street.name, distance_m: onstreet.distance_m}) AS streets,
                           collect(DISTINCT {name: nearby.name, type: 'Building'}) AS nearby_buildings,
                           collect(DISTINCT {name: stop.name, lines: stop.lines}) AS nearest_stops,
                           collect(DISTINCT {name: sensor.name, type: sensor.type}) AS sensors
                """, names=names)
                for r in rows:
                    loc = by_type["Building"].get(r["name"])
                    if not loc:
                        continue
                    loc["function"] = r["function"]
                    loc["note"] = r["note"]
                    loc["departments"] = r["departments"]
                    loc["aliases"] = r["aliases"]
                    loc["address"] = r["address"] or loc.get("address")
                    if r["fiware_type"]:
                        loc["fiware_type"] = r["fiware_type"]
                    streets = [s for s in r["streets"] if s.get("name")]
                    if streets:
                        loc["streets"] = streets
                        loc["street"] = streets[0]["name"]
                    nb = [n for n in r["nearby_buildings"] if n.get("name")]
                    if nb:
                        loc["nearby_buildings"] = nb
                    sensors = [s for s in r["sensors"] if s.get("name")]
                    if sensors:
                        loc["sensors"] = sensors
                    stops = [s for s in r["nearest_stops"] if s.get("name")]
                    if stops:
                        loc["nearest_stops"] = stops
            except Exception as e:
                self._log(f"[NEO4J] enrich Building bulk failed: {e}")

        # --- Stops: just streets ---
        if by_type["Stop"]:
            names = list(by_type["Stop"].keys())
            try:
                rows = session.run("""
                    UNWIND $names AS name
                    MATCH (st:Stop {name: name})
                    OPTIONAL MATCH (st)-[onstreet:ON_STREET]->(street:Street)
                    RETURN st.name AS name,
                           collect(DISTINCT {name: street.name, distance_m: onstreet.distance_m}) AS streets
                """, names=names)
                for r in rows:
                    loc = by_type["Stop"].get(r["name"])
                    if not loc:
                        continue
                    streets = [s for s in r["streets"] if s.get("name")]
                    if streets:
                        loc["streets"] = streets
                        loc["street"] = streets[0]["name"]
            except Exception as e:
                self._log(f"[NEO4J] enrich Stop bulk failed: {e}")

        # --- POIs: details + streets ---
        if by_type["POI"]:
            names = list(by_type["POI"].keys())
            try:
                rows = session.run("""
                    UNWIND $names AS name
                    MATCH (p:POI {name: name})
                    OPTIONAL MATCH (p)-[onstreet:ON_STREET]->(street:Street)
                    RETURN p.name AS name,
                           p.aliases AS aliases, p.note AS note,
                           p.dietary_options AS dietary_options,
                           p.opening_hours AS opening_hours,
                           p.phone AS phone, p.website AS website,
                           collect(DISTINCT {name: street.name, distance_m: onstreet.distance_m}) AS streets
                """, names=names)
                for r in rows:
                    loc = by_type["POI"].get(r["name"])
                    if not loc:
                        continue
                    if r["aliases"]:
                        loc["aliases"] = r["aliases"]
                    if r["note"]:
                        loc["note"] = r["note"]
                    if r["dietary_options"]:
                        loc["dietary_options"] = r["dietary_options"]
                    if r["opening_hours"]:
                        loc["opening_hours"] = r["opening_hours"]
                    if r["phone"]:
                        loc["phone"] = r["phone"]
                    if r["website"]:
                        loc["website"] = r["website"]
                    streets = [s for s in r["streets"] if s.get("name")]
                    if streets:
                        loc["streets"] = streets
                        loc["street"] = streets[0]["name"]
            except Exception as e:
                self._log(f"[NEO4J] enrich POI bulk failed: {e}")

        return locations

    def _enrich_with_street_info(self, session, locations: List[Dict]) -> List[Dict]:
        """DEPRECATED — use `_enrich_locations_bulk` to avoid N+1 queries.
        Add street information to locations using ON_STREET relationship."""
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
        """DEPRECATED — use `_enrich_locations_bulk` to avoid N+1 queries.
        Enrich Building-type results with full properties (function, note, departments, etc.)."""
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
        """DEPRECATED — use `_enrich_locations_bulk` to avoid N+1 queries.
        Enrich POI-type results with aliases, note, and dietary_options from the database."""
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
            if ch in SearchMixin._LUCENE_SPECIAL:
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
            return SearchMixin._escape_lucene(search_term.strip())

        parts = []
        for w in words:
            escaped = SearchMixin._escape_lucene(w)
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

                # Enrich with relationship data in ONE round-trip
                # (was 3 separate passes with N+1 queries each).
                locations = self._enrich_locations_bulk(session, locations)

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
                place_type_lc = (place_type or "all").lower()
                if place_type_lc not in _VALID_PLACE_TYPES:
                    return {"success": False, "error": f"Invalid place_type: {place_type!r}"}
                type_filter = "WHERE toLower(p.type) = $place_type" if place_type_lc != "all" else ""
                query = f"""
                    MATCH (p:POI)
                    {type_filter}
                    RETURN p.name as name, p.type as type, p.cuisine as cuisine,
                           p.address as address, p.latitude as latitude, p.longitude as longitude
                    LIMIT $limit
                """
                result = session.run(query, place_type=place_type_lc, limit=limit)
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
                place_type_lc = place_type.lower()
                if place_type_lc not in _VALID_PLACE_TYPES:
                    return {"success": False, "error": f"Invalid place_type: {place_type!r}"}
                conditions.append("toLower(p.type) = $place_type")
                params["place_type"] = place_type_lc
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

    def find_places_near_coordinates(self, coords: Coordinates, place_type: str = "all",
                                      cuisine: str = None, radius_meters: int = 1000, limit: int = 5) -> Dict:
        self._log(f"[NEO4J] find_places_near_coordinates: {coords.lat}, {coords.lon}")
        with self.driver.session(database=self.database) as session:
            conditions = []
            params = {"lat": coords.lat, "lon": coords.lon, "radius": radius_meters, "limit": limit}
            if place_type and place_type != "all":
                place_type_lc = place_type.lower()
                if place_type_lc not in _VALID_PLACE_TYPES:
                    return {"success": False, "error": f"Invalid place_type: {place_type!r}"}
                conditions.append("toLower(p.type) = $place_type")
                params["place_type"] = place_type_lc
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
