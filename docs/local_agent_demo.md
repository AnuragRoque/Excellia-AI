# Stage A proof — same MCP server, two brains, zero code changes

The whole point of Excellia's architecture: one thin MCP server (`excellia-mcp`) that any
AI host can drive. Below is the *same* server, unchanged, driven by a fully offline Ollama
agent. Swap the brain to Claude Desktop and nothing about the server changes.

Captured 2026-07-12 on Windows 11, Python 3.12, Ollama 0.30, model `llama3.2:latest`.

---

## Brain: local Ollama, fully offline

```
$ excellia-agent "Validate examples/messy_vendors.xlsx and tell me the total number of
                  issues and the three most serious ones."

excellia-agent — model llama3.2:latest, 4 tools, fully offline
  -> validate({"sheet": "None", "ruleset": "default", "file_path": "examples/messy_vendors.xlsx"})

The total number of issues in the file 'messy_vendors.xlsx' is 23. The three most serious ones are:

1. Error: Duplicate GST values ('27AAPFU0939F1AV', '27aapfu0939f1zv', and '27AAPFU0939F1Z')
   (Severity: error, Reason: Column 'gstin' is mostly GST values but this one is not)
2. Error: Format PAN values ('AB1234567Z', 'QASBB1514F', and 'YXXJD9900F')
   (Severity: error, Reason: Column 'pan' is mostly PAN values but this one is not)
3. Error: Duplicate row at row 14
   (Severity: warning, Reason: Entire row is an exact duplicate of another row)
```

Every number and row came from a real tool result — the model never inspected the file itself.
No network egress: the `.xlsx`, pandas, scikit-learn, the MCP server, the core API, and the
llama3.2 inference all ran on this machine.

Note the model passed `sheet: "None"` as a literal string — a thing small local models do
constantly for optional parameters. The API boundary coerces the null-sentinel strings
(`"null"`, `"none"`, `""`, `"nan"`) back to a real `None`, so it just works instead of failing
with "Worksheet named 'None' not found".

---

## Brain: Claude Desktop (run this yourself)

`claude_desktop_config.json` → Settings → Developer → Edit Config, then restart:

```json
{
  "mcpServers": {
    "excellia": {
      "command": "excellia-mcp"
    }
  }
}
```

Then in a conversation: *"Profile examples/messy_vendors.xlsx (absolute path) and tell me
what's wrong with it."* The server binary, its four tools, and their behaviour are byte-for-byte
identical to the offline run above. The only difference is where the reasoning happens.

---

## Why the server can start cold

`excellia-mcp` needs the core API (`excellia-api`) reachable on `http://127.0.0.1:8000`. If it
isn't running, the MCP server spawns it as a **detached** process (its own process group, no
inherited console or JSON-RPC pipes) and waits for `/health`. Detaching matters on Windows:
spawned inline as a grandchild inheriting the host's stdio pipes, uvicorn silently fails to
finish binding. So the first tool call after a cold start takes a few seconds (pandas +
scikit-learn import + bind); subsequent calls are instant. You can also run `excellia-api`
yourself in a terminal to keep it warm and watch its logs.
