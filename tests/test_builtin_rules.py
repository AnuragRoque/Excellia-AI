"""Tests for the built-in format patterns."""

import pytest

from excellia.core.rules.builtin import FORMATS, matches_format

VALID = {
    "gst": ["27AAPFU0939F1ZV", "29AABCU9603R1ZX"],
    "pan": ["AAPFU0939F", "ABCDE1234F"],
    "aadhaar": ["234567890123", "999999999999"],
    "email": ["a@b.co", "first.last+tag@example.org"],
    "phone": ["9876543210", "+91 9876543210", "+91-9876543210"],
    "ifsc": ["HDFC0001234", "SBIN0005943"],
}

INVALID = {
    "gst": ["27AAPFU0939F1AV", "27aapfu0939f1zv", "27AAPFU0939F1Z"],
    "pan": ["AAPFU0939", "12345ABCDE", "aapfu0939f"],
    "aadhaar": ["123456789012", "23456789012", "2345678901234"],
    "email": ["not-an-email", "a@b", "@example.com"],
    "phone": ["1234567890", "98765432", "987654321012"],
    "ifsc": ["HDFC1001234", "HDF00012345", "hdfc0001234"],
}


@pytest.mark.parametrize(
    "fmt,value",
    [(fmt, v) for fmt, values in VALID.items() for v in values],
)
def test_valid_values_match(fmt, value):
    assert matches_format(value, fmt), f"{value!r} should match {fmt}"


@pytest.mark.parametrize(
    "fmt,value",
    [(fmt, v) for fmt, values in INVALID.items() for v in values],
)
def test_invalid_values_rejected(fmt, value):
    assert not matches_format(value, fmt), f"{value!r} should NOT match {fmt}"


def test_whitespace_is_stripped():
    assert matches_format("  ABCDE1234F  ", "pan")


def test_all_formats_present():
    assert set(FORMATS) == {"gst", "pan", "aadhaar", "email", "phone", "ifsc"}
