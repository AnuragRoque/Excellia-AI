"""Shared result types returned by the core engine.

Every finding carries a human-readable reason. No black boxes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Issue:
    """A deterministic rule violation found by ``validate``."""

    row: int
    column: str
    rule_name: str
    severity: str  # "error" | "warning" | "info"
    reason: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Flag:
    """A statistical anomaly found by ``detect_anomalies``.

    Unlike an Issue, a Flag breaks no explicit rule — it just doesn't
    fit the data's pattern. ``confidence`` is 0..1 and ``reason``
    explains why the row was flagged.
    """

    row: int
    kind: str  # "multivariate_outlier" | "column_outlier" | "rare_category" | "near_duplicate" | "pattern_break"
    confidence: float
    reason: str
    columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ColumnProfile:
    """Per-column statistics inside a Profile."""

    name: str
    inferred_type: str  # "number" | "date" | "currency" | "categorical" | "id" | "text"
    null_rate: float
    cardinality: int
    min: Any = None
    max: Any = None
    mean: float | None = None
    top_values: list[Any] = field(default_factory=list)
    detected_format: str | None = None  # e.g. "GST", "PAN", "email"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Profile:
    """Output of ``profile``: the shape and character of a spreadsheet."""

    file: str
    sheet: str | None
    row_count: int
    column_count: int
    columns: list[ColumnProfile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReconcileResult:
    """Output of ``reconcile``: records bucketed by match outcome.

    ``discrepancies`` holds records that matched on the key columns
    but differ in at least one other field.
    """

    matched: list[dict[str, Any]] = field(default_factory=list)
    only_in_a: list[dict[str, Any]] = field(default_factory=list)
    only_in_b: list[dict[str, Any]] = field(default_factory=list)
    discrepancies: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            "matched": len(self.matched),
            "only_in_a": len(self.only_in_a),
            "only_in_b": len(self.only_in_b),
            "discrepancies": len(self.discrepancies),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "matched": self.matched,
            "only_in_a": self.only_in_a,
            "only_in_b": self.only_in_b,
            "discrepancies": self.discrepancies,
        }
