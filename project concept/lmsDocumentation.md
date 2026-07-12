# Limestone Reconciliation - Full Replication Specification

This document serves as the comprehensive architectural and technical specification of the **Limestone Reconciliation** application. It is designed to provide an AI agent or developer with the exact blueprints required to recreate, clone, or rebuild the software from scratch.

## 1. System Architecture & Tech Stack
- **Language**: Python 3.x
- **GUI Framework**: `customtkinter` (Modern Tkinter) alongside standard `tkinter` for legacy dialogues.
- **Data Manipulation**: `pandas` and `numpy`.
- **Report Generation**: `fpdf` for generating PDF reports.
- **Data Persistence**: Local JSON files (No SQL database used).
- **Styling**: Relies on a centralized theme file (`custom_theme1.json` and `default_theme.json`).

## 2. Directory Structure & AppData Storage
The application does not use a traditional database. Instead, it relies on local JSON files stored in the user's `Documents` folder to persist state and history.

**Configuration Directory Path**:
`C:\Users\<Username>\Documents\LimestoneV2\`

**Core JSON Databases**:
1. `reconciliations.json`: Stores active and past reconciliation configurations and mappings.
2. `reconciliation_report.json`: Stores the historical log of generated reports (Report ID, Date, Match Counts).
3. `reconciliation_types.json`: Stores user-defined templates and rules for matching.
4. `deep-analysis.json`: Caches analytical outputs.
5. `temp_file_paths.json`: Caches recent file paths.

*Note: The app checks for the existence of this folder on startup (`ensure_files_exist()` in `master_dashboard.py`) and creates these JSON files as empty arrays `[]` if missing.*

## 3. Core Modules & Execution Flow

### Step 1: The Launcher (`launcher.py`)
- **Class**: `Application(CTk)`
- **Role**: Entry point of the software. Displays a splash screen with a progress bar.
- **Behavior**: It uses a threading mechanism to animate the progress bar and asynchronously calls `subprocess.Popen` to execute the `login_frame.py` (or `.exe` if compiled). It destroys itself after a 2-second delay.

### Step 2: Authentication (`login_frame.py`)
- **Class**: `LoginWindow(CTk)`
- **Role**: Handles user sign-in and license validation.
- **Behavior**: 
  - Validates credentials dynamically by making a `requests.get()` call to a hardcoded Google Drive URL (fetching a text file containing key-value pairs of credentials).
  - Contains a multi-step frame transition (Welcome -> Sign Up -> Company Details -> License Validated -> Admin Account Creation -> Sign In).
  - On successful login, transitions to the `MasterDashboard`.

### Step 3: Master Dashboard (`master_dashboard.py`)
- **Class**: `MasterDashboard(ctk.CTk)`
- **Role**: The main application shell hosting the navigation menu and sub-frames.
- **Key Features**:
  - **Navigation**: Sidebar with tabs: `['Home', 'Reconciliation', 'Reports', 'Admin Console', 'Help']`.
  - **Global Top Bar**: Displays Company Name, a dropdown for Business Unit, current Date/Time, User Type (Admin), and two utility toggles:
    - **Dark/Light Mode**: Uses `ctk.set_appearance_mode()`.
    - **UI Scaling**: Uses `ctk.set_widget_scaling()` with `+` and `-` buttons to scale the UI dynamically between 0.1 and 2.0.

### Step 4: Data Cleaning / Excel Editor (`window_cleaning_stable.py` & `main_v1_2_cleaning.py`)
- **Role**: Allows users to import `.xlsx` or `.csv` files into a `pandas.DataFrame` and visually apply transformations without code.
- **UI Component**: `FormulaButtonFrame`.
- **Predefined Formulas**:
  1. **Sum**: Calculates column totals.
  2. **Delete Column**: Drops a pandas column.
  3. **Replace Character**: String replacement in a column.
  4. **Remove Character**: Regex or static string removal.
  5. **Text Filter (Advanced)**: Row filtering based on conditions.
  6. **Special Merge**: Custom combination logic.
- **User-Defined Formulas**:
  1. **Math Operation**: Add/Subtract/Multiply/Divide across columns.
  2. **L-R/LRB**: String slicing (Left, Right, Both).
  3. **Absolute**: Converts numerical columns to `abs()`.
  4. **Duplicate**: Duplicates a column.
  5. **Date / Time / Date&Time**: Casts columns to `datetime` objects with specific string formatting.
  6. **Split Column**: Splits a column based on a delimiter.
  7. **Concat**: Merges multiple columns.
- **Exporting**: Users can hit "Export Data" to send the manipulated DataFrame back to the Reconciliation Panel, or "Save to CSV" to write directly to disk.

### Step 5: Core Reconciliation Engine
- **Role**: The core business logic for matching two disparate datasets.
- **Behavior**: 
  - Loads two DataFrames (Data Source 1 and Data Source 2).
  - Uses `reconciliation_types.json` to define which columns to join/merge on (Primary Keys).
  - Performs a pandas `merge` (Left, Right, Outer, or Inner depending on user config) to identify:
    - **Matched Records**: Records existing in both datasets.
    - **Unmatched Records**: Records existing only in Source 1 or Source 2.
  - Calculations include absolute variances and percentage differences.

### Step 6: Deduplication Engine (`frame_deduplicate.py`)
- **Class**: `TransactionMergeApp`
- **Role**: Identifies duplicate rows within a single dataset.
- **Behavior**: Uses pandas `.duplicated()` and grouping to find transactions with identical keys (e.g., Transaction ID, Date, Amount) and merges or flags them.

### Step 7: Reporting System (`reports_table.py` & `reports_create.py`)
- **Role**: Displays a historical log of reconciliations and generates PDFs.
- **UI Component**: `DisplayTableApp` inside a `CTkScrollableFrame`.
- **Data Source**: Reads from `reconciliation_report.json`.
- **Data Columns**: `ReportID`, `Date`, `Time`, `Reconciliation Name`, `Type`, `Data Source 1`, `Data Source 2`, `Total Data`, `Matched`, `Unmatched`, `Reconciliation File`.
- **Features**:
  - Dropdown filters (`ttk.Combobox`) dynamically created for every column header to filter rows.
  - Pagination to handle large historical logs.
  - Integration with `fpdf` to export the summary of a specific Report ID into a formatted `Reconciliation_Report.pdf`.

## 4. UI/UX Design Guidelines (Replication Rules)
To build an exact replica, an AI agent must follow these UI rules:
1. **Window Sizing**: Base window minimum sizes are strictly enforced (e.g., `1580x900` for the Master Dashboard).
2. **Tooltips**: The app uses custom hover tooltips (`CToolTip` and custom `Tooltip` classes) extensively on buttons and truncated dropdown texts.
3. **Theming**: A `custom_theme1.json` dictates `button_styles` like `corner_radius`, `fg_color`, and `text_color`. CustomTkinter's `set_default_color_theme()` is heavily utilized.
4. **Dynamic Rendering**: Avoid hardcoding widget placements. Use `.pack(expand=True, fill='both')` and grid weights heavily to ensure the UI scales when the user clicks the scaling `+`/`-` buttons.

## 5. AI Replication Data Schemas & State Management

To successfully rebuild this application without hallucination, an AI agent must strictly adhere to the following schemas and state flows.

### 5.1 JSON Database Schemas

**1. `reconciliations.json` (Configuration State)**
```json
[
  {
    "reconciliation_id": "REC-10293",
    "name": "Bank vs Ledger Q1",
    "type": "Financial",
    "source_1_path": "C:/path/to/bank_statement.xlsx",
    "source_2_path": "C:/path/to/ledger.csv",
    "primary_key_1": "Transaction_ID",
    "primary_key_2": "Ref_Number",
    "created_at": "2024-05-20T14:32:00Z"
  }
]
```

**2. `reconciliation_report.json` (Historical Log)**
```json
[
  {
    "ReportID": "REP-9982",
    "Date": "2024-05-20",
    "Time": "14:35:12",
    "Reconciliation Name": "Bank vs Ledger Q1",
    "Type": "Financial",
    "Data Source 1": "bank_statement.xlsx",
    "Data Source 2": "ledger.csv",
    "Total Data": 1500,
    "Matched": 1495,
    "Unmatched": 5,
    "Reconciliation File": "C:/path/to/reports/REP-9982.xlsx"
  }
]
```

**3. `reconciliation_types.json` (Template Rules)**
```json
[
  {
    "type_name": "Financial",
    "suggested_keys": ["amount", "date", "id", "ref"],
    "tolerance_logic": "exact_match",
    "color_coding": {"match": "#00FF00", "mismatch": "#FF0000"}
  }
]
```

### 5.2 State Management Flow
- **Data Ingestion**: Files are loaded directly into `pandas.DataFrame` objects.
- **Inter-Module Transfer**: When transferring data from the *Data Cleaning module* to the *Core Engine*, the application does **not** rely on disk writing (unless the user explicitly clicks "Save to CSV"). Instead, it passes the `DataFrame` reference in-memory between Tkinter frame classes using controller methods (e.g., `self.controller.pass_data_to_reconciliation(df)`).
- **Session State**: Global state (like the currently logged-in user or active business unit) is held in a singleton class or the `MasterDashboard` root object to prevent prop-drilling across dozens of UI components.

### 5.3 Exact Theming Specifications (`custom_theme1.json`)
For the UI to visually match the original design, the custom theme must enforce these properties:
```json
{
  "CTkButton": {
    "corner_radius": 8,
    "border_width": 0,
    "fg_color": ["#3B8ED0", "#1F6AA5"],
    "hover_color": ["#36719F", "#144870"],
    "text_color": ["#DCE4EE", "#DCE4EE"]
  },
  "CTkFrame": {
    "corner_radius": 10,
    "fg_color": ["#F2F2F2", "#2B2B2B"]
  }
}
```

### 5.4 Authentication Mock Schema
The `requests.get()` call for login validation hits a simple text file hosted on Google Drive (or similar raw text host). The expected return body must be exactly parsable as key-value pairs (or JSON, if upgraded):
```json
{
  "valid_licenses": ["LIC-ABCD-1234", "LIC-WXYZ-9876"],
  "active_users": {
    "admin": "hash256_password_string",
    "user1": "hash256_password_string"
  }
}
```
*Note: If the request fails, the application must gracefully fail to a "Network Error / Offline Mode" rather than crashing.*
