# Excellia AI

Excellia AI is a local-first, AI-driven data quality and spreadsheet validation platform. It empowers data analysts to automate data cleaning, enforce schema consistency, and detect anomalies across large datasets (100K+ rows) without compromising data privacy. By combining traditional rule-based validation, machine learning techniques, and local Large Language Models, Excellia AI dramatically reduces manual review time while keeping sensitive data entirely on-device.

---

# Elevator Pitch

Excellia AI is a privacy-first, local web application that automates spreadsheet validation and data cleaning. Instead of manually writing complex Excel formulas or relying on cloud-based AI that compromises data security, Excellia leverages local LLMs (Ollama) and machine learning (Scikit-learn) to clean, standardize, and flag anomalies in datasets. Built for data analysts dealing with messy data, it turns hours of manual review into minutes of automated, offline processing.

---

# Problem Statement

Data analysts and engineers spend an inordinate amount of time manually cleaning, standardizing, and validating spreadsheets before the data can be ingested into BI tools or ETL pipelines. Standard spreadsheet software lacks intelligent, context-aware validation. Furthermore, passing confidential or regulated data through cloud-based AI tools (like OpenAI or Claude) poses unacceptable security and privacy risks. Excellia AI solves this by bringing powerful, AI-assisted data wrangling completely local to the user's machine.

---

# Target Users

**Primary users**
Data Analysts, Data Engineers, and Data Stewards responsible for data quality.

**Secondary users**
Business Analysts, Operations Managers, and Financial Controllers needing quick data sanity checks.

**Admin users**
IT Administrators (responsible for deploying the local Ollama models and Python environments).

---

# Core Vision

To become the ultimate privacy-first, intelligent data governance sidekick. The vision is to automate the tedious aspects of data preparation, allowing data professionals to focus on analysis rather than wrangling, all while guaranteeing zero data exfiltration.

---

# Product Philosophy

- **Privacy-first**: All data processing and AI inference runs completely locally. Data never leaves the system.
- **Offline-first**: No internet connection is required for core functionality once models are downloaded.
- **AI-Assisted, Not Autonomous**: AI augments the analyst by suggesting transformations and detecting outliers, but the user retains full control over the rules and the final export.
- **Pragmatic Scalability**: Built to handle large spreadsheets (100K+ rows) efficiently using parallel background workers, without freezing the user interface.

---

# Key Features

### 1. AI-Driven Data Cleaning (Column-level Analysis)
- **Purpose**: Understand column semantics and apply contextual, natural language transformations (e.g., categorizing data, extracting entities, standardizing text).
- **Inputs**: Spreadsheet data, selected columns, user prompts, specific rules.
- **Outputs**: New columns appended to the data containing AI-generated or transformed values.
- **Dependencies**: Ollama (Gemma3, Phi3).
- **Future improvements**: Domain-specific fine-tuned models, automatic prompt generation based on inferred column schema, batching LLM requests.

### 2. Rule-Based Validation
- **Purpose**: Enforce strict data quality standards with high determinism.
- **Inputs**: Spreadsheet data, user-selected checks (Missing values, Duplicates, Mixed Types, Format Issues).
- **Outputs**: Data health scores, summary statistics, and conditionally formatted Excel exports highlighting problematic cells.
- **Dependencies**: Pandas, OpenPyXL.
- **Future improvements**: Custom regex validation templates saved by the user, cross-table referential integrity checks.

### 3. ML-Based Anomaly Detection
- **Purpose**: Find statistical outliers that might not violate explicit rules but are anomalous compared to the rest of the dataset.
- **Inputs**: Numeric features from the spreadsheet.
- **Outputs**: Outlier flags ("Yes"/"No"), probability scores, remarks explaining the deviation, and cell highlighting.
- **Dependencies**: Scikit-learn (RandomForestClassifier).
- **Future improvements**: Unsupervised clustering for anomaly detection on categorical text data, integration of IsolationForest.

### 4. Interactive Data Workflow
- **Purpose**: Allow users to upload, preview, process, and download data seamlessly without touching code.
- **Inputs**: CSV or Excel files.
- **Outputs**: Downloadable sanitized Excel files and interactive progress updates.
- **Dependencies**: Flask, Threading, Vanilla JS.
- **Future improvements**: In-browser interactive spreadsheet editor (e.g., using Handsontable) for immediate cell modifications.

---

# User Journey

1. **User opens app**: Navigates to the local Flask server URL.
2. **Upload**: User uploads a CSV or Excel file.
3. **Dashboard / Preview**: The system parses the file using a robust loader and displays a data preview.
4. **Configuration**: User navigates to tabs to configure either AI transformations (writing prompts for columns) or deterministic checks (selecting checkboxes for missing values, duplicates, etc.).
5. **Background processing**: User initiates the scan. The backend queues the job and processes it using thread pools.
6. **Monitoring**: The UI polls the backend, displaying a real-time progress bar.
7. **Reports / Export**: The user downloads the resulting Excel file, which includes new AI-generated columns or color-coded cells indicating data quality issues.

---

# System Architecture

- **Frontend**: Vanilla HTML/CSS/JS with Jinja2 templates. Kept lightweight without heavy JS frameworks to maintain a simple, robust footprint.
- **Backend**: Python Flask handling API endpoints, routing, and in-memory session management.
- **Workers**: Python `threading` and `concurrent.futures.ThreadPoolExecutor` manage job queues, parallelize LLM inference, and prevent UI blocking.
- **AI**: Local Ollama instance serving models locally.
- **Data Processing**: Pandas handles all in-memory data manipulation, cleaning, and Excel generation. Scikit-learn handles machine learning logic.
- **Storage**: Ephemeral local filesystem (OS temp directory) for file uploads and output generation. Memory for active DataFrames.

---

# Folder Purpose

- `/` (Root): Contains core application logic (`app.py`, `routes.py`, `routes2.py`) and environment files.
- `/templates`: HTML views rendered by Flask.
- `/static`: CSS stylesheets and Vanilla JavaScript files for UI interactivity.
- `/ai scanner duck` & `/duckdb`: Experimental directories, likely exploring DuckDB integration for out-of-core data processing to replace in-memory Pandas.
- `/ollama`: Resources or scripts related to managing the local LLM environment.
- `/Images`: Static assets utilized primarily for documentation (README).

---

# Data Flow

User Upload
↓
Flask Route (`/`) saves file to Temp Directory
↓
Robust File Loader (tries multiple encodings/delimiters)
↓
Pandas DataFrame loaded into Memory (`session_state`)
↓
User requests Action (AI prompt or Data Checks)
↓
Job queued in Background Thread
↓
Data processed by Pandas / Scikit-learn / Ollama API
↓
Results appended as new columns or summary metrics
↓
Exported to conditionally formatted Excel file via OpenPyXL
↓
Client downloads file via Route (`/download_*`)

---

# AI Components

- **Models**: Gemma3 (4b-it-qat, 12b) and Phi3 (3.8b) run locally via Ollama.
- **Prompt Templates**: Strongly typed system instructions force models to act as expert data analysts. When replacing multiple columns, the system enforces a strict JSON mapping output.
- **Agents**: Currently implemented as highly parallelized, single-step prompt-response loops over individual rows, rather than autonomous, multi-step reasoning agents.
- **Inference**: Handled via `concurrent.futures.ThreadPoolExecutor` (max 8 workers) making simultaneous REST API calls to the local Ollama instance.
- **Semantic Search**: Used in `/ai_column_select` to let the LLM guess which spreadsheet columns match a user's natural language reference based on headers and sample values.

---

# Database Design

The application currently operates entirely in-memory using Python dictionaries (`session_state` and `file_dataframes`) to store Pandas DataFrames.
- There is no persistent relational database (SQL) for user data, reinforcing the ephemeral, privacy-first nature of the tool. 
- While DuckDB artifacts exist in the project structure, they are not currently the primary data engine in the active routing logic.
- State is tied to the running Flask instance. Restarting the server clears all data.

---

# API Design

- **Core Application**:
  - `/` (GET/POST): Upload files, reset session state, render main UI.
  - `/preview` (GET): Retrieve the first 50 rows of data for frontend rendering.
- **Background Jobs (AI)**:
  - `/start_ai` (POST): Queues an LLM processing job for specific columns.
  - `/job_progress/<job_id>` (GET): Short-polling endpoint for job completion percentage.
  - `/job_list` (GET): Returns status of all background jobs.
- **Data Checks (Deterministic & ML)**:
  - `/data_checks2` (POST): Triggers rule-based validation and Random Forest outlier checks, generating an Excel file with conditional highlighting.
- **Downloads & Editing**:
  - `/download*` (GET): Various endpoints to retrieve processed files.
  - `/edit/*` (POST): Endpoints for quick data modifications (cleaning empty fields, redefining headers, clearing rows).

---

# Configuration

- Hardcoded configuration in `app.py`.
- `UPLOAD_FOLDER` utilizes the OS temporary directory (`tempfile.gettempdir()`).
- Secret keys are hardcoded (intended for local desktop use).
- Model selection dynamically fetches available models from the local Ollama API, falling back to a hardcoded list if the API fails.

---

# Security Model

- **Privacy decisions**: The core security feature is the localized architecture. By completely bypassing third-party cloud APIs, it inherently protects sensitive enterprise data.
- **Authentication & Authorization**: None. The application is designed to run on `localhost` for a single user.
- **Input sanitization**: Basic path sanitization (`_sanitize_for_download`) is implemented to prevent directory traversal attacks during file downloads.

---

# Important Algorithms

- **Robust CSV Loader**: Instead of failing on messy CSVs, the loader loops through multiple encodings (`utf-8`, `cp1252`, `latin1`) and delimiters (`,`, `;`, `\t`, `|`), utilizing sniffing and shape verification to gracefully handle legacy data exports.
- **Synthetic Random Forest Outlier Detection**: For anomaly detection, the system auto-selects numeric features, synthesizes "fake" uniform data across the feature space, and trains a Random Forest to classify real vs. fake data. Real rows that the model strongly suspects are fake (low probability of being real) are flagged as outliers.

---

# Business Rules

- **Empty Value Canonicalization**: Empty strings, whitespace-only strings, and textual representations like "NaN", "N/A", "null" (case-insensitive) are mathematically treated as true missing values across all validation checks.
- **Highlighting Hierarchy**: When exporting Excel files, conditional formatting prioritizes issues: Outliers > Duplicates > Mixed Types > Format Issues.
- **Concurrency Limits**: AI tasks utilize thread pools, but a global lock (`session_state["ai_running"]`) prevents overlapping AI executions on the same dataset to manage memory and local compute limits.

---

# Dependencies

- `flask`: Lightweight web serving and routing.
- `pandas` & `numpy`: Core data manipulation and in-memory storage.
- `ollama`: Interface to the local LLM server.
- `scikit-learn`: Random Forest algorithms for outlier detection.
- `openpyxl`: Excel file generation, writing, and complex conditional formatting.
- `Orange3`: Mentioned in imports/README; likely legacy dependency for older ML workflows.

---

# Technical Decisions

- **In-Memory Pandas over SQL**: Chosen for rapid prototyping, rich vectorized data manipulation, and seamless integration with Scikit-learn, prioritizing speed over scale.
- **Local Ollama over OpenAI APIs**: Mandated by the privacy-first product philosophy.
- **Flask over Node/React**: Keeps the entire stack in Python, eliminating the need for a complex API bridge to utilize Pandas and ML libraries.
- **Short Polling over WebSockets**: JS polling against `/progress` endpoints is used instead of WebSockets/Redis/Celery to keep infrastructure requirements strictly at zero, ensuring easy local deployment.

---

# Performance Considerations

- **Parallelization**: Python `ThreadPoolExecutor` is used to parallelize LLM inference across rows.
- **Lazy Loading**: AI transforms can be restricted using a `row_limit` to test prompts before committing to a full dataset run.
- **Memory Optimization**: Dataframes are deduplicated prior to data checks to save memory.
- **Limitations**: Because the architecture relies on in-memory Pandas, the application is susceptible to Out of Memory (OOM) errors on extremely large files (e.g., >2GB) depending on the host machine's RAM.
- **Compute Bound**: LLM processing speed is entirely dictated by the local machine's GPU/CPU capabilities.

---

# Current Limitations

- **Global State**: UI state and DataFrames are stored in a global `session_state` dictionary. This is not thread-safe for multiple concurrent users and firmly restricts the app to a single-user local deployment.
- **Ephemeral Storage**: Closing the application or restarting the server loses all uploaded data and workflow progress.
- **No Agentic Reasoning**: The AI currently acts as a direct function mapped over rows, rather than an agent that can query, filter, or autonomously iterate on the entire dataset.

---

# Future Roadmap

- **Out-of-Core Processing**: Migrating the core data engine from Pandas to DuckDB to handle datasets larger than local RAM.
- **Enterprise Multi-User**: Refactoring the global state into a Redis-backed session model with authentication for deployment on secure internal servers.
- **Automated Quality Reports**: Generating comprehensive PDF/HTML data health dashboards.
- **Python Sandbox Agents**: Allowing the LLM to write and execute Python code in a secure sandbox to perform complex, multi-step data transformations rather than relying purely on text-based prompt responses.

---

# Developer Notes

- **Hidden Assumptions**: The code assumes it is running on `localhost` for a single user. Do not attempt to deploy this as a public SaaS without completely rewriting the session management and file handling logic.
- **Architecture Patterns**: The backend is functionally split. `routes.py` manages probabilistic, LLM-driven workflows and the job queue. `routes2.py` manages deterministic, programmatic validation (Pandas/Sklearn). 
- **Coding Conventions**: The codebase is pragmatic and data-science-oriented. You will find extensive `try/except` blocks designed to gracefully degrade features (especially around ML or Excel formatting) rather than crashing the user experience.

---

# How to Continue Development

**If you are an AI agent continuing this work, you must know:**

1. **State Management**: Do NOT try to refactor `session_state` or `file_dataframes` unless the explicit goal is to add multi-user support. The current monolithic state is intentional for a lightweight local tool.
2. **Strict Boundary**: Maintain the boundary between deterministic rules (`routes2.py`) and probabilistic AI (`routes.py`). 
3. **No Cloud APIs**: NEVER introduce external APIs (OpenAI, Anthropic, AWS) for data processing. The core value proposition is local execution. Any new models must run through Ollama or local HuggingFace inferences.
4. **Resiliency over Purity**: The robust CSV loader and the graceful fallbacks in the ML outlier detection (handling cases where Sklearn isn't available or features aren't numeric) are critical. Maintain this philosophy: the app should always return a result, even if it has to skip advanced formatting or checks.
