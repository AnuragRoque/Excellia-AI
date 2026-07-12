"""Excellia MCP server. Thin adapter: forwards to the core API.

Zero validation logic, zero pandas, zero Ollama. If this file ever
gets fat, the architecture is wrong. Transport is stdio — the host
(Claude Desktop, local_agent) launches this as a subprocess.
"""

import os

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("excellia")
API = os.environ.get("EXCELLIA_API", "http://localhost:8000")


@mcp.tool()
def profile_sheet(file_path: str) -> dict:
    """Get a data profile of a spreadsheet: row/column counts, types, null rates,
    and basic stats. Use this first to understand an unfamiliar file."""
    return requests.post(f"{API}/profile", json={"file": file_path}).json()


@mcp.tool()
def validate(file_path: str, ruleset: str = "default") -> dict:
    """Check a spreadsheet against validation rules (required fields, formats like
    GST/PAN/email, ranges, duplicates). Returns each violation with its row,
    column, and reason."""
    return requests.post(
        f"{API}/validate", json={"file": file_path, "ruleset": ruleset}
    ).json()


@mcp.tool()
def detect_anomalies(file_path: str, sensitivity: float = 0.05) -> dict:
    """Find statistically suspicious rows using Isolation Forest — outliers that
    break no explicit rule but don't fit the data's pattern. Returns flagged rows
    with confidence scores."""
    return requests.post(
        f"{API}/anomalies", json={"file": file_path, "contamination": sensitivity}
    ).json()


@mcp.tool()
def reconcile(file_a: str, file_b: str, key_columns: list[str]) -> dict:
    """Compare two spreadsheets and return matched records, records only in A,
    records only in B, and matched-but-differing records."""
    return requests.post(
        f"{API}/reconcile", json={"a": file_a, "b": file_b, "keys": key_columns}
    ).json()


def main() -> None:
    """Entry point for `excellia-mcp`."""
    mcp.run()


if __name__ == "__main__":
    main()
