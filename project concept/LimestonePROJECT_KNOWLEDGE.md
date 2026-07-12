# Limestone V2

Limestone V2 is a desktop-based data operations and reconciliation platform designed to automate the process of cross-referencing and cleaning large, disparate datasets (such as CMS logs and Switch transaction records). By providing an intuitive GUI wrapped around powerful Pandas-driven data manipulation, it allows operational teams to easily upload, clean, deduplicate, and reconcile financial or transactional data without writing code.

---

# Elevator Pitch

Limestone V2 bridges the gap between raw data dumps and clean, actionable reconciliation reports. Built for data analysts and operational teams, it provides a local-first, privacy-respecting desktop application to ingest records from multiple sources (like CMS and Switch), clean them using built-in or custom rules, and automatically match them to find discrepancies. By replacing manual Excel cross-referencing with automated, profile-based workflows and interactive dashboards, Limestone saves hours of tedious labor and drastically reduces human error in financial reconciliation.

---

# Problem Statement

Financial and operational teams often have to reconcile thousands of transaction records daily across multiple independent systems (e.g., frontend sales vs backend payment gateways). Doing this manually in Excel is slow, error-prone, and unsustainable. Limestone solves the problem of manual data reconciliation by providing an automated, repeatable, and visual platform to detect duplicates, apply data-cleaning formulas, and highlight unmatched or discrepant records.

---

# Target Users

**Primary users**: Data Analysts, Operations Associates, and Accountants who handle daily reconciliation of transaction logs.

**Secondary users**: Department Managers who need to view high-level dashboards and summaries of reconciliation health over time.

**Admin users**: System Administrators or Team Leads who manage user access, software licensing, and configure global reconciliation profiles.

---

# Core Vision

To become the standard local-first data reconciliation utility for organizations, offering enterprise-grade data matching and reporting capabilities without the overhead of complex cloud infrastructure. The vision is to make complex data transformation as simple as clicking a button.

---

# Product Philosophy

- **Local-First & Privacy-First**: All data processing is done locally via Pandas on the user's machine, ensuring sensitive financial data never leaves the corporate network.
- **Automation-first**: Save complex configurations as "Profiles" so daily tasks become one-click operations.
- **No-Code Data Engineering**: Provide users with Excel-like simplicity but Pandas-level power for data cleaning and transformation.
- **Visual Feedback**: Real-time dashboards and charts instead of just raw CSV outputs.

---

# Key Features

### 1. Multi-Source Reconciliation Engine
- **Purpose**: Cross-reference two distinct datasets to identify matched and unmatched records.
- **Inputs**: Cleaned datasets (e.g., CMS and Switch).
- **Outputs**: Excel/CSV files categorizing data into "Matched" and "Unmatched" sheets, along with match levels.
- **Dependencies**: Pandas, XlsxWriter.
- **Future improvements**: Fuzzy matching, machine-learning-based anomaly detection.

### 2. Interactive Data Cleaning & Transformation
- **Purpose**: Pre-process raw data to standardize formats before reconciliation.
- **Inputs**: Raw CSV/Excel files.
- **Outputs**: Cleaned DataFrames ready for reconciliation.
- **Dependencies**: Pandas, CustomTkinter (for UI).
- **Future improvements**: AI-driven column mapping and automatic data-type detection.

### 3. Intelligent Deduplication
- **Purpose**: Identify and merge or eliminate duplicate records within a single dataset.
- **Inputs**: Single raw dataset.
- **Outputs**: Deduplicated dataset.
- **Dependencies**: Pandas.
- **Future improvements**: Advanced conflict resolution rules for merging rows.

### 4. Interactive Dashboards & Analytics
- **Purpose**: Provide visual insights into reconciliation health.
- **Inputs**: Historical reconciliation JSON logs.
- **Outputs**: Matplotlib graphs, summary statistics.
- **Dependencies**: Matplotlib, JSON.
- **Future improvements**: Exportable PDF dashboard reports.

### 5. Profile-Based Workflow
- **Purpose**: Allow users to save recurring configurations.
- **Inputs**: User configurations (columns mapped, formulas applied).
- **Outputs**: JSON profile (`reconciliations.json`).
- **Dependencies**: JSON module.
- **Future improvements**: Shareable profiles across the network.

---

# User Journey

1. **User opens app**: Launches via `launcher.py` which shows a splash screen.
2. **Authentication**: User logs in via `login_frame.py` (which checks a centralized Google Drive file for valid license/credentials).
3. **Dashboard**: User lands on `main_dashboard.py` and sees historical stats and past reconciliation profiles.
4. **Data Ingest**: User starts a new reconciliation, uploading files (e.g., CMS and Switch data).
5. **Data Cleaning**: User applies formulas (Sum, Replace Character, Concat, Date format) via the UI (`window_cleaning_stable.py`).
6. **Deduplication**: User runs the deduplication engine if necessary (`frame_deduplicate_stable.py`).
7. **Reconciliation**: System cross-references the datasets based on defined columns.
8. **Reports**: System generates an Excel report with Matched/Unmatched sheets and updates the JSON log (`reports_generate.py`).

---

# System Architecture

- **Frontend**: Built entirely with `CustomTkinter` and `Tkinter` to provide a modern, standalone desktop GUI.
- **Backend**: Python-based monolithic architecture. All logic runs in the main process (with some UI tasks threaded).
- **Database**: Local file system. Uses JSON files (`reconciliations.json`, `temp_file_paths.json`, `cleaning_history.json`) for state and metadata, and local directories (`C:\Users\<User>\AppData\Local\lms2_database`) for caching data.
- **Data Engine**: `Pandas` is used as the in-memory data processing engine.

**Responsibilities**:
- **UI Layer**: Manages user input, themes, and navigation between frames.
- **Cleaning/Deduplication Layer**: Translates user UI clicks into Pandas DataFrame operations.
- **Reconciliation Layer**: Executes dataframe merges/joins and generates output reports.

---

# Folder Purpose

- `/` (Root): Main application entry points (`launcher.py`, `login_frame.py`, `main_dashboard.py`) and core logic modules (`window_cleaning_stable.py`, `main_v1_2_cleaning_stable.py`).
- `/mini_frames`: Modular UI components for specific sub-tasks (e.g., file selection, column editing, custom tooltips).
- `/files` & `/assets`: Static assets, images, and splash screens used in the UI.
- `/loading_window`: Scripts and assets specifically for the startup sequence.
- `/Output`: Default directory for generated reconciliation Excel/CSV reports.

---

# Data Flow

User (Uploads CSV/Excel) 
↓ 
Pandas DataFrame (In-Memory) 
↓ 
UI Formulas (User selects operations like "Concat" or "Date Formatter") 
↓ 
Pandas Transformation (Data is cleaned) 
↓ 
Reconciliation Engine (Two DataFrames are joined/compared) 
↓ 
Report Generator (Results written to `.xlsx` via `xlsxwriter`) 
↓ 
Local JSON Log (Metadata about the run is saved for the Dashboard)

---

# AI Components

*Currently, this project does not integrate AI components (no LLMs, Vector DBs, or RAG). It relies strictly on deterministic data processing.*

---

# Database Design

This system relies on **Local JSON Files** rather than a traditional SQL database.

- **`reconciliations.json`**: Acts as the main table. Stores profiles of past reconciliations (Name, Type, Start Date, End Date, Data Sources).
- **`reconciliation_report.json`**: Stores the metadata of the most recent report (Total Matched, Total Unmatched, File Path).
- **`custom_theme1.json` / `default_theme.json`**: Configuration state for UI styling.

*Data flows in and out of memory via Pandas DataFrames, and persistent state is purely configuration metadata.*

---

# API Design

*As a local desktop application, it does not serve APIs.*

**External API Consumption**:
- **Authentication Check**: `login_frame.py` makes a `requests.get` call to a hardcoded Google Drive URL to fetch valid license keys/credentials.

---

# Configuration

- **Environment Settings**: The app detects the Windows user profile (`os.getenv('USERPROFILE')` and `os.getenv('LOCALAPPDATA')`) to dynamically create configuration folders (`Documents/LimestoneV2/`).
- **Feature Flags**: Managed via different entry files (e.g., `_beta` vs `_stable` files).
- **Themes**: Loaded at runtime via JSON configuration.

---

# Security Model

- **Authentication**: Simple credential check against a centrally hosted file (Google Drive text file).
- **Privacy**: High privacy by design. Because it's a desktop app utilizing Pandas locally, no proprietary transactional data is sent to external servers.
- **Limitations**: The current authentication model (fetching a public Google Drive file) is easily bypassed via reverse engineering.

---

# Important Algorithms

- **Reconciliation Matching**: Relies on relational joins (Pandas `merge` and boolean masking) to find records that exist in Source A and Source B, categorizing them into "Matched" and "Unmatched".
- **Deduplication Logic**: Uses Pandas `drop_duplicates` combined with custom user-defined aggregations (e.g., summing monetary columns for duplicate transaction IDs).

---

# Business Rules

- **Level-Based Matching**: Matches are categorized by "Levels" depending on how strictly the data aligned (e.g., Exact match vs Partial match).
- **Source Agnosticism**: The system assumes one source is the "Truth" (e.g., Switch) and one is the "Record" (e.g., CMS), focusing heavily on where the gaps are.

---

# Dependencies

- **`customtkinter`**: Modern, dark-mode capable UI elements overriding standard Tkinter.
- **`pandas`**: The core workhorse for all data manipulation.
- **`xlsxwriter`**: High-performance Excel file generation for reports.
- **`matplotlib`**: Rendering charts and graphs directly into the Tkinter dashboard.
- **`requests`**: Fetching remote authentication credentials.

---

# Technical Decisions

- **Why CustomTkinter?**: Standard Tkinter looks outdated; CustomTkinter provides a modern, sleek interface without the overhead of learning a complex web framework (like Electron) for a Python team.
- **Why Pandas?**: It is the industry standard for tabular data manipulation in Python, capable of handling millions of rows efficiently in memory.
- **Why Local Desktop App?**: Financial data is sensitive. Processing it locally removes the need for complex compliance (SOC2/GDPR) associated with uploading PII/Financial records to a SaaS cloud.

---

# Performance Considerations

- **Memory Bound**: Because Pandas loads datasets fully into RAM, the application's capacity is tied directly to the user's local machine memory. Very large datasets (multiple gigabytes) may cause crashes.
- **Threading**: The application uses basic `threading` for loading screens to prevent the UI from freezing, but heavily relies on the main thread for data processing.

---

# Current Limitations

- **Authentication**: Using Google Drive for license validation is insecure and brittle.
- **Code Duplication**: There are many `_beta`, `copy`, and duplicate files in the root directory indicating technical debt and a lack of Git branching best practices.
- **Scalability**: Limited to local RAM capacity; not suitable for big data (10M+ rows) without chunking.

---

# Future Roadmap

- **Architecture Cleanup**: Removing all temporary/beta files and organizing modules into clear `/core`, `/ui`, `/data` directories.
- **Database Integration**: Moving from JSON files to a local SQLite database (`lms2_database`) for more robust querying of past reconciliation histories.
- **Chunked Processing**: Implementing Pandas chunking to process massive files without running out of memory.

---

# Developer Notes

- **Conventions**: The UI classes heavily rely on passing `root` and callback functions (like `navigate_to_panel`) between frames to manage state.
- **Technical Debt**: The root folder acts as a dumping ground. Developers must ensure they are editing `_stable` files rather than `_beta` or `copy` files.
- **Data Persistence**: Always refer to `os.path.join(os.getenv('USERPROFILE'), 'Documents', 'LimestoneV2')` for saving state, ensuring cross-machine compatibility on Windows.

---

# How to Continue Development

**If you are an AI or new developer taking over this project:**

1. **Understand the UI Pattern**: State is managed via Tkinter frames being destroyed and recreated. Understand how `main_dashboard.py` orchestrates the different views.
2. **Never Violate Privacy**: Do not add telemetry or cloud syncing for the data files. The local-first nature is a core product pillar.
3. **Stick to Pandas**: Do not introduce custom iterative loops for data manipulation. Always translate user requests into vectorized Pandas operations for performance.
4. **Cleanup First**: Before adding new features, consolidate the various `window_cleaning*.py` and `main_v1_2*.py` files to understand the single source of truth.
5. **UI Consistency**: Continue using `customtkinter` with the centralized `custom_theme1.json` to maintain the modern aesthetic.
