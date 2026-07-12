# Excellia AI - Local LLM Excel Extension (Full Technical Concept)

## Executive Summary
This repository contains iterations of a privacy-first, local AI assistant designed to operate directly inside Microsoft Excel as a Native Task Pane Add-in. The primary goal is to empower users with Large Language Models (LLMs) like Llama 3.1 and Mistral to perform complex data manipulation, classification, and generation tasks natively in Excel, while guaranteeing **zero data leakage**. 

Because it hooks into a local **Ollama** engine, financial, HR, and proprietary operational data never leave the user's machine, circumventing strict enterprise cloud compliance policies.

---

## 🏗️ System Architecture & The "Mixed-Content" Workaround

Building a local-only AI Excel extension presents a significant technical hurdle: **Office Add-ins must be served over HTTPS**, but local Ollama instances run on standard HTTP (`http://127.0.0.1:11434`). If the Excel task pane attempts to call Ollama directly, the browser engine blocks it as a "mixed-content" security violation.

### The Data Flow
1. **The Client (Excel Task Pane):** Built using Vanilla HTML/CSS/JS and the `office.js` API. It captures user intent, reads the selected Excel cells, and packages the request.
2. **The Local HTTPS Proxy (Node.js/Express):** A local server runs on `https://localhost:3000` (using `office-addin-dev-certs`). It serves the add-in UI and, crucially, uses `http-proxy-middleware` to listen on the `/ollama` path.
3. **The LLM Engine (Ollama):** The Node server intercepts the `/ollama` request and transparently proxies it to the local HTTP Ollama server. 
4. **Non-Destructive Write-Back:** The LLM's response flows back through the proxy to the Task Pane, which uses `office.js` to write the results into a *new* adjacent column or append it to the bottom of the dataset.

---

## ⚙️ Core Processing Modes

The extension is designed to handle Excel data in two fundamentally different ways, depending on the complexity of the task and the user's need for speed vs. accuracy.

### 1. Combined Mode (Batch Processing)
- **How it works:** Reads the entire selected range, formats it into a single numbered list, and appends the user's instruction. It asks the LLM to return a perfectly ordered **JSON array of strings**.
- **Pros:** Extremely fast (one single API call).
- **Cons:** LLMs can occasionally lose track of indexing in very large datasets, returning fewer array items than requested.
- **Output:** The add-in parses the JSON array and writes the entire column to Excel simultaneously. If the LLM hallucinates the JSON structure, it falls back to parsing line-by-line.

### 2. Per-Row Mode (Sequential Processing)
- **How it works:** A `for` loop iterates through the selected cells. The Add-in makes a separate, isolated API call to Ollama for *every single row*.
- **Pros:** Highly accurate. The LLM focuses 100% of its attention context on a single item.
- **Cons:** Slower, as it waits for network/inference latency on every row.
- **Output:** Provides a live UX. As each row finishes, the cell right next to it updates instantly in Excel, accompanied by a status tracker (e.g., "Row 3 / 10...").

---

## 🧠 Built-in AI Operations & Prompt Engineering

The extension uses predefined system prompts (configured in `script.js`) that prepend the user's custom instructions to force the LLM into specific data-processing behaviors:

| Operation | System Prompt Instruction (Combined Mode) | Expected Output |
| :--- | :--- | :--- |
| **Chat** | Standard conversational mode. | Text bubble in UI (does not write to Excel). |
| **Extract / Transform** | *"Apply the user's instruction... Return ONLY a JSON array of strings... No explanation, no markdown."* | Extracted sub-strings (e.g. pulling emails from messy text) or translated text. |
| **Summarize** | *"Summarize the selection in ONE concise sentence."* | A single, condensed string describing the dataset. |
| **Categorise** | *"Categorise each item into a short label (1-3 words)."* | Clean taxonomic tags for grouping/filtering data. |
| **Keywords** | *"Extract 3-5 keywords for each item."* | Comma-separated tags. |
| **Simplify JSON** | *"Convert each JSON payload into a plain one-sentence description."* | Human-readable English translated from raw database JSON dumps. |

---

## 🛡️ Edge Cases and Non-LLM Operations

### Smart Range Selection
Users frequently click an entire column header (e.g., Column A), which technically selects 1,048,576 rows. The script intelligently uses `sheet.getUsedRangeOrNullObject(true)` to intersect the user's selection with the *actual used data range*. This prevents the add-in from sending a million empty rows to the LLM.

### Deterministic Fallbacks (IFSC Validator)
Not everything requires an LLM. The extension includes an **IFSC Validator**.
- **Why?** LLMs are notoriously bad at strict character counting and regex-style pattern matching (they hallucinate).
- **How it works:** Bypasses Ollama entirely. It runs a pure JavaScript Regex (`/^[A-Z]{4}0[A-Z0-9]{6}$/`) over the cells. 
- **Result:** Instant, 100% accurate validation of Indian Bank branch codes.

### Output Formatting
When writing data back to the sheet, the script automatically applies subtle formatting (e.g., italicizing the top cell and applying a blue accent color `#0f6cbd`) so the user can easily spot where the AI generated new data versus their original dataset.
