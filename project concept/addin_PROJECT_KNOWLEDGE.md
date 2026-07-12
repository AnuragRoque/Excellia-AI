# Excellia AI - Local LLM Excel Extension

Excellia AI is a privacy-first, fully local AI assistant integrated natively into Microsoft Excel as a Task Pane Add-in, empowering users to leverage Large Language Models directly on their spreadsheets without sending sensitive data to the cloud.

---

# Elevator Pitch

Excellia AI bridges the gap between powerful Large Language Models and sensitive spreadsheet data. By running as a native Excel Add-in and communicating exclusively with a local Ollama instance, it allows financial, HR, and operations teams to chat with data, extract entities, categorize rows, and summarize text—all locally, offline, and with zero data privacy risk. 

---

# Problem Statement

Many professionals work with highly confidential or regulated data in Microsoft Excel (e.g., payroll, customer PII, internal financials). These users want to leverage generative AI for data transformation and analysis, but strict enterprise compliance policies forbid sending this data to third-party cloud APIs like OpenAI or Anthropic. Excellia AI solves this by bringing the AI directly to the data on the local machine.

---

# Target Users

**Primary users:**
Data Analysts, Finance Teams, HR Professionals, and Operations Managers handling sensitive datasets.

**Secondary users:**
Local-AI enthusiasts and developers looking for a fast, UI-driven way to batch-process data through local LLMs.

**Admin users:**
Not applicable (stateless local tool).

---

# Core Vision

To become the standard local-first data processing engine for enterprise spreadsheet workers, seamlessly blending deterministic logic (Regex, macros) with probabilistic inference (LLMs) under a unified, privacy-guaranteed interface.

---

# Product Philosophy

**Privacy-first:** Zero bytes leave the user's local network. Data belongs to the user.
**Non-Destructive:** AI operations must never overwrite original user data; they must augment it.
**Unobtrusive:** The UI should feel like a native, lightweight Microsoft Office feature (Fluent UI principles).
**Deterministic Fallbacks:** If a rule-based algorithm (like Regex) can solve a problem perfectly, it should be used instead of an LLM.

---

# Key Features

**Chat**
- **Purpose:** Context-aware Q&A with the local LLM.
- **Inputs:** User text prompt.
- **Outputs:** Text bubble in the chat UI.
- **Dependencies:** Ollama (`/api/generate`).
- **Future improvements:** Streaming token output, chat history memory.

**Extract & Transform**
- **Purpose:** Apply custom natural language instructions to each row (e.g., "Extract emails", "Translate to Hindi").
- **Inputs:** Selected Excel cells, user text instruction.
- **Outputs:** New column with transformed text.
- **Dependencies:** Ollama, `office.js`.
- **Future improvements:** Multi-column context awareness.

**Categorise & Summarize**
- **Purpose:** Taxonomy labeling and text condensation.
- **Inputs:** Selected text cells.
- **Outputs:** 1-3 word labels or a single sentence per row/batch.
- **Dependencies:** Ollama.
- **Future improvements:** Ability to specify custom predefined taxonomy lists.

**Simplify JSON**
- **Purpose:** Translates raw database JSON dumps inside cells into plain English.
- **Inputs:** Selected cells containing JSON strings.
- **Outputs:** Human-readable sentences.
- **Dependencies:** Ollama.

**IFSC Validator**
- **Purpose:** Validates Indian bank branch codes instantly and with 100% accuracy.
- **Inputs:** Selected cells.
- **Outputs:** "Valid" or "Invalid" annotations.
- **Dependencies:** Pure Regex (No LLM).
- **Future improvements:** Expand to SSN, email, and credit card format validation.

---

# User Journey

User opens Microsoft Excel and loads a sensitive dataset.
↓
User clicks the Excellia Add-in button on the ribbon.
↓
The Task Pane opens; the system auto-checks the local Ollama connection.
↓
User highlights a column of messy data (e.g., mixed addresses).
↓
User selects "Extract / Transform" and types "Extract only the Zip Code".
↓
User selects Processing Mode (Combined for speed, Per-Row for accuracy).
↓
User clicks "Send". The Add-in reads the data, proxies it to Ollama, and writes the Zip Codes into the adjacent empty column.

---

# System Architecture

**Frontend (Excel Task Pane):** 
Built with Vanilla HTML, CSS, and JavaScript. Uses `office.js` to read/write Excel DOM elements. 

**Backend (Local Proxy):**
A Node.js/Express server (`server.js`) running locally on HTTPS. Its sole responsibility is serving the static frontend files and acting as a transparent reverse proxy.

**AI (Ollama Engine):**
A local Ollama daemon running on HTTP. Executes the inference using models like `llama3.1` or `mistral`.

**Database / Storage:**
Stateless. The Excel workbook acts as the database.

---

# Folder Purpose

`/Excellia-AI-Extension`
The primary production-ready implementation containing the Node.js proxy and the HTML/JS frontend.

`/m1`
An archived, early-stage prototype utilizing Python/FastAPI instead of Node.js for the local server.

`/excel_extension_llm_stable` & `/my-excel-addin`
Earlier boilerplate iterations and snapshots capturing the initial setup of the Office Add-in manifest and HTTPS dev environment.

---

# Data Flow

User highlights Excel cells.
↓
`office.js` reads cell values into memory.
↓
`script.js` wraps the values in a strict system prompt.
↓
`fetch()` sends the payload to `https://localhost:3000/ollama/api/generate`.
↓
Express (`http-proxy-middleware`) strips `/ollama` and routes to `http://127.0.0.1:11434/api/generate`.
↓
Ollama performs inference and returns a JSON array or text block.
↓
`script.js` parses the response and maps it to the Excel grid.
↓
`office.js` writes the mapped data to an adjacent column and runs `context.sync()`.

---

# AI Components

**Models:** 
Agnostic, but defaults to `llama3.1:latest` or `mistral`.

**Prompt Templates:** 
Hardcoded zero-shot system prompts designed to force strict outputs (e.g., "Return ONLY a JSON array").

**Reasoning/Output Generation:** 
Utilizes temperature defaults from Ollama. Relies heavily on batch-processing (asking the model to process 10 rows and return 10 array items) or sequential processing (one distinct LLM call per row).

---

# Database Design

No internal database exists. The application uses the user's active Microsoft Excel Worksheet as the persistent state. 

---

# API Design

The system does not expose a public API; it consumes the local Ollama API.

**Ollama API Used:**
- `POST /api/generate`: Sends the model name and prompt with `stream: false`.
- `GET /api/tags`: Used on boot to verify the Ollama daemon is active and responsive.

---

# Configuration

**Runtime Settings (in `script.js` & `server.js`):**
- `MODEL`: Defines the Ollama model to use.
- `PORT`: Node server port (default 3000).
- `OLLAMA_TARGET`: The exact URL of the Ollama HTTP daemon (default `http://127.0.0.1:11434`).

---

# Security Model

**Privacy:** 100% offline and local. 
**Mixed-Content Evasion:** Excel blocks HTTP requests from HTTPS add-ins. The architecture solves this by wrapping the Ollama HTTP calls inside a trusted localhost HTTPS proxy (`office-addin-dev-certs`).
**Data Integrity:** The application enforces a strict "Non-Destructive Write" rule, meaning it actively calculates the boundaries of the user's data to ensure it only writes into empty, adjacent columns or rows.

---

# Important Algorithms

**Smart UsedRange Intersection:**
Users often click entire columns, technically selecting over 1 million rows. The system uses Excel's `getUsedRangeOrNullObject(true)` to calculate the mathematical intersection between the user's selection and the actually populated cells, preventing the system from sending a million empty strings to the LLM.

**IFSC Regex Validation:**
Bypasses the LLM entirely to use `/^[A-Z]{4}0[A-Z0-9]{6}$/` for fast, deterministic bank code validation, saving compute and preventing AI hallucinations.

---

# Business Rules

1. **Never Overwrite:** AI output must always go to `selectionRange.columnIndex + selectionRange.columnCount` (adjacent column) or appended beneath the active range.
2. **Visual Distinction:** AI-generated cells are formatted differently (e.g., blue accent text, italics on the header) to distinguish them from human-entered data.
3. **Graceful Degradation:** If the LLM hallucinates the JSON array structure in "Combined" mode, the parser falls back to splitting the string by newlines.

---

# Dependencies

- `express`: Handles the local web server routing.
- `http-proxy-middleware`: Crucial for securely proxying the Ollama HTTP traffic through HTTPS.
- `office-addin-dev-certs`: Generates the trusted localhost certificates required by Microsoft Office to load custom web add-ins.
- `office.js`: Hosted by Microsoft; provides the DOM bridge into the Excel desktop client.

---

# Technical Decisions

**Why Node.js/Express over direct fetch?**
Office Add-ins enforce strict HTTPS. Browsers block HTTPS clients from fetching HTTP endpoints (Ollama). The proxy was the lightest way to bridge this gap without modifying the host machine's firewall/network settings.

**Why Vanilla JS over React?**
To keep the bundle size virtually zero and load the task pane instantly inside the heavy Excel desktop client. 

**Why Local Models?**
To completely eliminate the friction of enterprise security reviews, API key management, and cloud costs.

---

# Performance Considerations

**Batching vs. Sequential Execution:**
The user can choose between "Combined" (one massive LLM call for all rows) or "Per-Row" (individual calls). Combined is network-efficient but prone to LLM formatting errors. Per-Row is slow but highly accurate.

**Excel Sync Optimization:**
`context.sync()` is an expensive operation in `office.js`. In Combined mode, it is called exactly once after mapping all data. In Per-Row mode, it is called repeatedly to create a live, typewriter-like UX.

---

# Current Limitations

- **No Streaming:** The UI waits for the entire LLM response before updating, which can feel slow on heavy tasks.
- **Model Selection:** The model is currently hardcoded in the JS file rather than being dynamically selectable from a dropdown in the UI.
- **Cancellation:** Once an LLM request fires, there is no "Abort" button to cancel the in-flight network request.

---

# Future Roadmap

- Implement the AbortController API to allow users to cancel long-running AI extractions.
- Add a dropdown querying Ollama's `/api/tags` to let the user switch between installed models on the fly.
- Implement streaming JSON parsing to populate Excel cells sequentially even during a single batch request.
- Add custom prompt template saving so users can reuse complex instructions.

---

# Developer Notes

- `office.js` relies heavily on `load()` and `sync()`. If you try to read a property (like `range.address`) without loading and syncing it first, Excel will throw a silent error. 
- The proxy server will fail to start if the local certs are expired or missing; `npx office-addin-dev-certs install` is the standard fix.
- Most heavy logic resides in `script.js`.

---

# How to Continue Development

If modifying this project, you must know:
1. **The HTTPS Proxy is non-negotiable.** Do not attempt to rip out Express to make direct `fetch()` calls to Ollama from the browser; Office will aggressively block it.
2. **Never violate the Non-Destructive Write principle.** Any new features must append or adjacent-write data. Overwriting user data will destroy trust in the tool.
3. **Respect `context.sync()`.** Batch Excel writes whenever possible. Only sync inside a loop if live UI feedback (like the Per-Row processing mode) is the explicit design goal.
4. **Assume Hallucinations.** When asking the LLM for structured data (like JSON arrays), always include a robust fallback parser. LLMs will eventually return malformed output.
