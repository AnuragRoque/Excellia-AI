"""Pydantic request/response models for the core API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileRequest(BaseModel):
    file: str
    sheet: str | None = None


class ValidateRequest(BaseModel):
    file: str
    ruleset: str = "default"
    sheet: str | None = None


class AnomaliesRequest(BaseModel):
    file: str
    contamination: float = Field(default=0.05, gt=0, lt=0.5)
    sheet: str | None = None


class ReconcileRequest(BaseModel):
    a: str
    b: str
    keys: list[str]
    tolerance: dict | None = None
