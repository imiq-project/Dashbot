"""
MCP client wiring for the single-agent Magdeburg Assistant.

Launches the four FastMCP stdio servers under `mcp_servers/` and exposes their
tools as LangChain `BaseTool`s, bound to PERSISTENT sessions — one long-lived
subprocess per server — so we never pay the subprocess-spawn + heavy-import cost
on every tool call (which is what `MultiServerMCPClient.get_tools()` does by
default: "a new session will be created for each tool call").

Lifecycle: the caller owns an `AsyncExitStack` whose lifetime == the app's. We
enter one `client.session(name)` per server into that stack and load the tools
bound to the live session. Closing the stack tears the subprocesses down.
"""

from __future__ import annotations

import os
import sys
from contextlib import AsyncExitStack

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# server name -> module file under mcp_servers/
_SERVERS = {
    "neo4j": "neo4j_server.py",
    "fiware": "fiware_server.py",
    "routing": "routing_server.py",
    "context": "context_server.py",
}


def build_connections(python_exe: str | None = None) -> dict[str, dict]:
    """Build the MultiServerMCPClient connection map for the 4 stdio servers."""
    py = python_exe or sys.executable
    conns: dict[str, dict] = {}
    for name, fname in _SERVERS.items():
        conns[name] = {
            "transport": "stdio",
            "command": py,
            "args": [os.path.join(_PROJECT_ROOT, "mcp_servers", fname)],
            "cwd": _PROJECT_ROOT,
            "env": dict(os.environ),   # propagate PATH + .env-derived vars
            "encoding": "utf-8",       # servers emit unicode (→, ß); avoid cp1252
        }
    return conns


async def open_mcp_tools(
    exit_stack: AsyncExitStack,
    python_exe: str | None = None,
) -> tuple[list[BaseTool], dict[str, list[str]]]:
    """Open ONE persistent session per server (entered into `exit_stack`) and
    return (combined_tools, per_server_tool_names). Sessions stay alive until
    the stack is closed by the caller.
    """
    client = MultiServerMCPClient(build_connections(python_exe))
    tools: list[BaseTool] = []
    per_server: dict[str, list[str]] = {}
    for name in _SERVERS:
        session = await exit_stack.enter_async_context(client.session(name))
        server_tools = await load_mcp_tools(session)
        per_server[name] = [t.name for t in server_tools]
        tools.extend(server_tools)
    print(f"[MCP] persistent sessions up; tools per server: {per_server}")
    return tools, per_server


if __name__ == "__main__":
    import asyncio

    async def _selftest() -> None:
        async with AsyncExitStack() as stack:
            tools, per_server = await open_mcp_tools(stack)
            print(f"[MCP] total {len(tools)} tools loaded across {len(per_server)} servers")
            for name, names in per_server.items():
                print(f"  {name}: {names}")
            # sanity: invoke one cheap read tool through the live session
            by_name = {t.name: t for t in tools}
            if "list_entity_types" in by_name:
                out = await by_name["list_entity_types"].ainvoke({})
                print("\n[MCP] sample list_entity_types() call ->", str(out)[:300])

    asyncio.run(_selftest())
