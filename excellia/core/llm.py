"""The only LLM door in core. Everything AI goes through this module.

Talks to a local Ollama over HTTP via stdlib ``urllib`` (core must not
import ``requests`` — enforced by tests/test_imports.py). The LLM only
assists, explains, and proposes; deterministic code decides and counts.

The strict-JSON contract (``json_call``) is the anti-hallucination
workhorse: prompt for JSON only, parse, repair-reprompt once on garbage,
then return a typed failure — callers never see a raw parse exception
and never crash on a rambling local model.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable

DEFAULT_TIMEOUT = 120

# Models we'd pick first when none is pinned — tool/JSON-reliable families.
_PREFERRED = ("qwen2.5", "qwen3", "llama3.1", "llama3.2", "mistral", "gemma")


class LLMError(RuntimeError):
    """The local LLM is unreachable or unusable. Message names the fix."""


def _default_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


class Ollama:
    """Minimal Ollama chat client with an injectable transport.

    ``transport(path, payload)`` posts JSON (or GETs when payload is
    None) and returns the decoded response dict. Tests inject a fake;
    production uses the urllib one built here.
    """

    def __init__(
        self,
        url: str | None = None,
        model: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        transport: Callable[[str, dict | None], dict] | None = None,
    ) -> None:
        self.url = (url or _default_url()).rstrip("/")
        self.timeout = timeout
        self._model = model or os.environ.get("EXCELLIA_MODEL") or None
        self._transport = transport or self._http

    # -- transport ------------------------------------------------------

    def _http(self, path: str, payload: dict | None) -> dict:
        req = urllib.request.Request(
            f"{self.url}{path}",
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError) as e:
            raise LLMError(
                f"Ollama is not reachable at {self.url} ({e}). Start it "
                "(`ollama serve` or the desktop app), or set OLLAMA_URL "
                "if it runs elsewhere. AI features (ask/transform) need it; "
                "profile/validate/anomalies/reconcile work without it."
            ) from e

    # -- model selection ------------------------------------------------

    def available(self) -> bool:
        try:
            self._transport("/api/tags", None)
            return True
        except LLMError:
            return False

    def model(self) -> str:
        """Pinned model (EXCELLIA_MODEL) or the best installed one."""
        if self._model:
            return self._model
        tags = self._transport("/api/tags", None).get("models", [])
        names = [t.get("model") or t.get("name", "") for t in tags]
        names = [n for n in names if n and "embed" not in n]
        if not names:
            raise LLMError(
                "No Ollama models installed. Pull one, e.g. `ollama pull qwen2.5:7b`, "
                "or set EXCELLIA_MODEL to a model you have."
            )
        for family in _PREFERRED:
            for n in names:
                if n.lower().startswith(family):
                    self._model = n
                    return n
        self._model = names[0]
        return self._model

    # -- calls ----------------------------------------------------------

    def chat(self, prompt: str, system: str | None = None,
             force_json: bool = False) -> str:
        """One chat completion, retried once on a transient failure."""
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": self.model(),
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0},
        }
        if force_json:
            payload["format"] = "json"
        last: Exception | None = None
        for _ in range(2):  # retry once — local servers hiccup under load
            try:
                resp = self._transport("/api/chat", payload)
                return resp.get("message", {}).get("content", "") or ""
            except LLMError as e:
                last = e
        raise last  # type: ignore[misc]

    def json_call(self, prompt: str, system: str | None = None) -> dict[str, Any]:
        """The strict-JSON contract. Always returns a dict; on unparseable
        output (after one repair reprompt) returns
        ``{"status": "error", "reason": "parse_failed", "raw": <text>}``."""
        raw = self.chat(prompt, system=system, force_json=True)
        parsed = _extract_json(raw)
        if parsed is not None:
            return parsed
        repair = self.chat(
            "Your previous reply was not valid JSON. Reply again with ONLY the "
            f"JSON object, no prose, no code fences.\n\nPrevious reply:\n{raw[:2000]}",
            system=system,
            force_json=True,
        )
        parsed = _extract_json(repair)
        if parsed is not None:
            return parsed
        return {"status": "error", "reason": "parse_failed", "raw": raw[:500]}


def _extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort: parse a JSON object out of model output (tolerates
    code fences and surrounding prose). None when hopeless."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None
