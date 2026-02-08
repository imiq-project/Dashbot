"""
FIWARE Agent for real-time sensor data queries. Extracts parameters for FIWARE Context Broker and TomTom traffic API calls.
"""

from typing import Dict, Any, Optional
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent, AgentValidationError
from prompts.fiware_prompts import (
    build_fiware_prompt,
    validate_fiware_output,
    FIWARE_ENTITY_TYPES
)


class FIWAREOutput:

    def __init__(self, data: Dict[str, Any]):
        self.entity_type: str = data["entity_type"]
        self.entity_id: Optional[str] = data.get("entity_id")
        self.id_pattern: Optional[str] = data.get("id_pattern")
        self.query_filter: Optional[str] = data.get("query_filter")
        self.attributes: Optional[list[str]] = data.get("attributes")
        self.location_filter: Optional[Dict] = data.get("location_filter")
        self.limit: int = data["limit"]
        self.confidence: float = data["confidence"]
        self.reasoning: str = data.get("reasoning", "")
        self.raw_output: Dict[str, Any] = data

    def to_fiware_params(self) -> Dict[str, Any]:
        params = {
            "entity_type": self.entity_type,
            "limit": self.limit
        }

        if self.entity_id:
            params["entity_id"] = self.entity_id

        if self.id_pattern:
            params["id_pattern"] = self.id_pattern

        if self.query_filter:
            if isinstance(self.query_filter, dict):
                q_parts = []
                for attr, condition in self.query_filter.items():
                    if isinstance(condition, dict):
                        for op, val in condition.items():
                            op_map = {"lt": "<", "gt": ">", "lte": "<=", "gte": ">=", "eq": "==", "$lt": "<", "$gt": ">", "$lte": "<=", "$gte": ">="}
                            op_str = op_map.get(op, "==")
                            q_parts.append(f"{attr}{op_str}{val}")
                    else:
                        q_parts.append(f"{attr}=={condition}")
                params["q"] = ";".join(q_parts) if q_parts else None
            else:
                params["q"] = self.query_filter

        if self.attributes:
            params["attrs"] = self.attributes

        if self.location_filter:
            if isinstance(self.location_filter, dict):
                params.update(self.location_filter)
            elif isinstance(self.location_filter, str):
                if not self.entity_id and not self.id_pattern:
                    params["id_pattern"] = f".*{self.location_filter}.*"

        return params

    def to_dict(self) -> Dict[str, Any]:
        return self.raw_output

    def __repr__(self) -> str:
        return (
            f"FIWAREOutput(entity_type='{self.entity_type}', "
            f"confidence={self.confidence:.2f})"
        )


class FIWAREAgent(BaseAgent[FIWAREOutput]):

    def __init__(
        self,
        client: Any,
        model: str = "qwen2.5-32b-instruct",
        timeout: int = 8,
        max_retries: int = 2,
        retry_delay: float = 0.5,
        temperature: float = 0.1,
        max_tokens: int = 800,
        min_confidence: float = 0.7,
        fiware_client: Optional[Any] = None,
        tomtom_client: Optional[Any] = None,
        verbose: bool = False
    ):
        super().__init__(
            name="FIWAREAgent",
            model=model,
            client=client,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
            temperature=temperature,
            max_tokens=max_tokens,
            verbose=verbose
        )

        self.min_confidence = min_confidence
        self.fiware_client = fiware_client
        self.tomtom_client = tomtom_client

    def _validate_input(self, input_data: Dict[str, Any]) -> None:
        if not isinstance(input_data, dict):
            raise AgentValidationError("Input must be a dictionary")

        if "query" not in input_data:
            raise AgentValidationError("Input must contain 'query' key")

        if "router_output" not in input_data:
            raise AgentValidationError("Input must contain 'router_output' key")

        if not isinstance(input_data["query"], str):
            raise AgentValidationError("Query must be a string")

        if not input_data["query"].strip():
            raise AgentValidationError("Query cannot be empty")

        if not isinstance(input_data["router_output"], dict):
            raise AgentValidationError("router_output must be a dictionary")

    def _execute_internal(self, input_data: Dict[str, Any]) -> str:
        query = input_data["query"]
        router_output = input_data["router_output"]

        self._log(f"Extracting FIWARE parameters for: '{query}'")

        messages = build_fiware_prompt(query, router_output)

        response = self._call_llm(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )

        return response

    def _format_output(self, raw_output: str) -> FIWAREOutput:
        parsed = self._parse_json_response(raw_output)

        is_valid, error_msg = validate_fiware_output(parsed)
        if not is_valid:
            raise AgentValidationError(f"Output validation failed: {error_msg}")

        confidence = parsed.get("confidence", 0.0)
        if confidence < self.min_confidence:
            self._log(
                f"Low confidence: {confidence:.2f} < {self.min_confidence:.2f}"
            )

        output = FIWAREOutput(parsed)

        self._log(f"Entity type: {output.entity_type} (confidence: {confidence:.2f})")

        if output.attributes:
            self._log(f"Attributes: {output.attributes}")
        else:
            self._log(f"Attributes: All (no filter)")

        self._log(f"Limit: {output.limit}")

        if output.reasoning:
            self._log(f"Reasoning: {output.reasoning}")

        return output

    def extract_params(self, query: str, router_output: Dict[str, Any]) -> FIWAREOutput:
        return self.execute({
            "query": query,
            "router_output": router_output
        })

    def query_sensors(
            self,
            query: str,
            router_output: Dict[str, Any],
            override_params: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            if not self.fiware_client:
                raise RuntimeError("FIWARE client not provided. Set fiware_client during initialization.")

            if override_params:
                self._log(f"Using override params from Neo4j: {override_params}")
                entity_id = override_params.get("entity_id")

                if entity_id:
                    self._log(f"Querying FIWARE by exact ID: {entity_id}")
                    results = self.fiware_client.get_entity_by_id(entity_id)

                    if results.get("success"):
                        entity = results.get("entity", {})
                        self._log(f"Retrieved entity: {entity.get('id', 'unknown')}")
                        return {
                            "success": True,
                            "entities": [entity],
                            "count": 1,
                            "returned": 1,
                            "entity_type": entity.get("type", override_params.get("entity_type", "Unknown")),
                            "params": {"entity_id": entity_id}
                        }
                    else:
                        self._log(f"Direct ID lookup failed: {results.get('error')}, trying query_entities...")
                        query_params = override_params
                        results = self.fiware_client.query_entities(**query_params)
                else:
                    query_params = override_params
                    self._log(f"Querying FIWARE with: {query_params}")
                    results = self.fiware_client.query_entities(**query_params)
            else:
                params_output = self.extract_params(query, router_output)
                query_params = params_output.to_fiware_params()
                self._log(f"Querying FIWARE with: {query_params}")
                results = self.fiware_client.query_entities(**query_params)

            if results.get("success"):
                self._log(f"Retrieved {results.get('returned', len(results.get('entities', [])))} entities")
            else:
                self._log(f"FIWARE query failed: {results.get('error')}")

            return results

    def _is_traffic_query(self, query: str, router_output: Dict[str, Any]) -> bool:
        primary_intent = router_output.get("primary_intent", "")
        if primary_intent == "get_traffic_info":
            return True

        query_lower = query.lower()
        traffic_keywords = ["traffic", "congestion", "road conditions", "delays", "commute"]
        return any(keyword in query_lower for keyword in traffic_keywords)

    def _query_tomtom_traffic(
        self,
        origin_coords: Optional[tuple] = None,
        dest_coords: Optional[tuple] = None
    ) -> Dict[str, Any]:
        if not self.tomtom_client:
            self._log("TomTom client not configured, falling back to FIWARE dummy data")
            return {"success": False, "error": "TomTom client not available"}

        try:
            if origin_coords and dest_coords:
                self._log(f"Querying TomTom route traffic: {origin_coords} -> {dest_coords}")
                result = self.tomtom_client.check_route_traffic(origin_coords, dest_coords)
            else:
                self._log("Querying TomTom general traffic flow")
                result = self.tomtom_client.get_traffic_flow(52.1205, 11.6276)

            if result.get("success"):
                self._log(f"TomTom traffic data retrieved")
                return {
                    "success": True,
                    "source": "tomtom",
                    "entities": [result],
                    "count": 1,
                    "returned": 1,
                    "entity_type": "Traffic",
                    "note": "Traffic data from TomTom (will migrate to FIWARE in future)"
                }
            else:
                self._log(f"TomTom query failed: {result.get('error')}")
                return result

        except Exception as e:
            self._log(f"TomTom error: {str(e)}")
            return {"success": False, "error": str(e)}

    def query_realtime_data(
        self,
        query: str,
        router_output: Dict[str, Any],
        override_params: Optional[Dict[str, Any]] = None,
        origin_coords: Optional[tuple] = None,
        dest_coords: Optional[tuple] = None
    ) -> Dict[str, Any]:
        if self._is_traffic_query(query, router_output):
            self._log("Detected traffic query, routing to TomTom")
            return self._query_tomtom_traffic(origin_coords, dest_coords)

        return self.query_sensors(query, router_output, override_params)


def create_fiware_agent(
    client: Any,
    config: Optional[Dict[str, Any]] = None,
    fiware_client: Optional[Any] = None,
    tomtom_client: Optional[Any] = None,
    verbose: bool = False
) -> FIWAREAgent:
    if config is None:
        config = {}

    return FIWAREAgent(
        client=client,
        model=config.get("model", "qwen2.5-32b-instruct"),
        timeout=config.get("timeout", 8),
        max_retries=config.get("max_retries", 2),
        retry_delay=config.get("retry_delay", 0.5),
        temperature=config.get("temperature", 0.1),
        max_tokens=config.get("max_tokens", 800),
        min_confidence=config.get("min_confidence", 0.7),
        fiware_client=fiware_client,
        tomtom_client=tomtom_client,
        verbose=verbose
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m agents.fiware_agent <query>")
        print("\nExamples:")
        print("  python -m agents.fiware_agent \"What's the weather?\"")
        print("  python -m agents.fiware_agent \"Is there parking available?\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    print(f"\nTesting FIWAREAgent with query: '{query}'\n")
    print("=" * 60)
    print("\nNote: This requires a configured OpenAI client and RouterAgent.")
    print("    See the docstring for create_fiware_agent() for usage.\n")
    print("=" * 60)
