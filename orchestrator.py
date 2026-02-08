"""
Multi-agent orchestrator for coordinating the Magdeburg Mobility Assistant agents.
Manages the pipeline: RouterAgent (intent) -> Specialist Agents (Neo4j, FIWARE) -> SynthesizerAgent (response).
Handles proactive context (weather, parking, traffic) and conversation history.
"""

from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from agents import (
    RouterAgent,
    Neo4jAgent,
    FIWAREAgent,
    SynthesizerAgent,
    create_router_agent,
    create_neo4j_agent,
    create_fiware_agent,
    create_synthesizer_agent
)

from prompts.synthesizer_prompts import SynthesizerMode

from neo4j_tools import Neo4jTransitGraph
from clients.fiware_client import FIWAREClient
from clients.ors_client import ORSClient


class AgentOrchestrator:

    def __init__(
        self,
        llm_client: Any,
        neo4j_graph: Neo4jTransitGraph,
        fiware_client: FIWAREClient,
        ors_client: Optional[ORSClient] = None,
        tomtom_client: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
        knowledge_base: Optional[Any] = None
    ):
        self.llm_client = llm_client
        self.neo4j_graph = neo4j_graph
        self.fiware_client = fiware_client
        self.ors_client = ors_client
        self.tomtom_client = tomtom_client
        self.config = config or {}
        self.verbose = verbose
        self.knowledge_base = knowledge_base

        self.session_histories: Dict[str, List[Dict[str, Any]]] = {}
        self.max_history_turns = self.config.get("max_history_turns", 10)

        # Entity caching disabled for Neo4j - all queries go directly to database

        self._log("🔧 Initializing agents...")

        self.router_agent = create_router_agent(
            client=llm_client,
            config=self._get_agent_config("router"),
            verbose=False
        )

        self.neo4j_agent = create_neo4j_agent(
            client=llm_client,
            config=self._get_agent_config("neo4j"),
            verbose=False
        )

        self.fiware_agent = create_fiware_agent(
            client=llm_client,
            config=self._get_agent_config("fiware"),
            fiware_client=fiware_client,
            tomtom_client=tomtom_client,
            verbose=False
        )

        self.synthesizer_agent = create_synthesizer_agent(
            client=llm_client,
            config=self._get_agent_config("synthesizer"),
            verbose=False
        )

        self.max_parallel_workers = self.config.get("max_parallel_workers", 3)

        self._log("✅ Orchestrator ready!")

    def _get_agent_config(self, agent_type: str) -> Dict[str, Any]:
        return self.config.get(f"{agent_type}_config", {})

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[ORCHESTRATOR] {message}")

    def _get_session_history(self, session_id: str = "default") -> List[Dict[str, Any]]:
        return self.session_histories.get(session_id, [])

    def _get_conversation_context(self, session_id: str = "default") -> List[Dict[str, str]]:
        history = self._get_session_history(session_id)
        context = []
        for turn in history[-self.max_history_turns:]:
            context.append({"role": "user", "content": turn["query"]})
            context.append({"role": "assistant", "content": turn["response"]})
        return context

    def _add_to_history(
        self,
        query: str,
        response: str,
        router_output,
        specialist_results: Dict[str, Any],
        session_id: str = "default"
    ) -> None:
        if session_id not in self.session_histories:
            self.session_histories[session_id] = []

        self.session_histories[session_id].append({
            "query": query,
            "response": response,
            "intent": router_output.primary_intent,
            "entities": router_output.entities,
            "specialist_results": specialist_results
        })

        if len(self.session_histories[session_id]) > self.max_history_turns:
            self.session_histories[session_id] = self.session_histories[session_id][-self.max_history_turns:]

    def reset_conversation(self, session_id: str = None) -> None:
        if session_id:
            self.session_histories.pop(session_id, None)
            self._log(f"🔄 Session '{session_id}' history cleared")
        else:
            self.session_histories.clear()
            self._log("🔄 All conversation histories cleared")

    def process_query(self, query: str, session_id: str = "default") -> str:
        start_time = time.time()

        try:
            print(f"\n{'='*60}")
            print(f"[MULTI-AGENT] Query: '{query}'")
            print(f"{'='*60}")

            conversation_context = self._get_conversation_context(session_id)

            # --- Step 1: Intent Classification ---
            routing_start = time.time()
            router_output = self.router_agent.parse_query(
                query,
                conversation_context=conversation_context
            )
            routing_time = time.time() - routing_start

            print(f"\n-- INTENT CLASSIFICATION (RouterAgent) {'-'*21}")
            print(f"  Intent:       {router_output.primary_intent}")
            print(f"  Confidence:   {router_output.confidence:.2f}")
            if router_output.sub_intents:
                print(f"  Sub-intents:  {router_output.sub_intents}")
            print(f"  Capabilities: {', '.join(router_output.required_capabilities) if router_output.required_capabilities else '(none)'}")
            print(f"  Strategy:     {router_output.execution_strategy}")
            print(f"  Routing time: {routing_time*1000:.0f} ms")

            if router_output.needs_clarification():
                print(f"  Clarification: {router_output.clarification_question}")

            # --- Entity Resolution ---
            entities = router_output.entities or {}
            found_entities = {k: v for k, v in entities.items() if v}

            intent_required_entities = {
                "find_route": ["origin", "destination"],
                "get_route": ["origin", "destination"],
                "get_weather": ["weather_location"],
                "get_parking_info": ["location"],
                "get_traffic_info": ["origin", "destination"],
                "get_air_quality": ["location"],
                "get_location_info": ["location", "building_name"],
                "get_transit_info": ["poi_name"],
                "find_places": ["location", "poi_name"],
                "knowledge_query": [],
                "get_sensor_info": ["location"],
            }
            relevant_keys = intent_required_entities.get(router_output.primary_intent, [])
            missing_entities = [k for k in relevant_keys if not entities.get(k)]

            print(f"\n-- ENTITIES (RouterAgent) {'-'*32}")
            if found_entities:
                for k, v in found_entities.items():
                    print(f"  {k:20s} {v}")
            else:
                print(f"  (none extracted)")
            if missing_entities:
                print(f"  Missing:            {', '.join(missing_entities)}")

            # --- Step 2: Specialists ---
            caps = router_output.required_capabilities
            if caps:
                print(f"\n  [Running specialists: {', '.join(caps)}...]")
            specialist_start = time.time()
            specialist_results = self._execute_specialists(
                query, router_output, conversation_context
            )
            specialist_time = time.time() - specialist_start

            origin_coords = None
            dest_coords = None
            ors_result = specialist_results.get("ors", {})
            if ors_result.get("success"):
                if ors_result.get("origin_coords"):
                    origin_coords = tuple(ors_result["origin_coords"])
                if ors_result.get("destination_coords"):
                    dest_coords = tuple(ors_result["destination_coords"])

            proactive_context = self._get_proactive_context(
                router_output.primary_intent,
                router_output.entities,
                query,
                origin_coords=origin_coords,
                destination_coords=dest_coords
            )
            if proactive_context:
                specialist_results["proactive_context"] = proactive_context

            print(f"\n-- SPECIALISTS {'-'*42}")
            for agent_name in ["neo4j", "fiware", "ors", "knowledge"]:
                if agent_name in specialist_results:
                    res = specialist_results[agent_name]
                    status = "OK" if res.get("success") else f"FAIL ({res.get('error', 'unknown')})"
                    print(f"  {agent_name:12s} {status}")
                else:
                    print(f"  {agent_name:12s} SKIPPED")
            if proactive_context:
                print(f"  proactive:     {', '.join(proactive_context.keys())}")
            print(f"  Specialist time: {specialist_time*1000:.0f} ms")

            # --- Step 3: Synthesis ---
            print(f"\n  [Synthesizing response...]")
            synthesis_start = time.time()
            response = self.synthesizer_agent.synthesize(
                query=query,
                router_output=router_output.to_dict(),
                specialist_results=specialist_results,
                conversation_context=conversation_context,
                proactive_context=proactive_context
            )
            synthesis_time = time.time() - synthesis_start

            self._add_to_history(query, response, router_output, specialist_results, session_id=session_id)

            total_time = time.time() - start_time

            print(f"\n-- RESPONSE {'-'*45}")
            print(f"  Length:  {len(response)} chars")
            preview = response[:80].replace('\n', ' ')
            print(f"  Preview: {preview}{'...' if len(response) > 80 else ''}")

            print(f"\n-- LATENCY SUMMARY {'-'*38}")
            print(f"  Routing:      {routing_time*1000:>6.0f} ms")
            print(f"  Specialists:  {specialist_time*1000:>6.0f} ms")
            print(f"  Synthesis:    {synthesis_time*1000:>6.0f} ms")
            print(f"  TOTAL:        {total_time*1000:>6.0f} ms")
            print(f"{'='*60}")

            return response

        except Exception as e:
            total_time = time.time() - start_time
            print(f"\n-- ERROR {'-'*48}")
            print(f"  {str(e)}")
            print(f"  After: {total_time*1000:.0f} ms")
            import traceback
            traceback.print_exc()

            return (
                "I'm sorry, I encountered an error while processing your request. "
                "Please try again or rephrase your question."
            )

    def _execute_specialists(
        self,
        query: str,
        router_output,
        conversation_context: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        results = {}

        capabilities = router_output.required_capabilities

        if not capabilities:
            self._log("   No specialists needed (greeting/out-of-scope)")
            return results

        if router_output.should_run_parallel():
            self._log("   ⚡ Running specialists in PARALLEL")
            results = self._execute_parallel(query, router_output, capabilities, conversation_context)
        else:
            self._log("   ➡️  Running specialists SEQUENTIALLY")
            results = self._execute_sequential(query, router_output, capabilities, conversation_context)

        return results

    def _execute_parallel(
        self,
        query: str,
        router_output,
        capabilities: List[str],
        conversation_context: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        results = {}

        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            futures = {}

            if "graph_location_lookup" in capabilities:
                future = executor.submit(
                    self._call_neo4j, query, router_output, conversation_context
                )
                futures[future] = "neo4j"

            if "sensor_data_retrieval" in capabilities or "traffic_data_retrieval" in capabilities:
                future = executor.submit(self._call_fiware, query, router_output)
                futures[future] = "fiware"

            if "knowledge_base_search" in capabilities:
                future = executor.submit(self._call_knowledge_base, query)
                futures[future] = "knowledge"

            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    result = future.result()
                    results[agent_name] = result
                    self._log(f"   ✅ {agent_name} completed")
                except Exception as e:
                    self._log(f"   ❌ {agent_name} failed: {str(e)}")
                    results[agent_name] = {"success": False, "error": str(e)}

        # Auto-trigger FIWARE if Neo4j returned a building with fiware_type (e.g. Mensa menu)
        if "fiware" not in results:
            fiware_type = self._extract_fiware_type_from_neo4j(results.get("neo4j"))
            if fiware_type:
                results["fiware"] = self._auto_fiware_for_building(query, router_output, fiware_type)

        return results

    def _execute_sequential(
        self,
        query: str,
        router_output,
        capabilities: List[str],
        conversation_context: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        results = {}

        if "graph_location_lookup" in capabilities:
            try:
                results["neo4j"] = self._call_neo4j(query, router_output, conversation_context)
                self._log(f"   ✅ neo4j completed")

                if results["neo4j"] and "fiware_id" in results["neo4j"]:
                    self._log(f"      🎯 Neo4j found sensor: {results['neo4j']['fiware_id']}")

            except Exception as e:
                self._log(f"   ❌ neo4j failed: {str(e)}")
                results["neo4j"] = {"success": False, "error": str(e)}

        # Auto-trigger FIWARE if Neo4j returned a building with fiware_type (e.g. Mensa menu)
        if "fiware" not in results:
            fiware_type = self._extract_fiware_type_from_neo4j(results.get("neo4j"))
            if fiware_type:
                results["fiware"] = self._auto_fiware_for_building(query, router_output, fiware_type)

        if "sensor_data_retrieval" in capabilities or "traffic_data_retrieval" in capabilities:
            try:
                neo4j_context = results.get("neo4j")

                self._log(f"      Calling FIWARE with Neo4j context: {bool(neo4j_context)}")

                results["fiware"] = self._call_fiware(
                    query,
                    router_output,
                    neo4j_context=neo4j_context
                )
                self._log(f"   ✅ fiware completed")

            except Exception as e:
                self._log(f"   ❌ fiware failed: {str(e)}")
                results["fiware"] = {"success": False, "error": str(e)}

        if "transit_routing" in capabilities:
            try:
                self._log(f"   🗺️ Processing ORS routing...")
                neo4j_result = results.get("neo4j", {})

                origin_coords, dest_coords = self._extract_coordinates_from_neo4j(
                    neo4j_result, router_output
                )

                if not origin_coords or not dest_coords:
                    entities = router_output.entities if hasattr(router_output, 'entities') else {}
                    origin_name = entities.get("origin")
                    dest_name = entities.get("destination")

                    self._log(f"      Looking up coordinates: origin='{origin_name}', dest='{dest_name}'")

                    if origin_name and not origin_coords:
                        origin_coords = self._get_coordinates_for_location(origin_name)
                        if origin_coords:
                            self._log(f"      📍 Found origin coords: {origin_coords}")

                    if dest_name and not dest_coords:
                        dest_coords = self._get_coordinates_for_location(dest_name)
                        if dest_coords:
                            self._log(f"      📍 Found dest coords: {dest_coords}")

                if origin_coords and dest_coords:
                    results["ors"] = self._call_ors(origin_coords, dest_coords)
                    self._log(f"   ✅ ors completed")
                else:
                    missing = []
                    if not origin_coords:
                        missing.append("origin")
                    if not dest_coords:
                        missing.append("destination")
                    self._log(f"   ⚠️ ORS skipped - missing coordinates for: {missing}")
                    results["ors"] = {
                        "success": False,
                        "error": f"Could not find coordinates for: {', '.join(missing)}"
                    }

            except Exception as e:
                self._log(f"   ❌ ors failed: {str(e)}")
                if self.verbose:
                    import traceback
                    traceback.print_exc()
                results["ors"] = {"success": False, "error": str(e)}

        return results

    def _call_neo4j(
        self,
        query: str,
        router_output,
        conversation_context: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        try:
            neo4j_output = self.neo4j_agent.map_query(
                query,
                router_output.to_dict(),
                conversation_context=conversation_context
            )

            print(f"  neo4j fn:  {neo4j_output.function_name}({neo4j_output.parameters})")

            func = getattr(self.neo4j_graph, neo4j_output.function_name)
            result = func(**neo4j_output.parameters)

            # Debug: show what Neo4j actually returned
            if result.get("results"):
                for r in result["results"][:3]:
                    print(f"  neo4j >>   {r.get('type','?')}: {r.get('name','?')} (score={r.get('score',0)})")
            elif result.get("building"):
                b = result["building"]
                bname = b.get("name", "?") if isinstance(b, dict) else "?"
                print(f"  neo4j >>   Building: {bname}")

            return result

        except Exception as e:
            self._log(f"      Neo4j error: {str(e)}")
            return {"success": False, "error": str(e)}

    def _call_fiware(self, query: str, router_output, neo4j_context: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            fiware_override = None

            if neo4j_context and isinstance(neo4j_context, dict) and neo4j_context.get("success"):
                sensor_info = None
                sensor_type = None

                if "sensor" in neo4j_context and isinstance(neo4j_context["sensor"], dict):
                    sensor_info = neo4j_context["sensor"]
                    self._log(f"      📍 Found single sensor in Neo4j result")

                elif "sensors" in neo4j_context and isinstance(neo4j_context["sensors"], list):
                    if neo4j_context["sensors"]:
                        sensor_info = neo4j_context["sensors"][0]
                        self._log(f"      📍 Found {len(neo4j_context['sensors'])} sensors, using first one")

                elif "fiware_id" in neo4j_context:
                    sensor_info = neo4j_context
                    self._log(f"      📍 Found fiware_id at top level")

                if sensor_info:
                    sensor_id = sensor_info.get("fiware_id") or sensor_info.get("id") or sensor_info.get("name")
                    sensor_type = sensor_info.get("type", "")

                    if sensor_id:
                        entity_type = self._map_sensor_type_to_fiware(sensor_type)

                        self._log(f"      🎯 Using Neo4j sensor: {sensor_id} (type: {sensor_type} → {entity_type})")

                        fiware_override = {
                            "entity_id": sensor_id,
                            "entity_type": entity_type,
                            "limit": 1
                        }

                        self._log(f"      🔍 FIWARE override params: {fiware_override}")

            router_dict = router_output.to_dict()
            primary_intent = router_dict.get("primary_intent", "")

            if primary_intent == "get_traffic_info" or "traffic" in query.lower():
                self._log(f"      🚦 Detected traffic query, using query_realtime_data (TomTom)")
                result = self.fiware_agent.query_realtime_data(
                    query,
                    router_dict,
                    origin_coords=None,
                    dest_coords=None
                )
            elif fiware_override:
                self._log(f"      📍 Querying FIWARE with Neo4j-provided params")
                result = self.fiware_agent.query_sensors(
                    query,
                    router_dict,
                    override_params=fiware_override
                )
            else:
                self._log(f"      📍 Querying FIWARE with LLM-extracted params")
                result = self.fiware_agent.query_sensors(
                    query,
                    router_dict,
                    override_params=fiware_override
                )

            return result

        except Exception as e:
            self._log(f"      FIWARE error: {str(e)}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return {"success": False, "error": str(e)}

    def _call_knowledge_base(self, query: str) -> Dict[str, Any]:
        try:
            if not self.knowledge_base:
                self._log("      ⚠️ Knowledge base not configured")
                return {"success": False, "error": "Knowledge base not available"}

            self._log(f"      📚 Searching knowledge base for: '{query}'")
            results = self.knowledge_base.search(query, top_k=3)

            if results:
                self._log(f"      ✅ Found {len(results)} relevant documents")
                return {
                    "success": True,
                    "results": results,
                    "query": query
                }
            else:
                self._log("      ❌ No relevant documents found")
                return {"success": False, "error": "No relevant documents found"}

        except Exception as e:
            self._log(f"      Knowledge base error: {str(e)}")
            return {"success": False, "error": str(e)}

    def _call_ors(
        self,
        origin_coords: tuple,
        dest_coords: tuple,
        modes: List[str] = None
    ) -> Dict[str, Any]:
        if modes is None:
            modes = ["walking", "cycling", "driving"]

        result = {
            "success": True,
            "origin_coords": origin_coords,
            "destination_coords": dest_coords,
            "routes": {}
        }

        ors_modes = [m for m in modes if m in ["walking", "cycling"]]
        use_tomtom_for_driving = "driving" in modes

        try:
            if ors_modes and self.ors_client:
                self._log(f"      🗺️ Calling ORS for modes: {ors_modes}")
                self._log(f"      📍 Origin: {origin_coords}, Dest: {dest_coords}")

                ors_routes = self.ors_client.get_multi_modal_routes(
                    origin_coords,
                    dest_coords,
                    ors_modes
                )

                for mode, route_data in ors_routes.items():
                    if route_data.get("success"):
                        result["routes"][mode] = {
                            "available": True,
                            "source": "ors",
                            "distance": route_data.get("distance"),
                            "distance_meters": route_data.get("distance_meters"),
                            "duration": route_data.get("duration"),
                            "duration_seconds": route_data.get("duration_seconds")
                        }
                        self._log(f"      ✅ {mode} (ORS): {route_data.get('duration')} ({route_data.get('distance')})")
                    else:
                        result["routes"][mode] = {
                            "available": False,
                            "error": route_data.get("error", "Route not available")
                        }
                        self._log(f"      ❌ {mode}: {route_data.get('error')}")

            elif ors_modes and not self.ors_client:
                self._log("      ⚠️ ORS client not configured for walking/cycling")
                for mode in ors_modes:
                    result["routes"][mode] = {
                        "available": False,
                        "error": "ORS client not available"
                    }

            if use_tomtom_for_driving:
                if self.tomtom_client:
                    self._log(f"      🚗 Calling TomTom for driving route (traffic-aware)")

                    origin_lat_lon = (origin_coords[1], origin_coords[0])
                    dest_lat_lon = (dest_coords[1], dest_coords[0])

                    driving_route = self.tomtom_client.get_driving_route_with_directions(
                        origin_lat_lon,
                        dest_lat_lon,
                        max_steps=6
                    )

                    if driving_route.get("success"):
                        result["routes"]["driving"] = {
                            "available": True,
                            "source": "tomtom",
                            "distance": driving_route.get("distance"),
                            "distance_meters": driving_route.get("distance_meters"),
                            "duration": driving_route.get("duration"),
                            "duration_seconds": driving_route.get("duration_seconds"),
                            "traffic_delay_minutes": driving_route.get("traffic_delay_minutes", 0),
                            "traffic_status": driving_route.get("traffic_status", "clear"),
                            "traffic_message": driving_route.get("traffic_message", ""),
                            "directions": driving_route.get("directions", []),
                            "directions_text": driving_route.get("directions_text", []),
                            "streets_on_route": driving_route.get("streets_on_route", []),
                            "departure_time": driving_route.get("departure_time", ""),
                            "arrival_time": driving_route.get("arrival_time", "")
                        }
                        delay = driving_route.get("traffic_delay_minutes", 0)
                        self._log(f"      ✅ driving (TomTom): {driving_route.get('duration')} ({driving_route.get('distance')}) - {driving_route.get('traffic_status')}")
                        if delay > 0:
                            self._log(f"         🚦 Traffic delay: {delay} min")
                        if driving_route.get("streets_on_route"):
                            self._log(f"         🛣️ Streets: {', '.join(driving_route['streets_on_route'][:3])}...")
                    else:
                        result["routes"]["driving"] = {
                            "available": False,
                            "error": driving_route.get("error", "Driving route not available")
                        }
                        self._log(f"      ❌ driving (TomTom): {driving_route.get('error')}")
                else:
                    self._log("      ⚠️ TomTom not available, falling back to ORS for driving")
                    if self.ors_client:
                        ors_driving = self.ors_client.get_route(origin_coords, dest_coords, "driving")
                        if ors_driving and ors_driving.get("success"):
                            result["routes"]["driving"] = {
                                "available": True,
                                "source": "ors",
                                "distance": ors_driving.get("distance"),
                                "distance_meters": ors_driving.get("distance_meters"),
                                "duration": ors_driving.get("duration"),
                                "duration_seconds": ors_driving.get("duration_seconds")
                            }
                            self._log(f"      ✅ driving (ORS fallback): {ors_driving.get('duration')}")
                        else:
                            result["routes"]["driving"] = {
                                "available": False,
                                "error": ors_driving.get("error") if ors_driving else "Route not available"
                            }
                    else:
                        result["routes"]["driving"] = {
                            "available": False,
                            "error": "No routing service available for driving"
                        }

            return result

        except Exception as e:
            self._log(f"      Routing error: {str(e)}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return {"success": False, "error": str(e)}

    def _extract_coordinates_from_neo4j(
        self,
        neo4j_result: Dict[str, Any],
        router_output
    ) -> tuple:
        origin_coords = None
        dest_coords = None

        if not neo4j_result or not neo4j_result.get("success"):
            return None, None

        entities = router_output.entities if hasattr(router_output, 'entities') else {}
        origin_name = entities.get("origin")
        dest_name = entities.get("destination")

        results = neo4j_result.get("results", [])
        if results:
            for r in results:
                coords_obj = r.get("coordinates", {})
                lat = coords_obj.get("latitude") or r.get("latitude") or r.get("lat")
                lon = coords_obj.get("longitude") or r.get("longitude") or r.get("lon")
                name = (r.get("name") or "").lower()

                if lat and lon:
                    coords = (lon, lat)

                    if origin_name and origin_name.lower() in name:
                        origin_coords = coords
                    elif dest_name and dest_name.lower() in name:
                        dest_coords = coords
                    elif not origin_coords:
                        origin_coords = coords
                    elif not dest_coords:
                        dest_coords = coords

        if "route" in neo4j_result:
            route = neo4j_result["route"]
            if route.get("origin_info"):
                oi = route["origin_info"]
                if oi.get("latitude") and oi.get("longitude"):
                    origin_coords = (oi["longitude"], oi["latitude"])
            if route.get("destination_info"):
                di = route["destination_info"]
                if di.get("latitude") and di.get("longitude"):
                    dest_coords = (di["longitude"], di["latitude"])

        if "location1" in neo4j_result:
            loc1 = neo4j_result["location1"]
            if loc1.get("latitude") and loc1.get("longitude"):
                origin_coords = (loc1["longitude"], loc1["latitude"])
        if "location2" in neo4j_result:
            loc2 = neo4j_result["location2"]
            if loc2.get("latitude") and loc2.get("longitude"):
                dest_coords = (loc2["longitude"], loc2["latitude"])

        if "from" in neo4j_result and isinstance(neo4j_result["from"], dict):
            f = neo4j_result["from"]
            if f.get("latitude") and f.get("longitude"):
                origin_coords = (f["longitude"], f["latitude"])
        if "to" in neo4j_result and isinstance(neo4j_result["to"], dict):
            t = neo4j_result["to"]
            if t.get("latitude") and t.get("longitude"):
                dest_coords = (t["longitude"], t["latitude"])

        return origin_coords, dest_coords

    def _get_coordinates_for_location(self, location_name: str) -> Optional[tuple]:
        try:
            result = self.neo4j_graph.find_any_location(location_name, limit=1)
            if result.get("success") and result.get("results"):
                loc = result["results"][0]
                coords = loc.get("coordinates", {})
                lat = coords.get("latitude") or loc.get("latitude") or loc.get("lat")
                lon = coords.get("longitude") or loc.get("longitude") or loc.get("lon")
                if lat and lon:
                    return (lon, lat)
        except Exception as e:
            self._log(f"      Error getting coordinates for {location_name}: {e}")
        return None

    def _extract_fiware_type_from_neo4j(self, neo4j_result: Dict[str, Any]) -> Optional[str]:
        """Scan Neo4j result for buildings with fiware_type (e.g. Mensa)."""
        if not neo4j_result or not neo4j_result.get("success"):
            return None

        # Check single building result
        building = neo4j_result.get("building")
        if isinstance(building, dict) and building.get("fiware_type"):
            return building["fiware_type"]

        # Check results list
        for r in neo4j_result.get("results", []):
            if isinstance(r, dict) and r.get("fiware_type"):
                return r["fiware_type"]

        return None

    def _auto_fiware_for_building(
        self, query: str, router_output, fiware_type: str
    ) -> Dict[str, Any]:
        """Call FIWARE by entity type discovered from a Neo4j building node."""
        self._log(f"      🍽️ Auto-triggering FIWARE for building fiware_type='{fiware_type}'")
        override = {"entity_type": fiware_type, "limit": 1}
        try:
            result = self.fiware_agent.query_sensors(
                query,
                router_output.to_dict(),
                override_params=override
            )
            self._log(f"      ✅ FIWARE auto-call completed (success={result.get('success')})")
            return result
        except Exception as e:
            self._log(f"      ❌ FIWARE auto-call failed: {e}")
            return {"success": False, "error": str(e)}

    def _map_sensor_type_to_fiware(self, sensor_type: str) -> str:
        mapping = {
            "weather": "Weather",
            "parking": "Parking",
            "traffic": "Traffic",
            "air_quality": "AirQuality",
            "airquality": "AirQuality",
            "room": "Room",
            "temperature": "Room",
            "vehicle": "Vehicle",
            "poi": "POI"
        }
        result = mapping.get(sensor_type.lower(), sensor_type)
        self._log(f"      🔄 Mapped sensor_type '{sensor_type}' → '{result}'")
        return result

    def _quick_weather_check(self) -> Optional[Dict[str, Any]]:
        try:
            self._log("   🌤️ Running quick weather check...")

            result = self.fiware_client.get_weather()

            if result and result.get("success"):
                entities = result.get("entities", [])
                if entities:
                    weather = entities[0]
                    weather_data = {
                        "temperature": weather.get("temperature"),
                        "conditions": self._interpret_weather_conditions(weather),
                        "humidity": weather.get("relativeHumidity"),
                        "wind_speed": weather.get("windSpeed")
                    }
                    self._log(f"   🌤️ Weather: {weather_data['temperature']}°C, {weather_data['conditions']}")
                    return weather_data

            return None

        except Exception as e:
            self._log(f"   ⚠️ Quick weather check failed: {e}")
            return None

    def _interpret_weather_conditions(self, weather: Dict[str, Any]) -> str:
        conditions = []

        temp = weather.get("temperature")
        if temp is not None:
            if temp < 0:
                conditions.append("freezing")
            elif temp < 5:
                conditions.append("cold")
            elif temp < 15:
                conditions.append("cool")
            elif temp < 25:
                conditions.append("mild")
            else:
                conditions.append("warm")

        precipitation = weather.get("precipitation", 0)
        weather_type = weather.get("weatherType", "").lower()

        if precipitation > 0 or "rain" in weather_type:
            conditions.append("rainy")
        elif "snow" in weather_type:
            conditions.append("snowy")
        elif "cloud" in weather_type:
            conditions.append("cloudy")
        else:
            conditions.append("clear")

        wind = weather.get("windSpeed", 0)
        if wind > 10:
            conditions.append("windy")

        return " and ".join(conditions) if conditions else "unknown"

    def _quick_traffic_check(
        self,
        origin_coords: Optional[tuple] = None,
        dest_coords: Optional[tuple] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.tomtom_client:
            self._log("   ⚠️ TomTom client not available for traffic check")
            return None

        try:
            self._log("   🚦 Running traffic check...")

            if origin_coords and dest_coords:
                origin_lat_lon = (origin_coords[1], origin_coords[0])
                dest_lat_lon = (dest_coords[1], dest_coords[0])

                result = self.tomtom_client.check_route_traffic(
                    origin_lat_lon,
                    dest_lat_lon
                )

                if result and result.get("success"):
                    delay = result.get("traffic_delay_minutes", 0)
                    incident_count = result.get("incident_count", 0)
                    recommendation = result.get("recommendation", "clear")

                    if delay > 5:
                        traffic_info = {
                            "status": recommendation,
                            "delay_minutes": delay,
                            "message": result.get("message", "")
                        }

                        route_data = result.get("route", {})
                        if route_data:
                            traffic_info["travel_time"] = route_data.get("travel_time", "")
                            traffic_info["arrival_time"] = route_data.get("arrival_time", "")

                        incidents = result.get("incidents", [])
                        if incidents:
                            traffic_info["incidents_summary"] = []
                            for inc in incidents[:3]:
                                summary = f"{inc.get('type', 'incident')}"
                                if inc.get("from"):
                                    summary += f" near {inc.get('from')}"
                                traffic_info["incidents_summary"].append(summary)

                        self._log(f"   🚦 Traffic: {recommendation} ({delay} min delay)")
                        for inc in incidents[:3]:
                            self._log(f"      - {inc.get('type')}: {inc.get('from', 'unknown location')}")
                    else:
                        traffic_info = {
                            "status": "clear",
                            "delay_minutes": 0,
                            "message": "Traffic is clear."
                        }
                        self._log(f"   🚦 Traffic: clear (no significant delays)")

                    return traffic_info
            else:
                result = self.tomtom_client.get_traffic_flow(52.12, 11.63)
                if result and result.get("success"):
                    return {
                        "status": "clear",
                        "congestion_level": result.get("congestion_level", "light"),
                        "delay_minutes": 0,
                        "incident_count": 0
                    }

            return None

        except Exception as e:
            self._log(f"   ⚠️ Traffic check failed: {e}")
            return None

    def _quick_parking_check(
        self,
        destination_coords: Optional[Tuple[float, float]] = None,
        max_distance_km: float = 0.5
    ) -> Optional[Dict[str, Any]]:
        try:
            self._log("   🅿️ Running quick parking check...")

            result = self.fiware_client.get_parking()

            if not result or not result.get("success"):
                return None

            entities = result.get("entities", [])
            if not entities:
                return None

            nearby_parking = []

            for entity in entities:
                entity_id = entity.get("id", "")
                name = entity.get("name") or entity_id.split(":")[-1] if entity_id else "Unknown"

                location = entity.get("location")
                parking_lat, parking_lon = None, None

                if isinstance(location, str) and "," in location:
                    try:
                        parts = location.split(",")
                        parking_lat = float(parts[0].strip())
                        parking_lon = float(parts[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif isinstance(location, dict):
                    coords = location.get("coordinates", [])
                    if len(coords) >= 2:
                        parking_lon, parking_lat = coords[0], coords[1]

                distance = None
                if destination_coords and parking_lat is not None and parking_lon is not None:
                    dest_lon, dest_lat = destination_coords
                    distance = self._haversine_distance(
                        parking_lat, parking_lon, dest_lat, dest_lon
                    )

                    if distance > max_distance_km:
                        self._log(f"   🅿️ Skipping {name} - too far ({distance:.2f}km)")
                        continue

                available = entity.get("freeSpaces") or entity.get("availableSpotNumber") or 0
                capacity = entity.get("totalSpaces") or entity.get("totalSpotNumber") or 0

                if distance is not None:
                    self._log(f"   🅿️ Found: {name} at {distance:.2f}km ({available}/{capacity} spots)")
                else:
                    self._log(f"   🅿️ Found: {name} ({available}/{capacity} spots)")

                nearby_parking.append({
                    "name": name,
                    "available": available,
                    "capacity": capacity,
                    "distance_km": distance
                })

            if not nearby_parking:
                if destination_coords:
                    self._log("   🅿️ No parking sensors near destination")
                else:
                    self._log("   🅿️ No parking data available")
                return None

            total_available = sum(p["available"] for p in nearby_parking)
            total_capacity = sum(p["capacity"] for p in nearby_parking)

            if destination_coords:
                nearby_parking.sort(key=lambda x: x.get("distance_km") or 999)
            else:
                nearby_parking.sort(key=lambda x: x.get("available", 0), reverse=True)

            return {
                "total_available": total_available,
                "total_capacity": total_capacity,
                "parking_lots": nearby_parking[:5],
                "status": "full" if total_available < 3 else "available",
                "has_nearby_parking": bool(destination_coords),
                "is_filtered_by_location": bool(destination_coords)
            }

        except Exception as e:
            self._log(f"   ⚠️ Quick parking check failed: {e}")
            return None

    def _haversine_distance(
        self,
        lat1: float, lon1: float,
        lat2: float, lon2: float
    ) -> float:
        from math import radians, sin, cos, sqrt, atan2

        R = 6371

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c

    def _create_modified_router_output(
        self,
        original_router_output,
        new_intent: str
    ):
        from copy import deepcopy

        intent_capabilities = {
            "get_parking_info": ["sensor_data_lookup"],
            "get_weather": ["sensor_data_lookup"],
            "find_route": ["graph_location_lookup"],
            "get_route": ["graph_location_lookup"],
            "find_places": ["graph_location_lookup"],
            "get_location_info": ["graph_location_lookup"],
            "get_transit_info": ["graph_location_lookup"]
        }

        modified = deepcopy(original_router_output)

        modified.primary_intent = new_intent

        if new_intent in intent_capabilities:
            modified.required_capabilities = intent_capabilities[new_intent]
        else:
            modified.required_capabilities = ["sensor_data_lookup"]

        self._log(f"   📝 Created modified router: intent={new_intent}, capabilities={modified.required_capabilities}")

        return modified

    def _get_proactive_context(
        self,
        intent: str,
        entities: Dict[str, Any],
        query: str,
        origin_coords: Optional[Tuple[float, float]] = None,
        destination_coords: Optional[Tuple[float, float]] = None
    ) -> Optional[Dict[str, Any]]:
        context = {}

        transport_mode = self._detect_transport_mode(entities, query)

        wants_directions = self._wants_directions(query)

        self._log(f"   🎯 Proactive check: intent={intent}, transport={transport_mode}, directions={wants_directions}")

        if intent in ["find_route", "get_route"]:
            weather = self._quick_weather_check()
            if weather:
                context["weather"] = weather

            if transport_mode == "driving":
                parking = self._quick_parking_check(destination_coords)
                if parking and parking.get("has_nearby_parking"):
                    context["parking"] = parking
                    if parking.get("total_available", 0) < 5:
                        context["parking_suggestion"] = (
                            f"Parking near destination is limited ({parking.get('total_available', 0)} spots). "
                            "Consider public transport."
                        )

                if origin_coords and destination_coords:
                    traffic = self._quick_traffic_check(origin_coords, destination_coords)
                    if traffic:
                        delay = traffic.get("delay_minutes", 0)
                        if delay > 5:
                            context["traffic"] = traffic
                            context["traffic_suggestion"] = (
                                f"Traffic delay of {delay} minutes expected. "
                                "Consider public transport."
                            )
                        else:
                            context["traffic"] = {
                                "status": "clear",
                                "message": "Traffic is clear."
                            }

                if wants_directions and origin_coords and destination_coords:
                    if self.tomtom_client:
                        self._log("   🧭 Fetching driving directions from TomTom...")
                        origin_lat_lon = (origin_coords[1], origin_coords[0])
                        dest_lat_lon = (destination_coords[1], destination_coords[0])
                        directions = self.tomtom_client.get_driving_route_with_directions(
                            origin_lat_lon,
                            dest_lat_lon,
                            max_steps=4
                        )
                        if directions and directions.get("success"):
                            context["directions"] = directions.get("directions_text", [])
                            context["streets_on_route"] = directions.get("streets_on_route", [])
                            self._log(f"   🧭 Got {len(context['directions'])} direction steps")
                    elif self.ors_client:
                        self._log("   🧭 Fetching driving directions from ORS (fallback)...")
                        directions = self.ors_client.get_route_with_directions(
                            origin_coords,
                            destination_coords,
                            profile="driving",
                            max_steps=4
                        )
                        if directions and directions.get("success"):
                            context["directions"] = directions.get("directions_text", [])
                            self._log(f"   🧭 Got {len(context['directions'])} direction steps")

            elif transport_mode in ["walking", "cycling"]:
                if weather:
                    temp = weather.get("temperature")
                    conditions = weather.get("conditions", "")
                    if temp is not None and temp < 0:
                        context["suggestion"] = (
                            f"It's {temp}°C and {conditions}. "
                            "Consider public transport or driving."
                        )

                if wants_directions and origin_coords and destination_coords and self.ors_client:
                    self._log(f"   🧭 Fetching {transport_mode} directions...")
                    directions = self.ors_client.get_route_with_directions(
                        origin_coords,
                        destination_coords,
                        profile=transport_mode,
                        max_steps=4
                    )
                    if directions and directions.get("success"):
                        context["directions"] = directions.get("directions_text", [])
                        context["streets_on_route"] = directions.get("streets_on_route", [])
                        self._log(f"   🛣️ Streets: {', '.join(context['streets_on_route'][:3])}...")

            elif transport_mode is None:
                parking = self._quick_parking_check(destination_coords)
                if parking and parking.get("has_nearby_parking"):
                    context["parking"] = parking

        if self._is_parking_query(query):
            self._log("   🅿️ Detected parking query, fetching real-time data...")

            location_coords = destination_coords
            if not location_coords:
                location_name = entities.get("location") or entities.get("poi_name")
                if location_name:
                    location_coords = self._get_coordinates_for_location(location_name)
                    if location_coords:
                        self._log(f"   📍 Found coords for {location_name}: {location_coords}")

            parking = self._quick_parking_check(location_coords, max_distance_km=1.0)
            if parking:
                context["parking"] = parking
                context["parking_query"] = True
                self._log(f"   🅿️ Found {len(parking.get('parking_lots', []))} parking lots")

        return context if context else None

    def _is_parking_query(self, query: str) -> bool:
        query_lower = query.lower()
        parking_keywords = [
            "parking", "park my car", "where to park", "car park", "parkplatz",
            "can i park", "where can i park", "park near", "park close",
            "park available", "free parking", "parking spot", "parking space"
        ]
        return any(kw in query_lower for kw in parking_keywords)

    def _detect_transport_mode(
        self,
        entities: Dict[str, Any],
        query: str
    ) -> Optional[str]:
        mode = entities.get("transport_mode")
        if mode:
            return mode.lower()

        query_lower = query.lower()

        if any(w in query_lower for w in ["drive", "car", "driving"]):
            return "driving"
        if any(w in query_lower for w in ["walk", "foot", "walking"]):
            return "walking"
        if any(w in query_lower for w in ["bike", "cycle", "cycling", "bicycle"]):
            return "cycling"
        if any(w in query_lower for w in ["tram", "bus", "transit", "public"]):
            return "transit"

        return None

    def _wants_directions(self, query: str) -> bool:
        query_lower = query.lower()

        direction_phrases = [
            "how do i get",
            "how can i get",
            "give me directions",
            "directions to",
            "navigate",
            "guide me",
            "which way",
            "which route",
            "show me the way",
            "take me to",
            "what's the way",
            "what is the way"
        ]

        return any(phrase in query_lower for phrase in direction_phrases)

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "router": self.router_agent.get_metrics(),
            "neo4j": self.neo4j_agent.get_metrics(),
            "fiware": self.fiware_agent.get_metrics(),
            "synthesizer": self.synthesizer_agent.get_metrics()
        }

    def reset_metrics(self) -> None:
        self.router_agent.reset_metrics()
        self.neo4j_agent.reset_metrics()
        self.fiware_agent.reset_metrics()
        self.synthesizer_agent.reset_metrics()


def create_orchestrator(
    llm_client: Any,
    neo4j_graph: Neo4jTransitGraph,
    fiware_client: FIWAREClient,
    ors_client: Optional[ORSClient] = None,
    tomtom_client: Optional[Any] = None,
    verbose: bool = False,
    knowledge_base: Optional[Any] = None
) -> AgentOrchestrator:
    import config

    agent_config = {
        "router_config": {
            "model": config.ROUTER_AGENT_MODEL,
            "timeout": config.ROUTER_AGENT_TIMEOUT,
            "temperature": config.ROUTER_AGENT_TEMPERATURE,
            "max_tokens": config.ROUTER_AGENT_MAX_TOKENS,
            "min_confidence": config.ROUTER_MIN_CONFIDENCE,
            "max_retries": config.AGENT_MAX_RETRIES,
            "retry_delay": config.AGENT_RETRY_DELAY
        },
        "neo4j_config": {
            "model": config.NEO4J_AGENT_MODEL,
            "timeout": config.NEO4J_AGENT_TIMEOUT,
            "temperature": config.NEO4J_AGENT_TEMPERATURE,
            "max_tokens": config.NEO4J_AGENT_MAX_TOKENS,
            "max_retries": config.AGENT_MAX_RETRIES,
            "retry_delay": config.AGENT_RETRY_DELAY
        },
        "fiware_config": {
            "model": config.FIWARE_AGENT_MODEL,
            "timeout": config.FIWARE_AGENT_TIMEOUT,
            "temperature": config.FIWARE_AGENT_TEMPERATURE,
            "max_tokens": config.FIWARE_AGENT_MAX_TOKENS,
            "max_retries": config.AGENT_MAX_RETRIES,
            "retry_delay": config.AGENT_RETRY_DELAY
        },
        "synthesizer_config": {
            "model": config.SYNTHESIZER_AGENT_MODEL,
            "timeout": config.SYNTHESIZER_AGENT_TIMEOUT,
            "temperature": config.SYNTHESIZER_AGENT_TEMPERATURE,
            "max_tokens": config.SYNTHESIZER_AGENT_MAX_TOKENS,
            "max_retries": config.AGENT_MAX_RETRIES,
            "retry_delay": config.AGENT_RETRY_DELAY
        },
        "max_parallel_workers": 3
    }

    return AgentOrchestrator(
        llm_client=llm_client,
        neo4j_graph=neo4j_graph,
        fiware_client=fiware_client,
        ors_client=ors_client,
        tomtom_client=tomtom_client,
        config=agent_config,
        verbose=verbose,
        knowledge_base=knowledge_base
    )


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎯 AGENT ORCHESTRATOR TEST")
    print("="*60)
    print("\nThis orchestrator coordinates all agents:")
    print("  1. RouterAgent - Intent classification")
    print("  2. Neo4jAgent - Location queries")
    print("  3. FIWAREAgent - Sensor data")
    print("  4. SynthesizerAgent - Response generation")
    print("\nUsage:")
    print("  from orchestrator import create_orchestrator")
    print("  orchestrator = create_orchestrator(llm_client, neo4j_graph, fiware_client)")
    print("  response = orchestrator.process_query('What\\'s the weather?')")
    print("\n" + "="*60)
