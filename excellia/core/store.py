"""Workspace persistence: saved rulesets/recipes/profiles + audit trail.

Root is ``EXCELLIA_HOME`` (env) or ``~/.excellia``. Everything in here
is data the user accumulated — never code, never their spreadsheets.
The audit trail (``history.jsonl``) is append-only and every layer
writes through the one ``record()`` function.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# JSON-document kinds the store manages. "models" (joblib) arrives in Stage C.
KINDS = ("rulesets", "recipes", "profiles")

_SUBDIRS = KINDS + ("models", "cache", "jobs")

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


class StoreError(ValueError):
    """Raised for bad names/kinds or missing documents. Message is instructive."""


def home() -> Path:
    """Workspace root, created (with subdirs) on first touch."""
    root = Path(os.environ.get("EXCELLIA_HOME", "") or Path.home() / ".excellia")
    for sub in _SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _check_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise StoreError(
            f"Invalid name '{name}'. Use 1-64 letters, digits, '-' or '_', "
            "starting with a letter or digit."
        )
    return name


def _path(kind: str, name: str) -> Path:
    if kind not in KINDS:
        raise StoreError(f"Unknown store kind '{kind}'. Kinds: {', '.join(KINDS)}")
    return home() / kind / f"{_check_name(name)}.json"


def save(kind: str, name: str, spec: dict[str, Any]) -> str:
    """Save a JSON document. Returns the path written."""
    if not isinstance(spec, dict):
        raise StoreError(f"A {kind[:-1]} must be a JSON object, got {type(spec).__name__}")
    path = _path(kind, name)
    path.write_text(json.dumps(spec, indent=2, default=str), encoding="utf-8")
    return str(path)


def load(kind: str, name: str) -> dict[str, Any]:
    path = _path(kind, name)
    if not path.exists():
        available = ", ".join(list_names(kind)) or "none saved yet"
        raise StoreError(
            f"No saved {kind[:-1]} named '{name}'. Available: {available}."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def list_names(kind: str) -> list[str]:
    if kind not in KINDS:
        raise StoreError(f"Unknown store kind '{kind}'. Kinds: {', '.join(KINDS)}")
    return sorted(p.stem for p in (home() / kind).glob("*.json"))


def delete(kind: str, name: str) -> bool:
    """Delete a saved document. Returns False if it didn't exist."""
    path = _path(kind, name)
    if not path.exists():
        return False
    path.unlink()
    return True


def file_fingerprint(file_path: str) -> str | None:
    """Short sha256 of a file's bytes — identifies the data in the audit
    trail without storing any of it. None if the file is unreadable."""
    try:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest()[:16]
    except OSError:
        return None


def record(op: str, params: dict[str, Any] | None = None,
           summary: dict[str, Any] | None = None, file: str | None = None) -> None:
    """Append one line to the audit trail. The ONLY writer of history.jsonl.

    Never raises: an unwritable audit line must not break the operation
    it describes."""
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "op": op,
    }
    if file:
        entry["file"] = os.path.basename(file)
        entry["file_hash"] = file_fingerprint(file)
    if params:
        entry["params"] = params
    if summary:
        entry["summary"] = summary
    try:
        with open(home() / "history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def history(limit: int = 50) -> list[dict[str, Any]]:
    """Most recent audit entries, newest first."""
    path = home() / "history.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines[-limit:] if limit else lines):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def cache_dir() -> Path:
    """Scratch area for pre-images and response caches (safe to wipe)."""
    return home() / "cache"


# --- trained models (fraud etc.): .joblib pipeline + .meta.json card --

def save_model(name: str, pipeline: Any, card: dict[str, Any]) -> str:
    """Persist a fitted sklearn pipeline beside its ModelCard.

    The card holds metrics, features, and a schema fingerprint — never
    the training data itself."""
    import joblib

    _check_name(name)
    base = home() / "models"
    joblib.dump(pipeline, base / f"{name}.joblib")
    (base / f"{name}.meta.json").write_text(
        json.dumps(card, indent=2, default=str), encoding="utf-8"
    )
    return str(base / f"{name}.joblib")


def load_model(name: str) -> tuple[Any, dict[str, Any]]:
    """(pipeline, card) for a saved model; instructive error if missing."""
    import joblib

    _check_name(name)
    base = home() / "models"
    path = base / f"{name}.joblib"
    if not path.exists():
        available = ", ".join(list_models()) or "none trained yet"
        raise StoreError(
            f"No trained model named '{name}'. Available: {available}. "
            "Train one with train_fraud_model / POST /fraud/train."
        )
    card_path = base / f"{name}.meta.json"
    card = json.loads(card_path.read_text(encoding="utf-8")) if card_path.exists() else {}
    return joblib.load(path), card


def list_models() -> list[str]:
    return sorted(p.stem for p in (home() / "models").glob("*.joblib"))


def model_cards() -> list[dict[str, Any]]:
    """All saved ModelCards (metrics and metadata, never data)."""
    cards = []
    for name in list_models():
        path = home() / "models" / f"{name}.meta.json"
        if path.exists():
            cards.append(json.loads(path.read_text(encoding="utf-8")))
    return cards
