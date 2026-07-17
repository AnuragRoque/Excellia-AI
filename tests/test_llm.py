"""llm.py: the strict-JSON contract, model pick, and instructive failures.

Everything runs against a fake transport — zero network, zero Ollama.
"""

import pytest

from excellia.core import llm
from tests.conftest import FakeOllama


def test_model_pick_prefers_known_families():
    fake = FakeOllama([])
    fake_tags = {"models": [{"model": "nomic-embed-text"}, {"model": "weird:1b"},
                            {"model": "qwen2.5:7b"}]}
    client = llm.Ollama(transport=lambda p, b: fake_tags)
    assert client.model() == "qwen2.5:7b"


def test_model_pick_no_models_is_instructive():
    client = llm.Ollama(transport=lambda p, b: {"models": []})
    with pytest.raises(llm.LLMError) as e:
        client.model()
    assert "ollama pull" in str(e.value)


def test_json_call_happy_path():
    client = llm.Ollama(model="fake", transport=FakeOllama(['{"plan": {"limit": 5}}']))
    assert client.json_call("q") == {"plan": {"limit": 5}}


def test_json_call_tolerates_fences_and_prose():
    reply = 'Sure! Here you go:\n```json\n{"value": "42"}\n```'
    client = llm.Ollama(model="fake", transport=FakeOllama([reply]))
    assert client.json_call("q") == {"value": "42"}


def test_json_call_repair_reprompt():
    fake = FakeOllama(["this is not json at all", '{"fixed": true}'])
    client = llm.Ollama(model="fake", transport=fake)
    assert client.json_call("q") == {"fixed": True}
    # the second request must be the repair prompt
    assert "not valid JSON" in fake.requests[-1][1]["messages"][-1]["content"]


def test_json_call_typed_fallback_never_raises():
    fake = FakeOllama(["garbage one", "garbage two"])
    client = llm.Ollama(model="fake", transport=fake)
    out = client.json_call("q")
    assert out["status"] == "error"
    assert out["reason"] == "parse_failed"


def test_unreachable_is_instructive():
    client = llm.Ollama(url="http://127.0.0.1:9", model="fake", timeout=1)
    with pytest.raises(llm.LLMError) as e:
        client.chat("hi")
    msg = str(e.value)
    assert "Ollama is not reachable" in msg and "profile/validate" in msg


def test_available_false_when_down():
    assert llm.Ollama(url="http://127.0.0.1:9", timeout=1).available() is False


def test_extract_json_shapes():
    assert llm._extract_json('{"a": 1}') == {"a": 1}
    assert llm._extract_json('noise {"a": 1} trailing') == {"a": 1}
    assert llm._extract_json("[1, 2]") is None  # arrays are not contract objects
    assert llm._extract_json("") is None
