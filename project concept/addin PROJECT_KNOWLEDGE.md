# Excellia AI

Excellia AI is a local-first, AI-driven spreadsheet validation and data quality platform. It is designed to automate the process of data cleaning, validation, anomaly detection, and enrichment for large datasets by combining rule-based heuristics, machine learning algorithms, and local Large Language Models (LLMs) to drastically reduce the manual effort required by data analysts.

---

# Elevator Pitch

Excellia AI empowers data teams to automate tedious spreadsheet validation without compromising data privacy. By leveraging local LLMs (via Ollama) and scikit-learn machine learning algorithms, the platform intelligently identifies outliers, enforces data rules, and applies complex text transformations directly onto your tabular data. It functions entirely on-premise, ensuring sensitive data never leaves your infrastructure, while processing hundreds of thousands of rows efficiently through a non-blocking background queue and an interactive, analyst-in-the-loop web interface.

---

# Problem Statement

Data analysts and engineers spend an inordinate amount of time manually cleaning, formatting, and validating large spreadsheets before they can be used for reporting or ETL pipelines. Traditional tools require writing complex macros, scripts, or formulas. Cloud-based AI tools can automate this, but sharing proprietary, regulated, or sensitive corporate data with third-party APIs poses unacceptable privacy and security risks. Excellia AI bridges this gap by providing an intelligent, automated data cleaning solution that operates 100% locally.

---

# Target Users

**Primary users**
*   **Data Analysts**: Looking to automate repetitive data cleaning and anomaly detection tasks.
*   **Data Engineers**: Needing a pre-ETL validation step to ensure data quality.

**Secondary users**
*   **Business Operations / Domain Experts**: Users who need to clean up lists, invoices, or customer data but lack coding skills.

**Admin users**
*   **IT / System Administrators**: Responsible for deploying local LLM infrastructure and securing internal data governance tools.

---

# Core Vision

The long-term vision for Excellia AI is to become the ultimate enterprise-grade, privacy-preserving data governance hub. It aims to seamlessly integrate advanced machine learning anomaly detection and deep LLM contextual understanding into everyday spreadsheet workflows, eventually serving as a robust automated data quality gatekeeper for enterprise data lakes and warehouses.

---

# Product Philosophy

*   **Privacy-first / Local AI**: No data ever leaves the local environment. All LLM inference and ML predictions happen on-premise.
*   **Analyst-in-the-loop**: The AI assists and suggests, but provides an interactive UI for the user to review, edit, and ultimately approve changes.
*   **Automation-first**: Replaces manual Excel formulas with natural language prompts and automated ML checks.
*   **Resilient & Scalable**: Must handle 100K+ rows without freezing the user interface, utilizing background job queues.

---

# Key Features

### 1. Dual-Layer Quality Assurance (Rule-Based & ML)
*   **Purpose**: Automatically flag data quality issues before they pollute downstream systems.
*   **Inputs**: Uploaded spreadsheet.
*   **Outputs**: Summary JSON report, Data Health Score, and conditionally formatted Excel files highlighting problem cells.
*   **Dependencies**: Pandas, Scikit-learn, Openpyxl.
*   **Future improvements**: Customizable rule templates per industry domain.

### 2. LLM-Assisted Column Analysis & Transformations
*   **Purpose**: Perform complex data extraction, categorization, or formatting using natural language prompts.
*   **Inputs**: Target columns, user prompt, optional rules/output formats.
*   **Outputs**: Transformed data (either overwriting existing columns or appending new `_AI_Result` columns).
*   **Dependencies**: Ollama (Gemma3, Phi3), Threading.
*   **Future improvements**: Agentic chaining where one AI output feeds into another AI validation step.

### 3. Interactive Data Cleaning Workflow
*   **Purpose**: Provide standard data wrangling tools via a simple UI.
*   **Inputs**: User UI interactions.
*   **Outputs**: Cleaned DataFrame state in memory.
*   **Dependencies**: Flask backend.
*   **Future improvements**: Undo/redo stack for data transformations.

### 4. Background Job Processing
*   **Purpose**: Process large datasets with LLMs without timing out the web requests.
*   **Inputs**: AI tasks.
*   **Outputs**: Progress updates and downloadable resulting Excel files.
*   **Dependencies**: Python `queue.Queue` and `concurrent.futures.ThreadPoolExecutor`.
*   **Future improvements**: Migration to Redis/Celery for distributed processing.

---

# User Journey

User opens app in browser
↓
**Upload**: User uploads a CSV or Excel file.
↓
**Preview & Setup**: User previews data (first 50 rows) and performs basic cleaning (e.g., dropping empty rows, redefining header rows).
↓
**Automated Checks**: User runs Data Quality Checks. System calculates missing values, format inconsistencies, and runs ML to find synthetic outliers.
↓
**Review**: User reviews the Data Health Score and downloads the highlighted summary report.
↓
**AI Transformation (Optional)**: User selects columns and writes a prompt (e.g., "Extract company name from this text").
↓
**Background Jobs**: System queues the AI job, processing rows concurrently. UI polls for progress.
↓
**Export**: User downloads the final, enriched, and validated Excel spreadsheet.

---

# System Architecture

*   **Frontend**: Vanilla HTML, CSS, and JavaScript. Uses basic polling (`setInterval`) for job progress updates. No complex SPA framework, ensuring lightweight delivery.
*   **Backend**: Python Flask application. Acts as the orchestrator.
*   **Database**: Currently state is held in memory using global Python dictionaries (`session_state`, `file_dataframes`). Temporary files are written to the OS temp directory.
*   **Workers**: A built-in Python background thread reads from a `queue.Queue` and uses `ThreadPoolExecutor` to handle concurrent LLM requests to the Ollama daemon.
*   **AI (Local)**: Expects a local Ollama instance running models like `gemma3:4b-it-qat` or `phi3:3.8b`. 
*   **Storage**: Ephemeral local disk storage for uploaded and generated Excel/CSV files.

---

# Folder Purpose

*   **`/` (Root)**: Contains the main application entry points (`app.py`, `routes.py`, `routes2.py`) and documentation (`README.md`).
*   **`/templates`**: Contains Flask HTML templates. Features a modular design with partials (`tab_home.html`, `tab_preview.html`, etc.) included into `index.html`.
*   **`/static`**: Contains vanilla CSS (`styles.css`) and JavaScript logic (`script.js`, `script2.js`) for the interactive UI.
*   **`/ai scanner duck`**: Appears to be an experimental or future directory for DuckDB integration (contains a `.duckdb` database file), indicating a planned move towards robust on-disk data processing.

---

# Data Flow

User Upload 
↓ 
File saved to OS temp directory
↓ 
Pandas DataFrame loaded into global memory (`session_state`) 
↓ 
**Branch A (Rule/ML Checks)**: `routes2.py` analyzes DataFrame synchronously -> Generates formatted Excel -> Returns JSON summary to UI.
**Branch B (AI Job)**: `routes.py` creates a job ID -> Puts job in `queue.Queue` -> Worker thread pulls job -> `ThreadPoolExecutor` dispatches row data to Ollama -> Ollama returns text/JSON -> Worker updates DataFrame -> Result Excel saved -> UI polls and downloads.

---

# AI Components

*   **Models**: Specifically optimized for local execution via Ollama (Gemma3, Phi3).
*   **Prompt Templates**: The system heavily relies on a strict `SYSTEM_INSTRUCTION` declaring the AI as an "expert data analyst" forbidden from outputting conversational filler.
*   **Agents / Tools**: Currently operates as a single-step transformer. If the user selects multiple columns to replace, the prompt dynamically requests a JSON mapping back from the LLM to route answers to the correct columns.
*   **ML Outlier Detection**: Uses a `RandomForestClassifier`. It generates "synthetic" random rows based on the dataset's numerical distributions and trains the model to distinguish real rows from synthetic ones. Rows highly classified as synthetic are flagged as outliers.

---

# Database Design

The application currently does not use a relational database. It relies heavily on in-memory Python state:
*   **`session_state`**: A dictionary tracking the active user's current DataFrame, selected model, progress metrics, and file paths.
*   **`file_dataframes`**: A dictionary mapping file IDs to their respective Pandas DataFrames.
*   **`jobs`**: A dictionary tracking the status, progress, and results of background AI tasks.

*Note: The presence of `duckdb` files suggests a migration towards a more robust, queryable analytical database in the future.*

---

# API Design

*   **`POST /start_ai`**: Submits a prompt and selected columns for AI processing. Returns a `job_id`.
*   **`GET /job_progress/<job_id>` & `/job_list`**: Polled by the frontend to update progress bars and job status.
*   **`POST /data_checks2`**: Executes the comprehensive rule-based and ML anomaly detection pipeline. Returns a detailed JSON payload of data health metrics and file paths for download.
*   **`POST /edit/*`**: A suite of lightweight endpoints for DataFrame manipulation (`clean_empty_fields`, `redefine_headers`, `clear_row`).
*   **`POST /apply_formats2`**: Applies standard programmatic data formatting (trimming, casing, currency stripping) without needing LLMs.

---

# Configuration

*   **Environment Variables**: Minimal. Relies on `tempfile.gettempdir()` for storage.
*   **Secrets**: `app.secret_key` is hardcoded to `"change_this_to_a_secure_random_key"`.
*   **Runtime Settings**: Model selection is dynamic based on available local Ollama models. Concurrency is hardcoded to `max_workers=8` in the ThreadPoolExecutor.

---

# Security Model

*   **Privacy**: Strong. Because all processing is local, there is zero risk of data leakage to external APIs.
*   **Authentication/Authorization**: Currently **non-existent**. The UI has a placeholder dropdown for user profiles, but the backend uses global shared state. This means if two users access the app concurrently, their data will collide.
*   **Input Sanitization**: Basic file extension validation (.csv, .xlsx). Filenames are sanitized before download to prevent directory traversal.

---

# Important Algorithms

*   **Synthetic Outlier Detection (`detect_outliers_rf`)**: Instead of standard standard deviation checks, it attempts to auto-select numeric features, generates uniform synthetic data across feature ranges, and trains a Random Forest. Real rows that the classifier thinks look "synthetic" (low probability of being real) are flagged.
*   **Row-Level Duplicate Checking**: Optimizes duplicate detection by checking for repeating values *across* columns within a single row, identifying redundant data entry.
*   **Data Health Score**: A custom heuristic scoring algorithm starting at 100, deducting points weighted by severity (e.g., outliers cost 0.8 points per percentage of rows affected, mixed types cost 0.5 points).

---

# Business Rules

*   **Empty Value Definition**: A value is considered empty if it is NaN, None, an empty string, or exact text matches like "nan", "null", "n/a", or "\n".
*   **AI JSON Parsing Fallback**: When requesting multi-column replacements, the system strictly requests JSON from the LLM. If the LLM fails to return valid JSON, it falls back to pasting the raw text response into all selected columns.
*   **Data Consistency Priorities**: For conditional formatting in the Excel report, Outliers > Intra-row Duplicates > Cross-row Duplicates > Mixed Types > Format Issues.

---

# Dependencies

*   **Flask**: Core web server and routing.
*   **Pandas & NumPy**: Heavy lifting for all data manipulation, cleaning, and tabular state management.
*   **Scikit-learn**: Required for the Random Forest outlier detection.
*   **Ollama (Python API)**: Connects to the local LLM daemon for AI inference.
*   **Openpyxl**: Specifically used for applying cell-level background colors (conditional formatting) to the generated summary Excel files.

---

# Technical Decisions

*   **Local LLMs (Ollama) chosen over OpenAI**: To adhere strictly to the privacy-first core vision, making it safe for regulated enterprise data.
*   **Pandas as In-Memory State**: Chosen for fast prototyping and excellent tabular data manipulation APIs, though it limits scalability and multi-user support.
*   **Vanilla JS over React/Vue**: Keeps the project lightweight, easy to run without Node.js build steps, and straightforward to integrate with Jinja templates.
*   **Split Routing (`routes.py` vs `routes2.py`)**: `routes.py` handles the AI jobs and queueing, while `routes2.py` isolates the traditional programmatic and ML-based data quality checks.

---

# Performance Considerations

*   **Job Queues**: LLM generation is inherently slow. The app prevents HTTP timeouts by immediately returning a Job ID and processing the DataFrame concurrently in background threads.
*   **Batching / Threading**: The `ThreadPoolExecutor` maps the LLM requests across 8 workers simultaneously, significantly speeding up column generation.
*   **Graceful ML Fallbacks**: If Scikit-learn is missing or if the dataset has zero numeric columns, the system gracefully bypasses the Random Forest logic rather than crashing.

---

# Current Limitations

*   **Global State Collisions**: The use of global variables (`session_state`, `file_dataframes`) makes the app unsafe for concurrent multi-user access.
*   **Hardcoded Configuration**: Concurrency limits and secret keys are hardcoded.
*   **Memory Leaks**: DataFrames are stored in memory and are only cleared if the user manually hits a 'restart' action or uploads a new file. Stale sessions will eventually consume all RAM.
*   **No File Cleanup**: Temporary generated Excel files are not automatically garbage collected.

---

# Future Roadmap

*   **Database Integration**: The presence of DuckDB files suggests a move toward out-of-core data processing, which will solve memory limitations and allow for handling massive files.
*   **Multi-tenant Architecture**: Implementing real sessions or a database backend to isolate user workspaces.
*   **Agentic Workflows**: Moving beyond single-prompt column generation to complex, multi-step reasoning agents that can autonomously decide how to clean a messy file.

---

# Developer Notes

*   **Architecture Pattern**: Classic monolithic MVC, but the "Model" is currently just volatile RAM.
*   **Coding Conventions**: Functions are highly encapsulated within the `register_routes` functions. This prevents circular imports but makes the files very long and somewhat difficult to unit test.
*   **Common Abstractions**: The robust file loader (`load_dataframe` in `routes.py`) is a critical utility. It attempts multiple encodings, delimiters, and engines to ensure maximum compatibility with messy CSVs.

---

# How to Continue Development

**If another AI receives ONLY this document:**

*   **What you must know**: This is a strictly local-first application. Do not introduce any dependencies on cloud APIs (OpenAI, AWS, etc.) without explicit permission. The state is currently fragile (in-memory globals) and should be respected or fully refactored into a session-backed database (like Redis or DuckDB).
*   **Never violate**: The privacy of the data. All inference must go through the local Ollama connection.
*   **Architecture consistency**: The split between `routes.py` (LLM background jobs) and `routes2.py` (Programmatic Data Checks) is intentional. Maintain this separation of concerns. If modifying the background jobs, ensure the queue and threading logic remains non-blocking for the Flask server.
