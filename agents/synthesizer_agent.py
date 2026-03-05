"""
Synthesizer Agent for generating natural language responses. Combines data from specialist agents into user-friendly answers with proactive suggestions.
"""

from typing import Dict, Any, Optional
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent, AgentValidationError
from prompts.synthesizer_prompts import (
    build_synthesizer_prompt,
    validate_synthesizer_output,
    SynthesizerMode
)


class SynthesizerAgent(BaseAgent[str]):

    def __init__(
        self,
        client: Any,
        model: str = "qwen3-30b-a3b-instruct-2507",
        timeout: int = 15,
        max_retries: int = 2,
        retry_delay: float = 0.5,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        verbose: bool = False
    ):
        super().__init__(
            name="SynthesizerAgent",
            model=model,
            client=client,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
            temperature=temperature,
            max_tokens=max_tokens,
            verbose=verbose
        )

    def _validate_input(self, input_data: Dict[str, Any]) -> None:
        if not isinstance(input_data, dict):
            raise AgentValidationError("Input must be a dictionary")

        required = ["query", "router_output", "specialist_results"]
        for field in required:
            if field not in input_data:
                raise AgentValidationError(f"Input must contain '{field}' key")

        if not isinstance(input_data["query"], str):
            raise AgentValidationError("Query must be a string")

        if not input_data["query"].strip():
            raise AgentValidationError("Query cannot be empty")

        if not isinstance(input_data["router_output"], dict):
            raise AgentValidationError("router_output must be a dictionary")

        if not isinstance(input_data["specialist_results"], dict):
            raise AgentValidationError("specialist_results must be a dictionary")

    def _execute_internal(self, input_data: Dict[str, Any]) -> str:
        query = input_data["query"]
        router_output = input_data["router_output"]
        specialist_results = input_data["specialist_results"]
        conversation_context = input_data.get("conversation_context", [])
        mode = input_data.get("mode", SynthesizerMode.STANDARD)
        dialogue_state = input_data.get("dialogue_state")
        proactive_context = input_data.get("proactive_context")

        self._log(f"Generating response for: '{query}'")
        self._log(f"   Mode: {mode.value if hasattr(mode, 'value') else mode}")

        for agent_name, results in specialist_results.items():
            if results:
                success = results.get("success", False) if isinstance(results, dict) else True
                status = "OK" if success else "FAIL"
                self._log(f"{status} {agent_name}: {type(results).__name__}")

        messages = build_synthesizer_prompt(
            query,
            router_output,
            specialist_results,
            conversation_context=conversation_context,
            mode=mode,
            dialogue_state=dialogue_state,
            proactive_context=proactive_context
        )

        response = self._call_llm(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )

        return response

    def _format_output(self, raw_output: str) -> str:
        import re
        response = raw_output.strip()
        response = re.sub(r'<think>.*?</think>\s*', '', response, flags=re.DOTALL).strip()

        is_valid, error_msg = validate_synthesizer_output(response)
        if not is_valid:
            raise AgentValidationError(f"Output validation failed: {error_msg}")

        preview = response[:100] + "..." if len(response) > 100 else response
        self._log(f"Generated response: \"{preview}\"")
        self._log(f"Response length: {len(response)} chars")

        return response

    def synthesize(
        self,
        query: str,
        router_output: Dict[str, Any],
        specialist_results: Dict[str, Any],
        conversation_context: list[dict] = None,
        mode: SynthesizerMode = None,
        dialogue_state: Dict[str, Any] = None,
        proactive_context: Dict[str, Any] = None
    ) -> str:
        input_data = {
            "query": query,
            "router_output": router_output,
            "specialist_results": specialist_results
        }
        if conversation_context:
            input_data["conversation_context"] = conversation_context
        if mode:
            input_data["mode"] = mode
        if dialogue_state:
            input_data["dialogue_state"] = dialogue_state
        if proactive_context:
            input_data["proactive_context"] = proactive_context
        return self.execute(input_data)


def create_synthesizer_agent(
    client: Any,
    config: Optional[Dict[str, Any]] = None,
    verbose: bool = False
) -> SynthesizerAgent:
    if config is None:
        config = {}

    return SynthesizerAgent(
        client=client,
        model=config.get("model", "qwen3-30b-a3b-instruct-2507"),
        timeout=config.get("timeout", 15),
        max_retries=config.get("max_retries", 2),
        retry_delay=config.get("retry_delay", 0.5),
        temperature=config.get("temperature", 0.3),
        max_tokens=config.get("max_tokens", 2000),
        verbose=verbose
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m agents.synthesizer_agent <query>")
        print("\nExamples:")
        print("  python -m agents.synthesizer_agent \"What's the weather?\"")
        print("  python -m agents.synthesizer_agent \"Where is Building 03?\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    print(f"\nTesting SynthesizerAgent with query: '{query}'\n")
    print("=" * 60)
    print("\nNote: This requires specialist results to synthesize.")
    print("    See the docstring for create_synthesizer_agent() for usage.\n")
    print("=" * 60)
