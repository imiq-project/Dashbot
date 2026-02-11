"""
Neo4j Agent for mapping user queries to Neo4j graph database functions. Determines which graph function to call and extracts parameters.
"""

from typing import Dict, Any, Optional
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent, AgentValidationError
from prompts.neo4j_prompts import (
    build_neo4j_prompt,
    validate_neo4j_output,
    NEO4J_FUNCTIONS
)


class Neo4jOutput:

    def __init__(self, data: Dict[str, Any]):
        self.function_name: str = data["function_name"]
        self.parameters: Dict[str, Any] = data["parameters"]
        self.confidence: float = data["confidence"]
        self.reasoning: str = data.get("reasoning", "")
        self.raw_output: Dict[str, Any] = data

    def get_parameter(self, key: str, default: Any = None) -> Any:
        return self.parameters.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return self.raw_output

    def __repr__(self) -> str:
        return (
            f"Neo4jOutput(function='{self.function_name}', "
            f"confidence={self.confidence:.2f})"
        )


class Neo4jAgent(BaseAgent[Neo4jOutput]):

    def __init__(
        self,
        client: Any,
        model: str = "qwen3-30b-a3b-instruct-2507",
        timeout: int = 10,
        max_retries: int = 2,
        retry_delay: float = 0.5,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        min_confidence: float = 0.7,
        verbose: bool = False
    ):
        super().__init__(
            name="Neo4jAgent",
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
        conversation_context = input_data.get("conversation_context", [])

        self._log(f"Mapping query to Neo4j function: '{query}'")

        try:
            self._log(f"DEBUG: Building prompt...")
            messages = build_neo4j_prompt(
                query,
                router_output,
                conversation_context=conversation_context
            )
            self._log(f"DEBUG: Prompt built successfully, {len(messages)} messages")
        except Exception as e:
            self._log(f"DEBUG: Prompt building failed: {type(e).__name__}: {str(e)}")
            raise

        self._log(f"DEBUG: Calling LLM...")
        response = self._call_llm(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )

        self._log(f"DEBUG: LLM call completed")
        return response

    def _format_output(self, raw_output: str) -> Neo4jOutput:
        self._log(f"DEBUG: raw_output type = {type(raw_output)}")
        self._log(f"DEBUG: raw_output content (first 200): {str(raw_output)[:200]}")

        parsed = self._parse_json_response(raw_output)

        is_valid, error_msg = validate_neo4j_output(parsed)
        if not is_valid:
            raise AgentValidationError(f"Output validation failed: {error_msg}")

        confidence = parsed.get("confidence", 0.0)
        if confidence < self.min_confidence:
            self._log(
                f"Low confidence: {confidence:.2f} < {self.min_confidence:.2f}"
            )

        output = Neo4jOutput(parsed)

        self._log(f"Selected function: {output.function_name} (confidence: {confidence:.2f})")
        self._log(f"Parameters: {output.parameters}")

        if output.reasoning:
            self._log(f"Reasoning: {output.reasoning}")

        return output

    def map_query(
        self,
        query: str,
        router_output: Dict[str, Any],
        conversation_context: list[dict] = None
    ) -> Neo4jOutput:
        input_data = {
            "query": query,
            "router_output": router_output
        }
        if conversation_context:
            input_data["conversation_context"] = conversation_context
        return self.execute(input_data)


def create_neo4j_agent(
    client: Any,
    config: Optional[Dict[str, Any]] = None,
    verbose: bool = False
) -> Neo4jAgent:
    if config is None:
        config = {}

    return Neo4jAgent(
        client=client,
        model=config.get("model", "qwen3-30b-a3b-instruct-2507"),
        timeout=config.get("timeout", 10),
        max_retries=config.get("max_retries", 2),
        retry_delay=config.get("retry_delay", 0.5),
        temperature=config.get("temperature", 0.0),
        max_tokens=config.get("max_tokens", 1000),
        min_confidence=config.get("min_confidence", 0.7),
        verbose=verbose
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m agents.neo4j_agent <query>")
        print("\nExamples:")
        print("  python -m agents.neo4j_agent \"Where is Building 03?\"")
        print("  python -m agents.neo4j_agent \"Find cafes near the library\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    print(f"\nTesting Neo4jAgent with query: '{query}'\n")
    print("=" * 60)
    print("\nNote: This requires a configured OpenAI client and RouterAgent.")
    print("    See the docstring for create_neo4j_agent() for usage.\n")
    print("=" * 60)
