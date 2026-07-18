"""Pydantic request/response models for the core API.

The `sheet` field tolerates the null-sentinel strings that local LLMs
routinely emit for optional parameters ("null", "none", "", "nan") and
coerces them to a real ``None`` — otherwise a model that passes
``sheet="null"`` would get "Worksheet named 'null' not found".
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_NULL_SENTINELS = {"", "null", "none", "nan", "na"}


def _normalise_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return None if value.strip().lower() in _NULL_SENTINELS else value


class _SheetMixin(BaseModel):
    sheet: str | None = None

    @field_validator("sheet", mode="before")
    @classmethod
    def _clean_sheet(cls, v: object) -> object:
        return _normalise_optional(v) if isinstance(v, str) else v


class ProfileRequest(_SheetMixin):
    file: str


class ValidateRequest(_SheetMixin):
    file: str
    ruleset: str = "default"

    @field_validator("ruleset", mode="before")
    @classmethod
    def _default_ruleset(cls, v: object) -> object:
        # local models pass "null"/"" when they mean "use the default"
        if isinstance(v, str) and v.strip().lower() in _NULL_SENTINELS:
            return "default"
        return v


class AnomaliesRequest(_SheetMixin):
    file: str
    contamination: float = Field(default=0.05, gt=0, lt=0.5)


class ReconcileRequest(BaseModel):
    a: str
    b: str
    keys: list[str]
    tolerance: dict | None = None


class AskRequest(_SheetMixin):
    file: str
    question: str


class CleanRequest(_SheetMixin):
    file: str
    steps: list[dict]
    out_path: str | None = None

    @field_validator("out_path", mode="before")
    @classmethod
    def _clean_out(cls, v: object) -> object:
        return _normalise_optional(v) if isinstance(v, str) else v


class TransformPreviewRequest(_SheetMixin):
    file: str
    instruction: str


class TransformApplyRequest(_SheetMixin):
    file: str
    recipe: dict | None = None
    recipe_name: str | None = None
    instruction: str | None = None
    replace: bool = False
    out_path: str | None = None
    save_as: str | None = None  # also save the recipe under this name

    @field_validator("recipe_name", "instruction", "out_path", "save_as", mode="before")
    @classmethod
    def _clean_optionals(cls, v: object) -> object:
        return _normalise_optional(v) if isinstance(v, str) else v


class ReportRequest(_SheetMixin):
    file: str
    ruleset: str = "default"
    sensitivity: float = Field(default=0.05, gt=0, lt=0.5)
    out_path: str | None = None

    @field_validator("out_path", mode="before")
    @classmethod
    def _clean_out(cls, v: object) -> object:
        return _normalise_optional(v) if isinstance(v, str) else v

    @field_validator("ruleset", mode="before")
    @classmethod
    def _default_ruleset(cls, v: object) -> object:
        if isinstance(v, str) and v.strip().lower() in _NULL_SENTINELS:
            return "default"
        return v


class SpecBody(BaseModel):
    """Body for saving a ruleset or recipe: the JSON spec itself."""

    spec: dict


class JobRequest(BaseModel):
    op: str
    params: dict = Field(default_factory=dict)


class FraudTrainRequest(_SheetMixin):
    file: str
    label_column: str
    model_name: str
    positive_label: str | None = None
    algorithm: str = "gradient_boosting"

    @field_validator("positive_label", mode="before")
    @classmethod
    def _clean_positive(cls, v: object) -> object:
        return _normalise_optional(v) if isinstance(v, str) else v

    @field_validator("algorithm", mode="before")
    @classmethod
    def _default_algorithm(cls, v: object) -> object:
        if isinstance(v, str) and v.strip().lower() in _NULL_SENTINELS:
            return "gradient_boosting"
        return v


class FraudScoreRequest(_SheetMixin):
    file: str
    model_name: str
    threshold: float | None = Field(default=None, gt=0, lt=1)


class FraudEvaluateRequest(_SheetMixin):
    file: str
    label_column: str
    model_name: str


class ReconcileRunRequest(BaseModel):
    a: str
    b: str
    profile_name: str | None = None
    profile: dict | None = None
    report: bool = True
    out_path: str | None = None

    @field_validator("profile_name", "out_path", mode="before")
    @classmethod
    def _clean_optionals(cls, v: object) -> object:
        return _normalise_optional(v) if isinstance(v, str) else v


class KycMatchRequest(_SheetMixin):
    file: str
    col_a: str | None = None
    col_b: str | None = None
    group_by: str | None = None
    llm_verify: bool = False
    seq_threshold: float = Field(default=50.0, ge=0, le=100)

    @field_validator("col_a", "col_b", "group_by", mode="before")
    @classmethod
    def _clean_optionals(cls, v: object) -> object:
        return _normalise_optional(v) if isinstance(v, str) else v


class ValuesValidateRequest(BaseModel):
    values: list
    format: str


class ValuesSimilarityRequest(BaseModel):
    a: list
    b: list


class ValuesMapRequest(BaseModel):
    values: list = Field(max_length=2000)
    instruction: str


class ValuesSplitRequest(BaseModel):
    values: list = Field(max_length=2000)
    parts: list[str]


class ValuesAskRequest(BaseModel):
    columns: list[str]
    rows: list[list]
    question: str


class KycDedupeRequest(_SheetMixin):
    file: str
    columns: list[str]
    threshold: float = Field(default=85.0, ge=0, le=100)
    strategy: str = "most_complete"
    out_path: str | None = None

    @field_validator("out_path", mode="before")
    @classmethod
    def _clean_out(cls, v: object) -> object:
        return _normalise_optional(v) if isinstance(v, str) else v
