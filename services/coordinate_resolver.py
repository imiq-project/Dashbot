"""
Semantic coordinate resolver for place name to coordinates mapping.

Uses embeddings for fuzzy matching of buildings and transit stops.

Every successful resolve returns a dict-compatible result with a
``resolve_method`` field so callers can distinguish:

  * ``"exact"``     - id / exact-name match in Neo4j
  * ``"semantic"``  - embedding match above threshold AND top-1 vs top-2
                       gap >= TOP_GAP_MIN
  * ``"ambiguous"`` - top candidate failed the gap check; top-3 listed
  * ``"not_found"`` - nothing matched (nearest-fit is NOT silently returned)

``resolve()`` still returns a plain ``Coordinates`` for back-compat.  New
callers can use ``resolve_detailed()`` to get the full result dict.

Embedding warmup runs in a background daemon thread on first instance
creation (L16/L17) so the first user query doesn't block on the index.
"""

import threading
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from models import Coordinates

from .thresholds import BUILDING_EXACT, STOP_EXACT, TOP_GAP_MIN
from ._embedder import ensure_shared_encoder


class CoordinateResolver:

    def __init__(
        self,
        neo4j_graph,
        ors_client,
        encoder,
        magdeburg_lat: float = 52.1205,
        magdeburg_lon: float = 11.6276,
    ):
        self.neo4j_graph = neo4j_graph
        self.ors_client = ors_client
        self.magdeburg_lat = magdeburg_lat
        self.magdeburg_lon = magdeburg_lon
        # Share the process-wide encoder so we don't load the model per-service.
        self.encoder = ensure_shared_encoder(encoder)

        self._building_cache: Optional[Dict[str, Any]] = None
        self._stop_cache: Optional[Dict[str, Any]] = None
        self._cache_initialized = False
        self._cache_lock = threading.Lock()

        # Background warmup (L16/L17).
        self._ready_event = threading.Event()
        self._warmup_thread = threading.Thread(
            target=self._warmup, name="coord-resolver-warmup", daemon=True
        )
        self._warmup_thread.start()

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------

    def _warmup(self) -> None:
        try:
            self._initialize_cache_impl()
        except Exception as e:
            print(f"   Warning: coordinate resolver warmup failed: {e}")
        finally:
            self._ready_event.set()

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Block up to ``timeout`` seconds for the embedding cache to be built.
        Returns True if ready, False on timeout (callers fall back to name lookup).
        """
        return self._ready_event.wait(timeout=timeout)

    def _initialize_cache(self) -> None:
        if self._cache_initialized:
            return
        with self._cache_lock:
            if self._cache_initialized:
                return
            self._initialize_cache_impl()

    def _initialize_cache_impl(self) -> None:
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

                buildings: List[Dict[str, Any]] = []
                building_texts: List[str] = []

                for record in result:
                    building = {
                        "id": record["id"],
                        "name": record["name"],
                        "function": record["function"],
                        "aliases": record["aliases"],
                        "lat": record["lat"],
                        "lon": record["lon"],
                    }
                    buildings.append(building)

                    building_id = record["id"] or ""
                    search_parts: List[str] = [
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
                    building_embeddings = self.encoder.encode(
                        building_texts, normalize_embeddings=True
                    )
                    self._building_cache = {
                        "buildings": buildings,
                        "texts": building_texts,
                        "embeddings": building_embeddings,
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

                stops: List[Dict[str, Any]] = []
                stop_texts: List[str] = []

                for record in result:
                    stop = {
                        "name": record["name"],
                        "lat": record["lat"],
                        "lon": record["lon"],
                        "lines": record["lines"],
                    }
                    stops.append(stop)

                    name = record["name"] or ""
                    short_name = name.replace("Magdeburg ", "")
                    stop_texts.append(f"{name} | {short_name}")

                if stop_texts:
                    stop_embeddings = self.encoder.encode(
                        stop_texts, normalize_embeddings=True
                    )
                    self._stop_cache = {
                        "stops": stops,
                        "texts": stop_texts,
                        "embeddings": stop_embeddings,
                    }
                    print(f"   Indexed {len(stops)} stops")

                self._cache_initialized = True

        except Exception as e:
            print(f"   Warning: Error building search index: {e}")
            self._cache_initialized = False

    # ------------------------------------------------------------------
    # Public resolution API
    # ------------------------------------------------------------------

    def resolve(self, place_name: str) -> Optional[Coordinates]:
        """Back-compat entry point: returns Coordinates or None."""
        detail = self.resolve_detailed(place_name)
        if detail and detail.get("resolve_method") in ("exact", "semantic"):
            return Coordinates(lat=detail["lat"], lon=detail["lon"])
        return None

    def resolve_detailed(self, place_name: str) -> Dict[str, Any]:
        """Return a dict with ``resolve_method`` set to one of
        ``"exact" | "semantic" | "ambiguous" | "not_found"``.
        """
        if not place_name:
            return {"resolve_method": "not_found", "query": place_name}

        original = place_name
        normalized = place_name.lower().strip()

        # Use embeddings if ready; otherwise fall back to name-only lookups.
        self.wait_until_ready(0.1)

        # 1. Exact building id pattern (e.g., "Building 04").
        building_id = self._extract_building_id(normalized)
        if building_id:
            exact = self._get_building_by_id(building_id)
            if exact is not None:
                return {
                    "resolve_method": "exact",
                    "type": "building",
                    "query": original,
                    "id": building_id,
                    **exact,
                }

        # 2. Exact stop name match.
        exact_stop = self._exact_stop_match(normalized)
        if exact_stop is not None:
            return {
                "resolve_method": "exact",
                "type": "stop",
                "query": original,
                **exact_stop,
            }

        # 3. Semantic building search (with top-1/top-2 gap enforcement).
        b_result = self._semantic_search(self._building_cache, normalized, "building", BUILDING_EXACT)
        if b_result is not None:
            b_result["query"] = original
            if b_result["resolve_method"] != "not_found":
                return b_result

        # 4. Semantic stop search.
        s_result = self._semantic_search(self._stop_cache, normalized, "stop", STOP_EXACT)
        if s_result is not None:
            s_result["query"] = original
            if s_result["resolve_method"] != "not_found":
                return s_result

        # 5. Ambiguous from either layer — prefer whichever had candidates.
        if b_result is not None and b_result.get("candidates"):
            return b_result
        if s_result is not None and s_result.get("candidates"):
            return s_result

        # 6. ORS geocode fallback — only if query doesn't look building-shaped.
        if not self._is_likely_building(normalized, original):
            try:
                coords = self.ors_client.geocode(
                    place_name, self.magdeburg_lat, self.magdeburg_lon
                )
                if coords:
                    return {
                        "resolve_method": "exact",
                        "type": "geocode",
                        "query": original,
                        "lat": coords.lat,
                        "lon": coords.lon,
                    }
            except Exception as e:  # ORS failure shouldn't crash the caller
                print(f"   Warning: ORS geocode failed: {e}")

        return {"resolve_method": "not_found", "query": original}

    # ------------------------------------------------------------------
    # Building / stop lookups
    # ------------------------------------------------------------------

    def _extract_building_id(self, text: str) -> Optional[str]:
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

    def _get_building_by_id(self, building_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self.neo4j_graph.driver.session(database=self.neo4j_graph.database) as session:
                result = session.run(
                    """
                    MATCH (b:Building)
                    WHERE b.id = $id
                    RETURN b.name as name, b.longitude as lon, b.latitude as lat
                    LIMIT 1
                    """,
                    id=building_id,
                )
                record = result.single()
                if record:
                    print(f"   Found Building {building_id}: {record['name']}")
                    return {
                        "name": record["name"],
                        "lat": record["lat"],
                        "lon": record["lon"],
                    }
        except Exception as e:
            print(f"   Warning: Error getting building by ID: {e}")
        return None

    def _exact_stop_match(self, normalized: str) -> Optional[Dict[str, Any]]:
        try:
            with self.neo4j_graph.driver.session(database=self.neo4j_graph.database) as session:
                search_terms = [
                    normalized,
                    f"magdeburg {normalized}",
                    normalized.replace("magdeburg ", ""),
                ]

                # Collect ALL matches so ambiguous stops (e.g., two
                # "Hauptbahnhof" entries) can be surfaced rather than silently
                # picking one.  If there's exactly one match we return exact;
                # if more than one, ambiguous.
                seen = set()
                matches: List[Dict[str, Any]] = []
                for search in search_terms:
                    result = session.run(
                        """
                        MATCH (s:Stop)
                        WHERE toLower(s.name) = $search
                        RETURN s.name as name, s.longitude as lon, s.latitude as lat
                        LIMIT 5
                        """,
                        search=search,
                    )
                    for record in result:
                        key = (record["name"], record["lat"], record["lon"])
                        if key in seen:
                            continue
                        seen.add(key)
                        matches.append(
                            {
                                "name": record["name"],
                                "lat": record["lat"],
                                "lon": record["lon"],
                            }
                        )

                if len(matches) == 1:
                    print(f"   Found Stop: {matches[0]['name']}")
                    return matches[0]
                if len(matches) > 1:
                    # Surface as ambiguous via resolve_detailed's caller path —
                    # but _exact_stop_match signature returns a single dict,
                    # so only return when unambiguous; otherwise fall through
                    # to semantic search which can return full ambiguous info.
                    return None
        except Exception as e:
            print(f"   Warning: Error in exact stop match: {e}")
        return None

    # ------------------------------------------------------------------
    # Semantic search with threshold + top-gap enforcement
    # ------------------------------------------------------------------

    def _semantic_search(
        self,
        cache: Optional[Dict[str, Any]],
        query: str,
        entity_type: str,
        threshold: float,
    ) -> Optional[Dict[str, Any]]:
        """Shared semantic match logic.

        Returns one of:
          * ``{"resolve_method": "semantic", ...}`` - top-1 passes threshold
             and beats top-2 by >= TOP_GAP_MIN
          * ``{"resolve_method": "ambiguous", "candidates": [top3]}`` -
             top-1 passes threshold but tied with top-2
          * ``None`` - cache missing / query not encodable
          * ``{"resolve_method": "not_found"}`` - no candidate above threshold

        ``candidates`` is a list of ``{name, lat, lon, score}`` dicts ordered
        by score desc, limited to 3.
        """
        if not cache:
            return None

        try:
            query_embedding = self.encoder.encode(query, normalize_embeddings=True)
            similarities = np.dot(cache["embeddings"], query_embedding)

            if similarities.size == 0:
                return {"resolve_method": "not_found"}

            order = np.argsort(similarities)[::-1]
            best_idx = int(order[0])
            best_score = float(similarities[best_idx])
            second_score = float(similarities[int(order[1])]) if similarities.size > 1 else 0.0

            if best_score < threshold:
                return {"resolve_method": "not_found"}

            top3_idx = [int(i) for i in order[:3]]
            candidates: List[Dict[str, Any]] = []
            key = "buildings" if entity_type == "building" else "stops"
            for i in top3_idx:
                item = cache[key][i]
                candidates.append(
                    {
                        "name": item.get("name"),
                        "lat": item.get("lat"),
                        "lon": item.get("lon"),
                        "score": float(similarities[i]),
                    }
                )

            gap = best_score - second_score
            if gap < TOP_GAP_MIN:
                print(
                    f"   Ambiguous {entity_type} (top={best_score:.2f}, "
                    f"gap={gap:.2f} < {TOP_GAP_MIN}); returning candidates"
                )
                return {
                    "resolve_method": "ambiguous",
                    "type": entity_type,
                    "confidence": "ambiguous",
                    "candidates": candidates,
                    "score": best_score,
                    "gap": gap,
                }

            best = cache[key][best_idx]
            print(
                f"   Found {entity_type} (semantic, {best_score:.2f}, "
                f"gap={gap:.2f}): {best.get('name')}"
            )
            return {
                "resolve_method": "semantic",
                "type": entity_type,
                "name": best.get("name"),
                "lat": best.get("lat"),
                "lon": best.get("lon"),
                "score": best_score,
                "gap": gap,
                "candidates": candidates,
            }

        except Exception as e:
            print(f"   Warning: Error in semantic {entity_type} search: {e}")
            return None

    # Thin back-compat wrappers — retained in case external modules imported them.
    def _semantic_building_search(
        self, query: str, threshold: float = BUILDING_EXACT
    ) -> Optional[Coordinates]:
        result = self._semantic_search(self._building_cache, query, "building", threshold)
        if result and result.get("resolve_method") == "semantic":
            return Coordinates(lat=result["lat"], lon=result["lon"])
        return None

    def _semantic_stop_search(
        self, query: str, threshold: float = STOP_EXACT
    ) -> Optional[Coordinates]:
        result = self._semantic_search(self._stop_cache, query, "stop", threshold)
        if result and result.get("resolve_method") == "semantic":
            return Coordinates(lat=result["lat"], lon=result["lon"])
        return None

    def _is_likely_building(self, normalized: str, original: str) -> bool:
        building_keywords = [
            "building",
            "bldg",
            "gebäude",
            "faculty",
            "department",
            "institute",
            "center",
            "centre",
            "library",
            "mensa",
        ]
        return any(kw in normalized for kw in building_keywords)


_resolver_instance: Optional[CoordinateResolver] = None


def initialize_resolver(
    neo4j_graph,
    ors_client,
    encoder,
    magdeburg_lat: float = 52.1205,
    magdeburg_lon: float = 11.6276,
) -> CoordinateResolver:
    global _resolver_instance
    _resolver_instance = CoordinateResolver(
        neo4j_graph, ors_client, encoder, magdeburg_lat, magdeburg_lon
    )
    return _resolver_instance


def get_coordinates(place_name: str) -> Optional[Coordinates]:
    if _resolver_instance is None:
        raise RuntimeError(
            "Coordinate resolver not initialized. Call initialize_resolver() first."
        )
    return _resolver_instance.resolve(place_name)


if __name__ == "__main__":
    print("CoordinateResolver with Semantic Search")
    print("Requires Neo4j and ORS clients to run.")
