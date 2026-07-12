"""The air-gapped proof: Ollama as the brain, talking to the same MCP
server Claude Desktop uses, with zero code changes to the server.

Phase 2 builds this (~60 lines): mcp client over stdio + a local
Ollama model deciding which tools to call. Zero network calls.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("Phase 2: Ollama + mcp client, fully offline")


if __name__ == "__main__":
    main()
