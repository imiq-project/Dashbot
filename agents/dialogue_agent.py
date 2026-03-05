"""
LLM-based Dialogue Agent for determining conversation actions. Decides when to ask clarifications, execute queries, or provide follow-up suggestions.
"""

import json
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from prompts.dialogue_prompts import build_dialogue_prompt


class DialogueAction(Enum):
    ASK_TRANSPORT_MODE = "ASK_TRANSPORT_MODE"
    ASK_CUISINE = "ASK_CUISINE"
    ASK_LOCATION = "ASK_LOCATION"
    ASK_PLACE_TYPE = "ASK_PLACE_TYPE"

    EXECUTE_ROUTE = "EXECUTE_ROUTE"
    EXECUTE_WEATHER = "EXECUTE_WEATHER"
    EXECUTE_PARKING = "EXECUTE_PARKING"
    EXECUTE_POI_SEARCH = "EXECUTE_POI_SEARCH"
    EXECUTE_BUILDING_INFO = "EXECUTE_BUILDING_INFO"
    EXECUTE_TRANSIT_INFO = "EXECUTE_TRANSIT_INFO"

    SUGGEST_PARKING = "SUGGEST_PARKING"
    SUGGEST_ALTERNATIVE = "SUGGEST_ALTERNATIVE"

    UNKNOWN = "UNKNOWN"


CLARIFICATION_ACTIONS = {
    DialogueAction.ASK_TRANSPORT_MODE,
    DialogueAction.ASK_CUISINE,
    DialogueAction.ASK_LOCATION,
    DialogueAction.ASK_PLACE_TYPE,
}

EXECUTION_ACTIONS = {
    DialogueAction.EXECUTE_ROUTE,
    DialogueAction.EXECUTE_WEATHER,
    DialogueAction.EXECUTE_PARKING,
    DialogueAction.EXECUTE_POI_SEARCH,
    DialogueAction.EXECUTE_BUILDING_INFO,
    DialogueAction.EXECUTE_TRANSIT_INFO,
    DialogueAction.SUGGEST_PARKING,
    DialogueAction.SUGGEST_ALTERNATIVE,
}


@dataclass
class DialogueAgentOutput:
    action: DialogueAction
    response: str
    state: Dict[str, Any] = field(default_factory=dict)
    choices: Optional[List[str]] = None
    missing_info: Optional[List[str]] = None
    proactive_note: Optional[str] = None
    raw_output: Dict[str, Any] = field(default_factory=dict)

    def should_clarify(self) -> bool:
        return self.action in CLARIFICATION_ACTIONS

    def should_execute(self) -> bool:
        return self.action in EXECUTION_ACTIONS

    def get_execution_intent(self) -> str:
        action_to_intent = {
            DialogueAction.EXECUTE_ROUTE: "find_route",
            DialogueAction.EXECUTE_WEATHER: "get_weather",
            DialogueAction.EXECUTE_PARKING: "get_parking_info",
            DialogueAction.EXECUTE_POI_SEARCH: "find_places",
            DialogueAction.EXECUTE_BUILDING_INFO: "get_location_info",
            DialogueAction.EXECUTE_TRANSIT_INFO: "get_transit_info",
            DialogueAction.SUGGEST_PARKING: "get_parking_info",
            DialogueAction.SUGGEST_ALTERNATIVE: "find_route",
        }
        return action_to_intent.get(self.action, "unknown")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "response": self.response,
            "state": self.state,
            "choices": self.choices,
            "missing_info": self.missing_info,
            "proactive_note": self.proactive_note
        }


class DialogueAgent:

    def __init__(
        self,
        client: Any,
        config: Optional[Dict[str, Any]] = None,
        verbose: bool = False
    ):
        self.client = client
        self.verbose = verbose

        self.model = "meta-llama-3.1-8b-instruct"
        self.temperature = 0.3
        self.max_tokens = 500
        self.timeout = 10
        self.max_retries = 2
        self.retry_delay = 0.5

        if config:
            self.model = config.get("model", self.model)
            self.temperature = config.get("temperature", self.temperature)
            self.max_tokens = config.get("max_tokens", self.max_tokens)
            self.timeout = config.get("timeout", self.timeout)
            self.max_retries = config.get("max_retries", self.max_retries)
            self.retry_delay = config.get("retry_delay", self.retry_delay)

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[DialogueAgent] {message}")

    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        self._log(f"Calling {self.model} (temp={self.temperature})")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout
        )

        content = response.choices[0].message.content
        return content

    def _parse_output(self, raw_output: str) -> DialogueAgentOutput:
        try:
            cleaned = raw_output.strip()

            if "<think>" in cleaned:
                cleaned = cleaned.split("</think>")[-1].strip()

            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                cleaned = cleaned[start_idx:end_idx]

            data = json.loads(cleaned)

            action_str = data.get("action", "UNKNOWN").upper()

            try:
                action = DialogueAction[action_str]
            except KeyError:
                self._log(f"Unknown action: {action_str}, defaulting to UNKNOWN")
                action = DialogueAction.UNKNOWN

            state = data.get("state", {})

            response = data.get("response", "")

            choices = data.get("choices")

            missing_info = data.get("missing_info", [])

            proactive_note = data.get("proactive_note")

            return DialogueAgentOutput(
                action=action,
                response=response,
                state=state,
                choices=choices,
                missing_info=missing_info,
                proactive_note=proactive_note,
                raw_output=data
            )

        except json.JSONDecodeError as e:
            self._log(f"Failed to parse JSON: {e}")
            self._log(f"Raw output: {raw_output[:300]}")

            return DialogueAgentOutput(
                action=DialogueAction.UNKNOWN,
                response="",
                state={},
                raw_output={"error": str(e), "raw": raw_output[:500]}
            )

    def analyze(
        self,
        query: str,
        router_output: Dict[str, Any],
        conversation_context: Optional[List[Dict[str, str]]] = None,
        proactive_context: Optional[Dict[str, Any]] = None,
        gathered_info: Optional[Dict[str, Any]] = None
    ) -> DialogueAgentOutput:
        self._log(f"Analyzing: '{query}'")

        messages = build_dialogue_prompt(
            query=query,
            router_output=router_output,
            conversation_context=conversation_context,
            proactive_context=proactive_context,
            gathered_info=gathered_info
        )

        start_time = time.time()
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._call_llm(messages)
                duration = time.time() - start_time
                self._log(f"Response in {duration:.2f}s")

                output = self._parse_output(response)

                self._log(f"Action: {output.action.value}")
                if output.should_clarify():
                    self._log(f"Question: {output.response}")
                    self._log(f"Missing info: {output.missing_info}")
                else:
                    self._log(f"Executing: {output.get_execution_intent()}")

                return output

            except Exception as e:
                last_error = e
                self._log(f"Attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)

        self._log(f"All retries failed: {last_error}")
        return DialogueAgentOutput(
            action=DialogueAction.UNKNOWN,
            response="",
            state={},
            raw_output={"error": str(last_error)}
        )


def create_dialogue_agent(
    client: Any,
    config: Optional[Dict[str, Any]] = None,
    verbose: bool = False
) -> DialogueAgent:
    return DialogueAgent(client=client, config=config, verbose=verbose)
