# Offline agent — `excellia/local_agent/`

The privacy proof. Our own air-gapped MCP host: a local **Ollama** model picks the tools, the
bundled MCP client calls the same unchanged `excellia-mcp` server, and **zero bytes leave the
machine** — data, computation, *and* reasoning are all local.

This is the door for regulated environments where even tool results (counts, flagged rows,
reasons) must not reach a cloud host.

## Prerequisites

[Ollama](https://ollama.com) running, with a **tool-capable** model:

```bash
ollama pull qwen2.5:7b        # the recommended, verified-class model
```

## Run

```bash
excellia-agent                                     # interactive REPL
excellia-agent check examples/messy_vendors.xlsx   # one-shot file check
```

The agent connects to `excellia-mcp` over stdio (which auto-starts the core API), converts the
tool schemas to Ollama's function-calling format, and loops: your prompt → model → tool
call(s) → results → answer.

## Configuration

| Env var | Meaning | Default |
|---|---|---|
| `EXCELLIA_AGENT_MODEL` | Pin a specific model | auto-picks an installed tool-capable model |
| `OLLAMA_URL` | Non-default Ollama location | `http://127.0.0.1:11434` |

If the picked model can't call tools, the agent says so and names the fix (pull `qwen2.5:7b`) —
it never fails silently.

## Why it exists

The whole thesis is that the same MCP server serves two brains: Claude Desktop for convenience,
this agent for air-gapped deployments — with zero code changes in between. A demo transcript of
exactly that lives in [docs/local_agent_demo.md](../../docs/local_agent_demo.md).

This is also the **only MCP-client code in the repo** — hosts are products other people build;
ours exists only to prove the offline path works.
