"""
Single-agent factory for the Magdeburg Campus Assistant.

One GPT-5.4 ReAct agent owns the full tool surface (Neo4j + FIWARE +
Routing + Context). The model's native tool-calling loop handles routing,
parallel fan-out, and answer composition in a single conversation —
replacing what used to be a supervisor + 4 specialist agents + synthesis.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from config import (
    AGENT_TIMEOUT,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    SINGLE_AGENT_MODEL,
)
from graph.system_prompt import get_system_prompt

logger = logging.getLogger(__name__)


def build_single_agent(tools: Any):
    """Build the single gpt-5.4 ReAct agent on the given MCP tools.

    Tools come from the MCP servers (graph/mcp_client.py). This is the ONLY
    tool path — there is no in-process fallback.

    Returns (agent, tool_names). tool_names is for startup diagnostics.
    """
    all_tools = list(tools)
    tool_names = [getattr(t, "name", "?") for t in all_tools]
    print(f"[SINGLE AGENT] Using {len(all_tools)} MCP tools: {tool_names}")

    llm = ChatOpenAI(
        base_url=OPENAI_BASE_URL,
        api_key=OPENAI_API_KEY,
        model=SINGLE_AGENT_MODEL,
        temperature=0.0,
        streaming=True,
    )

    prompt = get_system_prompt()
    print(f"[SINGLE AGENT] System prompt ready ({len(prompt)} chars)")

    agent = create_react_agent(llm, all_tools, prompt=prompt)
    return agent, tool_names


def _format_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history[-6:]:
        role = (turn.get("role") or "user").upper()
        content = turn.get("content") or ""
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _format_location(user_location: Any) -> str:
    if not isinstance(user_location, dict):
        return ""
    lat = user_location.get("lat") or user_location.get("latitude")
    lon = user_location.get("lon") or user_location.get("longitude")
    if lat is None or lon is None:
        return ""
    return f"User's current location: latitude={lat}, longitude={lon}"


def _count_tool_calls(messages: list) -> int:
    n = 0
    for m in messages:
        tc = getattr(m, "tool_calls", None)
        if tc:
            n += len(tc)
    return n


def create_single_agent_node(agent):
    """Create a LangGraph node that invokes the single agent.

    Reads query / conversation_history / user_location from state; runs
    the agent with a wall-clock timeout; writes response and
    final_response back. The legacy `agent_results` field is left empty
    — downstream code (api.py card extractor) degrades gracefully.
    """

    async def single_agent_node(state: dict) -> dict:
        query = (state.get("query") or "").strip()
        conversation_history = state.get("conversation_history") or []
        user_location = state.get("user_location")

        parts: list[str] = []
        history_text = _format_history(conversation_history)
        if history_text:
            parts.append(f"Recent conversation:\n{history_text}")
        location_text = _format_location(user_location)
        if location_text:
            parts.append(location_text)
        proactive_context = (state.get("proactive_context") or "").strip()
        if proactive_context:
            parts.append(proactive_context)
        parts.append(f"Question: {query}")
        user_msg = "\n\n".join(parts)

        print(f"[SINGLE AGENT] Processing: {query!r}")

        try:
            result = await asyncio.wait_for(
                agent.ainvoke({"messages": [HumanMessage(content=user_msg)]}),
                timeout=AGENT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            print(f"[SINGLE AGENT] Timeout after {AGENT_TIMEOUT}s")
            msg = "Sorry, that took longer than expected to look up. Please try again."
            return {"response": msg, "final_response": msg}
        except Exception as e:
            logger.error(f"Single agent failed: {e}", exc_info=True)
            print(f"[SINGLE AGENT] Error: {e}")
            msg = "Sorry, I ran into an internal error answering that. Please try again."
            return {"response": msg, "final_response": msg}

        msgs = result.get("messages") or []

        # Diagnostic: print every tool call (with args) and every tool
        # result (truncated). Helps catch cases where the LLM misreads a
        # successful tool result as a failure, or calls the wrong tool.
        for i, m in enumerate(msgs):
            cls = type(m).__name__
            tcs = getattr(m, "tool_calls", None)
            if tcs:
                for tc in tcs:
                    args_preview = str(tc.get("args", {}))[:300]
                    print(f"[SINGLE AGENT]   step {i} {cls} -> {tc.get('name')}({args_preview})")
            elif cls == "ToolMessage":
                content = getattr(m, "content", "") or ""
                preview = (content[:400] + "...") if len(content) > 400 else content
                print(f"[SINGLE AGENT]   step {i} ToolMessage <- {preview}")

        final = ""
        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                content = (m.content or "").strip()
                if content:
                    final = content
                    break

        if not final:
            final = "Sorry, I couldn't put together an answer for that one."

        n_tool_calls = _count_tool_calls(msgs)
        print(
            f"[SINGLE AGENT] Done — {n_tool_calls} tool call(s), "
            f"{len(final)} char answer"
        )

        return {
            "response": final,
            "final_response": final,
            "messages": msgs,
        }

    return single_agent_node
