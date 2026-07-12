"""Built-in format patterns for rule-based validation.

Each entry is a compiled regex that must match the ENTIRE cell value
(after stripping whitespace). These are also used by profiling to
auto-detect a column's format.
"""

from __future__ import annotations

import re

FORMATS: dict[str, re.Pattern[str]] = {
    # 2-digit state code + PAN + entity number + 'Z' + checksum
    "gst": re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"),
    "pan": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
    # 12 digits, cannot start with 0 or 1
    "aadhaar": re.compile(r"^[2-9][0-9]{11}$"),
    "email": re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"),
    # Indian mobile, optional +91 prefix
    "phone": re.compile(r"^(?:\+91[\s-]?)?[6-9][0-9]{9}$"),
    "ifsc": re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
}


def matches_format(value: str, format_name: str) -> bool:
    """True if ``value`` (stripped) matches the named built-in format."""
    pattern = FORMATS[format_name]
    return bool(pattern.fullmatch(str(value).strip()))
