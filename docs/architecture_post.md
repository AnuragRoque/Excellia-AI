# Why enterprise AI logic should be an MCP server, not an app

*The architecture post behind [Excellia](../README.md) — an air-gapped spreadsheet intelligence
engine. Draft for publishing; ~1,100 words.*

---

Every enterprise AI tool I've seen this year is an app. A chat window bolted onto a domain, a
subscription, a place your data goes. And every one of them has the same three problems: the
interface is welded to the logic, the AI is welded to one vendor, and your data is welded to
their cloud.

I spent the last months building spreadsheet-intelligence tooling for exactly the kind of users
who can't accept any of those three welds — banks reconciling settlement files, compliance teams
running KYC checks, auditors hunting fraud signals in vendor ledgers. Here's the conclusion I
ended up rebuilding my entire codebase around:

**The product is not an app. The product is a set of capabilities. Ship it as an MCP server, and
every app — including the ones you didn't write — becomes your frontend.**

## The placement math

Excellia does profiling, rule validation, anomaly detection, two-file reconciliation, fraud
scoring, KYC name matching, and AI-assisted cleanup. The naive build is a Flask app with all of
that behind buttons — I know, because the legacy version was exactly that, and it was a monolith
where every feature existed once *per screen* instead of once.

The rebuild follows one placement rule, and it decides every line of code:

- If it **computes**, it lives in the core engine — pure Python, pandas, scikit-learn. No HTTP
  imports, no GUI imports. Test-enforced.
- If it **waits, queues, stores, or uploads**, it lives in a small FastAPI layer. Every endpoint
  calls exactly one core function.
- If it **describes a capability to a model**, it lives in the MCP server.
- If it **renders pixels**, it's a face — and faces own zero logic.

The MCP server is the interesting layer, and the discipline is that it stays *thin*: nineteen
tools, each one a docstring and an HTTP forward. The moment it imports pandas, the architecture
has failed. Docstrings are written for the model, not for humans — trigger words, defaults,
output shapes, and what to do on failure — because in an agentic world, **the docstring is the
UI** and the error message is the help page. "File not found: use an absolute path" makes an
agent self-correct; a stack trace makes it hallucinate.

## One server, two brains

Here is the payoff, and it's the whole thesis. The same unchanged server runs:

- **Claude Desktop**, for the analyst who wants convenience. Claude never receives the file —
  it receives tools. The spreadsheet, the pandas work, the ML — all local. What reaches the
  cloud is the prompt, a file *path*, and tool results.
- **A fully offline agent** — a ~100-line MCP host we ship, where a local Ollama model picks the
  same tools over the same stdio protocol. Wi-Fi off. Zero bytes leave the machine. This is the
  mode for the bank.

Zero code changes between those two deployments. Not "portable in principle" — the same
`server.py`, byte for byte, proven by an integration test that drives both. When a regulated
customer says "we can't send even the summaries to a cloud vendor," the answer isn't a
six-month enterprise fork; it's a different config block.

Try to do that with an app. The app *is* the brain-vendor coupling.

And the human doors didn't disappear — they got cheaper. Excellia still ships a web UI and an
Excel add-in with custom formulas, but both are pure HTTP clients of the same API the MCP tools
call, and both are test-enforced to contain zero logic. When the fraud scorer gained a new
metric, every face got it for free. The web app is static vanilla JS served by the API process
itself; the "frontend rewrite" argument ended because there's nothing there to rewrite.

## The LLM is staff, not management

An MCP server full of AI-shaped tools invites a failure mode: letting the model do the work.
We drew a hard line, and it belongs in the architecture, not in a prompt:

**Deterministic code decides; the LLM proposes, explains, and formats.** If a regex can validate
a tax ID, a model must not. Numbers only ever come from pandas. When a user chats with their
data, the model produces a *query plan* — a strict-JSON structure executed against a whitelist —
and the answer ships with the evidence table and the plan that ran. When the model proposes a
cleanup, it compiles to a deterministic recipe, previewed on a sample, applied only on confirm,
and always to a *new* file. The model call itself lives behind one module with a strict-JSON
contract, one repair reprompt, and a typed failure — so a sloppy local model degrades into an
instructive refusal, never a silent wrong number.

This split is also what makes the offline mode viable: a 7B local model that only has to *route
and narrate* is good enough today. A 7B model trusted to *compute* is not, and may never need
to be.

## What this costs

Honesty section, because architecture posts lie by omission:

- **MCP hosts are uneven.** Sideloading, config blocks, restarts — the last mile is still
  manual in ways a packaged app isn't.
- **You write more error-message copy than UI copy.** That's the trade: the interface moved
  from pixels to prose.
- **Thin is a discipline, not a default.** Every feature wants to grow logic in the server
  layer "just this once." Line count is our canary; a purity test is our enforcement.
- **A local job queue, workspace, and audit trail** had to be built anyway — agents need
  somewhere to park big-file work and humans need to audit what ran. The API layer never
  becomes zero; it becomes small.

## The bet

Enterprise software spent a decade as "SaaS app with an API, maybe." The agentic version
inverts that: **capabilities-first, faces optional**. A deep, well-documented tool server —
one that computes deterministically, explains every output, and runs where the data lives —
gets adopted by whatever host the customer already trusts: Claude Desktop today, an internal
agent tomorrow, an Excel formula for the analyst who never leaves her grid.

One brain, many faces. The faces are replaceable. The brain is yours.

*Excellia is open source — a pip install, one config block, and nothing leaves your machine.*
