"""
Router Agent for intent classification and query parsing. Uses LLM to analyze queries and output structured plans with intents, entities, and required capabilities.
"""

from typing import Dict, Any, Optional
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent, AgentValidationError
from prompts.router_prompts import (
    build_router_prompt,
    validate_router_output,
    ROUTER_OUTPUT_SCHEMA
)


class RouterOutput:

    def __init__(self, data: Dict[str, Any]):
        self.primary_intent: str = data["primary_intent"]
        self.sub_intents: list[str] = data["sub_intents"]
        self.entities: Dict[str, Optional[str]] = data["entities"]
        self.required_capabilities: list[str] = data["required_capabilities"]
        self.execution_strategy: str = data["execution_strategy"]
        self.confidence: float = data["confidence"]
        self.is_compound: bool = data["is_compound"]
        self.clarification_question: Optional[str] = data.get("clarification_question")
        self.raw_output: Dict[str, Any] = data

    def needs_clarification(self) -> bool:
        return self.primary_intent == "clarification_needed"

    def get_entity(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.entities.get(key, default)

    def has_capability(self, capability: str) -> bool:
        return capability in self.required_capabilities

    def should_run_parallel(self) -> bool:
        return self.execution_strategy == "parallel"

    def to_dict(self) -> Dict[str, Any]:
        return self.raw_output

    def __repr__(self) -> str:
        return (
            f"RouterOutput(primary_intent='{self.primary_intent}', "
            f"confidence={self.confidence:.2f}, "
            f"is_compound={self.is_compound})"
        )


class RouterAgent(BaseAgent[RouterOutput]):

    def __init__(
        self,
        client: Any,
        model: str = "qwen3-30b-a3b-instruct-2507",
        timeout: int = 5,
        max_retries: int = 2,
        retry_delay: float = 0.5,
        temperature: float = 0.1,
        max_tokens: int = 500,
        min_confidence: float = 0.7,
        include_examples: bool = True,
        verbose: bool = False
    ):
        super().__init__(
            name="RouterAgent",
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
        self.include_examples = include_examples

    def _validate_input(self, input_data: Dict[str, Any]) -> None:
        if not isinstance(input_data, dict):
            raise AgentValidationError("Input must be a dictionary")

        if "query" not in input_data:
            raise AgentValidationError("Input must contain 'query' key")

        query = input_data["query"]

        if not isinstance(query, str):
            raise AgentValidationError("Query must be a string")

        if not query.strip():
            raise AgentValidationError("Query cannot be empty")

        if len(query) > 500:
            raise AgentValidationError(
                f"Query too long ({len(query)} chars, max 500)"
            )

    def _execute_internal(self, input_data: Dict[str, Any]) -> str:
        query = input_data["query"]
        conversation_context = input_data.get("conversation_context", [])

        self._log(f"Parsing query: '{query}'")

        messages = build_router_prompt(
            user_query=query,
            include_examples=self.include_examples,
            conversation_context=conversation_context
        )

        response = self._call_llm(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )

        return response

    def _format_output(self, raw_output: str) -> RouterOutput:
        parsed = self._parse_json_response(raw_output)

        is_valid, error_msg = validate_router_output(parsed)
        if not is_valid:
            raise AgentValidationError(f"Output validation failed: {error_msg}")

        confidence = parsed.get("confidence", 0.0)
        if confidence < self.min_confidence:
            self._log(
                f"Low confidence: {confidence:.2f} < {self.min_confidence:.2f}"
            )

            if parsed["primary_intent"] != "clarification_needed":
                if not parsed.get("clarification_question"):
                    parsed["clarification_question"] = (
                        "I'm not entirely sure I understood correctly. "
                        "Could you rephrase your question?"
                    )

        output = RouterOutput(parsed)

        self._log(f"Parsed intent: {output.primary_intent} (confidence: {confidence:.2f})")

        if output.is_compound:
            self._log(f"Compound query with sub-intents: {output.sub_intents}")

        if output.required_capabilities:
            self._log(f"Required capabilities: {output.required_capabilities}")

        if output.entities:
            non_null_entities = {
                k: v for k, v in output.entities.items()
                if v is not None
            }
            if non_null_entities:
                self._log(f"Extracted entities: {non_null_entities}")

        return output

    def parse_query(
        self,
        query: str,
        conversation_context: list[dict] = None
    ) -> RouterOutput:
        input_data = {"query": query}
        if conversation_context:
            input_data["conversation_context"] = conversation_context
        return self.execute(input_data)


def create_router_agent(
    client: Any,
    config: Optional[Dict[str, Any]] = None,
    verbose: bool = False
) -> RouterAgent:
    if config is None:
        config = {}

    return RouterAgent(
        client=client,
        model=config.get("model", "qwen3-30b-a3b-instruct-2507"),
        timeout=config.get("timeout", 5),
        max_retries=config.get("max_retries", 2),
        retry_delay=config.get("retry_delay", 0.5),
        temperature=config.get("temperature", 0.1),
        max_tokens=config.get("max_tokens", 500),
        min_confidence=config.get("min_confidence", 0.7),
        include_examples=config.get("include_examples", True),
        verbose=verbose
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m agents.router_agent <query>")
        print("\nExamples:")
        print("  python -m agents.router_agent \"What's the weather?\"")
        print("  python -m agents.router_agent \"How do I get to Building 03?\"")
        print("  python -m agents.router_agent \"Weather and route to mensa\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    print(f"\nTesting RouterAgent with query: '{query}'\n")
    print("=" * 60)
    print("\nNote: This requires a configured OpenAI client.")
    print("    See the docstring for create_router_agent() for usage.\n")
    print("=" * 60)
