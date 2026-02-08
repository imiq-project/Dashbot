"""
Dialogue Manager for multi-turn conversation flow. Tracks conversation state, handles clarification questions, and manages proactive information delivery.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, TYPE_CHECKING
import time

if TYPE_CHECKING:
    from orchestrator import AgentOrchestrator


class ResponseType(Enum):
    ANSWER = "answer"
    SUGGESTION = "suggestion"


@dataclass
class DialogueState:
    last_destination: Optional[str] = None
    last_transport_mode: Optional[str] = None
    last_updated: float = field(default_factory=time.time)

    def is_stale(self, max_age: float = 300) -> bool:
        return (time.time() - self.last_updated) > max_age


@dataclass
class ProactiveContext:
    weather: Optional[Dict[str, Any]] = None
    parking: Optional[Dict[str, Any]] = None
    traffic: Optional[Dict[str, Any]] = None
    suggestions: List[str] = field(default_factory=list)

    def has_issues(self) -> bool:
        if self.parking and self.parking.get("total_available", 0) < 3:
            return True
        if self.weather:
            temp = self.weather.get("temperature")
            if temp is not None and (temp < 0 or temp > 35):
                return True
            conditions = self.weather.get("conditions", "")
            if any(w in conditions.lower() for w in ["rain", "snow", "storm"]):
                return True
        return False


class DialogueManager:

    MAX_SESSIONS = 1000
    SESSION_MAX_AGE = 3600  # 1 hour

    def __init__(
        self,
        orchestrator: "AgentOrchestrator",
        verbose: bool = False
    ):
        self.orchestrator = orchestrator
        self.verbose = verbose
        self.states: Dict[str, DialogueState] = {}

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[PROACTIVE] {message}")

    def _cleanup_stale_sessions(self) -> None:
        """Remove sessions that have been inactive for longer than SESSION_MAX_AGE."""
        if len(self.states) <= self.MAX_SESSIONS:
            return
        stale_ids = [
            sid for sid, state in self.states.items()
            if state.is_stale(max_age=self.SESSION_MAX_AGE)
        ]
        for sid in stale_ids:
            del self.states[sid]
        if stale_ids:
            self._log(f"Cleaned up {len(stale_ids)} stale sessions")

    def get_or_create_state(self, session_id: str) -> DialogueState:
        self._cleanup_stale_sessions()
        if session_id not in self.states:
            self.states[session_id] = DialogueState()
        return self.states[session_id]

    def get_proactive_context(
        self,
        intent: str,
        entities: Dict[str, Any],
        session_id: str
    ) -> ProactiveContext:
        state = self.get_or_create_state(session_id)
        context = ProactiveContext()

        transport_mode = self._extract_transport_mode(entities)
        destination = entities.get("destination") or entities.get("location")

        if destination:
            state.last_destination = destination
        if transport_mode:
            state.last_transport_mode = transport_mode
        state.last_updated = time.time()

        self._log(f"Intent: {intent}, Transport: {transport_mode}, Dest: {destination}")

        if intent in ["find_route", "get_route"]:
            context.weather = self._fetch_weather()

            if transport_mode == "driving":
                context.parking = self._fetch_parking()
                self._log("Fetching parking for driving route")

            elif transport_mode in ["walking", "cycling"]:
                self._log("Weather context for walking/cycling")

            else:
                context.parking = self._fetch_parking()
                self._log("No transport mode - fetching all context")

        elif intent == "get_parking_info":
            context.parking = self._fetch_parking()
            self._log("Direct parking query")

        elif intent == "get_weather":
            context.weather = self._fetch_weather()

        context.suggestions = self._generate_suggestions(context, transport_mode)

        return context

    def _extract_transport_mode(self, entities: Dict[str, Any]) -> Optional[str]:
        mode = entities.get("transport_mode")
        if mode:
            return mode.lower()

        all_text = " ".join(str(v) for v in entities.values() if v).lower()

        if any(w in all_text for w in ["drive", "car", "driving"]):
            return "driving"
        if any(w in all_text for w in ["walk", "foot", "walking"]):
            return "walking"
        if any(w in all_text for w in ["bike", "cycle", "cycling", "bicycle"]):
            return "cycling"
        if any(w in all_text for w in ["tram", "bus", "transit", "public"]):
            return "transit"

        return None

    def _fetch_weather(self) -> Optional[Dict[str, Any]]:
        try:
            return self.orchestrator._quick_weather_check()
        except Exception as e:
            self._log(f"Weather fetch failed: {e}")
            return None

    def _fetch_parking(self) -> Optional[Dict[str, Any]]:
        try:
            return self.orchestrator._quick_parking_check()
        except Exception as e:
            self._log(f"Parking fetch failed: {e}")
            return None

    def _generate_suggestions(
        self,
        context: ProactiveContext,
        transport_mode: Optional[str]
    ) -> List[str]:
        suggestions = []

        if context.parking:
            available = context.parking.get("total_available", 0)
            if available < 3:
                suggestions.append(
                    f"Parking is very limited ({available} spots). "
                    "Consider public transport instead."
                )
            elif available < 10:
                suggestions.append(
                    f"Parking availability is moderate ({available} spots)."
                )

        if context.weather:
            temp = context.weather.get("temperature")
            conditions = context.weather.get("conditions", "")

            if temp is not None:
                if temp < -5:
                    suggestions.append(
                        f"It's very cold ({temp}C). Consider driving or public transport."
                    )
                elif temp < 0:
                    if transport_mode in ["walking", "cycling"]:
                        suggestions.append(
                            f"It's freezing ({temp}C). Dress warmly or consider alternatives."
                        )

            if "rain" in conditions.lower() or "snow" in conditions.lower():
                if transport_mode in ["walking", "cycling"]:
                    suggestions.append(
                        f"Weather is {conditions}. Public transport might be better."
                    )

        return suggestions

    def format_proactive_info(self, context: ProactiveContext) -> str:
        parts = []

        if context.weather:
            temp = context.weather.get("temperature")
            cond = context.weather.get("conditions", "")
            if temp is not None:
                parts.append(f"Current weather: {temp}C, {cond}")

        if context.parking:
            available = context.parking.get("total_available", 0)
            parts.append(f"Parking: {available} spots available")

        if context.suggestions:
            parts.extend(context.suggestions)

        return " | ".join(parts) if parts else ""


class DialoguePhase(Enum):
    GATHERING_INFO = "gathering_info"
    READY_TO_EXECUTE = "ready_to_execute"
    AWAITING_CHOICE = "awaiting_choice"


@dataclass
class DialogueResponse:
    text: str
    response_type: ResponseType = ResponseType.ANSWER
    choices: Optional[List[str]] = None
    proactive_info: Optional[Dict[str, Any]] = None
    should_execute: bool = True
    execution_params: Optional[Dict[str, Any]] = None
