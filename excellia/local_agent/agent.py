"""The air-gapped proof: Ollama as the brain, talking to the same MCP
server Claude Desktop uses, with zero code changes to the server.

This is the only place in Excellia that contains MCP *client* code.
Everything runs on this machine: the model (Ollama), the MCP server
(spawned as a subprocess over stdio), the core API, and the data.

Usage:
    excellia-agent                      # interactive REPL
    excellia-agent check vendors.xlsx   # one-shot prompt, then exit
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
# Models known to support tool calling in Ollama, best first.
PREFERRED = ("qwen3", "qwen2.5", "llama3.1", "llama3.2", "mistral", "granite")
MAX_TOOL_TURNS = 8
TOOL_RESULT_LIMIT = 8000  # chars; local models have small contexts

SYSTEM = (
    "You are Excellia's offline data-quality agent. You inspect and validate "
    "spreadsheets using the provided tools; you never guess file contents. "
    f"The working directory is {os.getcwd()} — resolve relative paths against it. "
    "Row numbers in tool results are Excel rows (header is row 1, data starts at 2); "
    "quote them as-is. If a tool returns an 'error' key, read it, fix your call, and retry. "
    "Answer concisely and only from tool results."
)


def _pick_model() -> str:
    if model := os.environ.get("EXCELLIA_AGENT_MODEL"):
        return model
    try:
        tags = requests.get(f"{OLLAMA}/api/tags", timeout=5).json().get("models", [])
    except requests.RequestException:
        sys.exit(
            f"Ollama is not reachable at {OLLAMA}. Start it (`ollama serve`) or "
            "set OLLAMA_URL, then rerun."
        )
    names = [m["model"] for m in tags]
    for family in PREFERRED:
        for name in names:
            if name.lower().startswith(family):
                return name
    if names:
        return names[0]  # last resort; may lack tool support
    sys.exit("No Ollama models installed. Try: ollama pull qwen2.5:7b")


def _chat(model: str, messages: list[dict], tools: list[dict]) -> dict:
    resp = requests.post(
        f"{OLLAMA}/api/chat",
        json={"model": model, "messages": messages, "tools": tools, "stream": False},
        timeout=600,
    )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("error", resp.text)
        except ValueError:
            detail = resp.text
        if "does not support tools" in str(detail):
            sys.exit(
                f"Model '{model}' cannot call tools. Pull one that can "
                "(e.g. `ollama pull qwen2.5:7b`) or set EXCELLIA_AGENT_MODEL."
            )
        raise RuntimeError(f"Ollama error: {detail}")
    return resp.json()["message"]


async def _run_turn(
    session: ClientSession, model: str, messages: list[dict], tools: list[dict]
) -> str:
    for _ in range(MAX_TOOL_TURNS):
        msg = _chat(model, messages, tools)
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content", "")
        for call in calls:
            name = call["function"]["name"]
            args = call["function"].get("arguments") or {}
            if isinstance(args, str):  # some models return JSON strings
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            print(f"  -> {name}({json.dumps(args, default=str)})", file=sys.stderr)
            result = await session.call_tool(name, args)
            text = "\n".join(b.text for b in result.content if getattr(b, "text", None))
            if len(text) > TOOL_RESULT_LIMIT:
                text = text[:TOOL_RESULT_LIMIT] + "\n...(truncated; ask a narrower question)"
            messages.append({"role": "tool", "content": text, "tool_name": name})
    return "Stopped: too many tool calls in one turn. Ask a narrower question."


async def _amain(prompt: str | None) -> None:
    model = _pick_model()
    server = StdioServerParameters(
        command=sys.executable, args=["-m", "excellia.mcp_server.server"]
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.inputSchema,
                    },
                }
                for t in listed.tools
            ]
            print(
                f"excellia-agent — model {model}, {len(tools)} tools, fully offline",
                file=sys.stderr,
            )
            messages: list[dict] = [{"role": "system", "content": SYSTEM}]
            if prompt is not None:
                messages.append({"role": "user", "content": prompt})
                print(await _run_turn(session, model, messages, tools))
                return
            while True:
                try:
                    user = (await asyncio.to_thread(input, "\nyou> ")).strip()
                except (EOFError, KeyboardInterrupt):
                    return
                if user.lower() in ("exit", "quit"):
                    return
                if not user:
                    continue
                messages.append({"role": "user", "content": user})
                print(await _run_turn(session, model, messages, tools))


def main() -> None:
    args = sys.argv[1:]
    asyncio.run(_amain(" ".join(args) if args else None))


if __name__ == "__main__":
    main()
