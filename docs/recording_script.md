# Recording scripts — the two demo videos

Two recordings, per the shipping plan: a **90-second Claude Desktop demo** (the hook) and a
**30-second fully-offline agent demo** (the differentiator). Record the screen with your voice
over it. Scripts below give the exact actions, the exact things to type, and the exact words to
say — timed so you never have to improvise.

**General tips**

- 125% Windows display scaling or larger — terminal and Claude text must be readable on a phone.
- Practice each run once before recording; the LLM steps have variable latency, so record the
  *second* take where you know what's coming. It's fine to cut dead air while a tool runs.
- Speak slightly slower than feels natural. The scripts are ~120 words/min.
- Keep the demo file path short on screen: copy `examples/messy_vendors.xlsx` to `C:\demo\vendors.xlsx`.

---

## Video 1 — "Claude cleans a spreadsheet without ever seeing it" (~90s)

### Prep (before recording)

1. `excellia-mcp` registered in `claude_desktop_config.json` (absolute venv path), Claude
   Desktop fully restarted, tools visible (hammer icon → 19 excellia tools).
2. `C:\demo\vendors.xlsx` in place (the seeded-errors demo file).
3. Close every other window. Claude Desktop maximised. A fresh conversation.
4. Optional second window (for the closing shot): File Explorer open at `C:\demo\`.

### Shot list & narration

**0:00–0:10 — cold open on Claude Desktop, empty chat.**

> "This is Claude Desktop. And this is a messy vendor spreadsheet on my disk — duplicate IDs,
> broken GST numbers, missing values. Claude is about to find every one of those problems
> **without the file ever leaving my machine**."

**0:10–0:25 — type the first prompt, hit enter.**

Type:

```
Profile C:\demo\vendors.xlsx and tell me what's wrong with it.
```

> "Excellia is a local MCP server. Claude doesn't get the file — it gets *tools*. Watch it pick
> one."

**0:25–0:45 — the tool call runs; expand the tool-call block when it appears.**

> "The profile ran on my machine, in pure Python. What went to the cloud? My prompt, the file
> *path*, and this summary — counts, types, null rates. Not one row of data."

(Pause narration; let the viewer read Claude's summary for ~3 seconds.)

**0:45–1:05 — second prompt: validation.**

Type:

```
Validate it with the kyc ruleset and show me the worst problems with their row numbers.
```

> "Now real validation — deterministic rules, not AI guesses. PAN formats, GST checksums,
> duplicates. Every issue comes back with its Excel row number and a reason a human can act on."

**1:05–1:20 — third prompt: the fix.**

Type:

```
Clean it up: trim whitespace, fix the casing, and save it as a new file. Preview first.
```

> "For changes, Excellia never lets the AI touch data silently — it proposes a recipe, shows a
> before-and-after preview, and only applies to a **new** file when I confirm."

**1:20–1:30 — closing. Optionally flip to File Explorer showing the new cleaned file.**

> "One pip install, one config block. And if even the *summaries* are too sensitive for the
> cloud — the next video runs the exact same server with no internet at all."

---

## Video 2 — "The same server, fully offline" (~30s)

### Prep

1. Ollama running, `qwen2.5:7b` pulled.
2. Terminal (readable font size, dark theme), venv activated, in the repo directory.
3. **The airplane-mode proof is the whole video:** turn Wi-Fi off *on camera* if you can — it's
   the strongest 3 seconds. (Everything works offline; Ollama and the API are localhost.)

### Shot list & narration

**0:00–0:05 — click the network icon, turn Wi-Fi OFF.**

> "Same spreadsheet. Same Excellia server. But now — no internet."

**0:05–0:20 — run the one-shot check.**

Type:

```
excellia-agent check C:\demo\vendors.xlsx
```

> "This is a local Llama-class model, running in Ollama, driving the **same unchanged MCP
> server** through the same tools. Data, computation, and now the reasoning too — all on this
> machine."

**0:20–0:30 — results scroll; end on the issue summary.**

> "Cloud brain for convenience. Local brain for regulated work. Zero code changes in between —
> that's the point of building on MCP. Excellia — pip install, and nothing leaves your machine."

---

## After recording

- Trim tool-latency dead air; keep total lengths ≤ 95s and ≤ 35s.
- Captions on (many viewers watch muted) — the narration text above is the caption file.
- Thumbnail suggestion: split frame — Claude Desktop left, the Wi-Fi-off toast right, title
  "AI cleaned this file. It never saw it."
