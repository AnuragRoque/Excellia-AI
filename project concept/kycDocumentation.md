# KYC Data Automation - Full Replication Specification

This document serves as the comprehensive architectural and technical specification of the **KYC Data Automation** toolkit. It provides the exact logic, algorithms, and endpoints required for an AI agent or developer to replicate the data pipelines, OCR processors, and utility scripts.

## 1. Core OCR Pipelines (Jupyter Notebooks)
The OCR pipelines are structured to handle low-resolution and noisy document scans of Indian identification cards.

### Aadhaar OCR (`Aadhaar_OCR_Code_v1/v2/v3...`)
- **Objective**: Extract structured data (Name, DOB, Aadhaar Number, Gender, Address) from Aadhaar cards.
- **Tools Used**: Google Cloud Vision API / Tesseract for raw text extraction.
- **Logic Progression**:
  - `v1 / v2`: Relies heavily on static Regular Expressions (Regex) to parse fields like `[0-9]{4}\s[0-9]{4}\s[0-9]{4}` for Aadhaar numbers or `DOB:\s*(.*)` for dates.
  - `v3 (OCR+Local LLM)`: Upgrades the pipeline by pushing the raw, noisy OCR text into a Local LLM (Ollama). The LLM is prompted to strictly format the raw text into a standard JSON schema, correcting minor OCR errors dynamically instead of relying purely on brittle Regex.

### Corporate OCR (`PAN_Incorporation_OCR_...` & `GST_Certificate_OCR_...`)
- **Objective**: Extract business-critical information (Company Name, Incorporation Date, PAN Number, GSTIN).
- **Format**: Similar pipeline structure as Aadhaar, tailored with regex patterns for specific alphanumeric IDs (e.g., PAN regex `[A-Z]{5}[0-9]{4}[A-Z]{1}`).

## 2. Advanced Utility Scripts

### Name Match Percentage Bulk LLM (`Name Match Percentage Bulk LLM.py`)
- **Objective**: Compare user-entered names against a database of IDs (e.g., OYO IDs) and return a confidence score identifying if they represent the same person.
- **File Input**: Reads an `.xlsx` file containing `OYO ID` and `Operator Name`. Groups entries by `OYO ID` and compares combinations (`nC2`) of names.
- **Algorithm (Hybrid Matcher)**:
  1. **Normalization**: Converts text to lowercase, strips punctuation via `re.sub(r"[^\w\s]", "", text)`, and collapses multiple spaces.
  2. **Base Similarity**: Uses `difflib.SequenceMatcher` to generate a base ratio score (0-100%).
  3. **LLM Validation**: If the sequence similarity crosses the `SEQ_THRESHOLD` (set to `50.0%`), it sends the two names to a local **Ollama** instance.
     - **Endpoint**: `http://localhost:11434/api/generate`
     - **Model**: `mistral:latest` (or similar).
     - **Prompt Strategy**: Instructs the model to act as a "strict name-matching fraud screening assistant" and output valid JSON with `status` ("match" / "no_match"), `match_percent` (0-100), and `reason`.
- **Output**: Generates a new Excel file containing the ID, the two names, the sequence similarity, and the LLM's final verdict and reasoning.

### Name Match Percentage Bulk ML (`Name Match Percentage Bulk ML.py`)
- **Objective**: A faster, offline version of the name matcher without LLM dependencies.
- **Algorithm**: Relies entirely on the `difflib.SequenceMatcher(None, a, b).ratio() * 100` algorithm post-normalization to generate a `similarity_percent`.

### Excel Sheet Cleaner & Repair (`Excel Sheet Cleaner & Repair.py`)
- **UI Framework**: Built with `customtkinter`.
- **Functionality**:
  - Uses `pandas` to read Excel/CSV files.
  - Allows the user to select specific sheets.
  - **Cleaning Logic**:
    - Drops completely empty rows/columns (`df.dropna(how="all")`).
    - Strips the first `N` rows or columns to eliminate bad metadata or headers before processing.
  - Exports the cleaned DataFrame back to a new file or overwrites the existing one.

### Quantity Splitter & Unique Generator (`Quantity Splitter & Unique Generator.py`)
- **UI Framework**: Standard `tkinter` dialogues.
- **Functionality**:
  - Processes a CSV iteratively using Python's built-in `csv` module.
  - Users define a `column_index`.
  - **Logic**: Tracks existing identifiers using a `set()`. If a base identifier exists, it appends an incrementing suffix (e.g., `-1`, `-2`) using a `while` loop until a globally unique identifier is found.

### Image Compressor Offline Secured GUI (`Image_Compressor_Offline_Secured_GUI.py`)
- **Functionality**: Likely uses the `Pillow` (PIL) library to reduce image resolution and quality locally, ensuring PII (Personally Identifiable Information) on KYC documents is never transmitted externally for compression.

## 3. Replication Requirements for an AI Agent
To rebuild this KYC suite from scratch, an AI must:
1. Initialize a Python environment with `pandas`, `customtkinter`, `opencv-python`, `pytesseract`, and `google-cloud-vision`.
2. Setup a local instance of **Ollama** serving a lightweight instruction model (like Mistral or Llama 3) on port `11434`.
3. Implement hybrid matching by combining deterministic algorithms (`SequenceMatcher`) for fast filtering, followed by LLM-based semantic reasoning for edge cases.
4. Utilize `pandas` heavily for bulk data manipulation (cleaning, dropping NaNs, reading Excel sheets).

## 4. AI Replication Data Schemas & Prompt Engineering

To successfully rebuild this application without hallucination, an AI agent must strictly adhere to the following prompts, schemas, and architectural constraints.

### 4.1 LLM Prompt Blueprints
The system's reliability hinges on exact LLM prompting. For the Name Matching pipeline, the following prompt structure must be used in the Ollama API call:

**System Prompt:**
> "You are a strict fraud-detection assistant specializing in Indian names. Your ONLY job is to compare Name A and Name B and determine if they belong to the exact same person. Ignore minor spelling mistakes or missing middle names. You must return your analysis strictly in valid JSON format. Do not include markdown formatting or extra text."

**User Prompt:**
> "Name A: {name_a}\nName B: {name_b}\nDetermine if these match. Return JSON."

### 4.2 LLM JSON Output Schema (Pydantic/JSON)
To ensure the Python scripts do not crash when parsing the Ollama response, the LLM must be forced to output exactly this schema:
```json
{
  "status": "match", // Must be strictly "match" or "no_match"
  "match_percent": 85, // Integer between 0 and 100
  "reason": "Name B is a common abbreviation of Name A." // Max 1 sentence
}
```
*Note: The Python code must include a `json.loads(response)` wrapped in a try/except block to handle occasional LLM formatting errors, defaulting to `{"status": "error", "match_percent": 0, "reason": "parsing failed"}` on failure.*

### 4.3 Comprehensive Regex Dictionary
The initial (v1/v2) pipelines and fallback mechanisms for OCR rely on these exact regex patterns:
- **Aadhaar Number**: `r"\b\d{4}\s?\d{4}\s?\d{4}\b"`
- **PAN Number**: `r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b"`
- **GSTIN**: `r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b"`
- **Date of Birth (DOB)**: `r"(?:DOB|Year of Birth)[:\-\s]*([0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{4})"`
- **Gender**: `r"\b(Male|Female|Transgender)\b"`

### 4.4 Project Structure Constraints
If rebuilding, the repository must be logically split into two sub-directories to separate heavy dependencies (like Jupyter/TensorFlow/Vision API) from the lightweight utility scripts:
1. `/ocr_pipelines/`: Contains all Jupyter Notebooks, `tesseract` binaries, and Google Cloud JSON keys.
2. `/utility_tools/`: Contains all standalone `.py` scripts (`Name Match Percentage Bulk LLM.py`, `Excel Sheet Cleaner & Repair.py`) along with a generic `requirements.txt` (`pandas`, `customtkinter`, `requests`).
