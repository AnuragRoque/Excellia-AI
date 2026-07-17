"""Shared fixtures. Every test runs against a throwaway workspace so the
user's real ~/.excellia is never touched."""

import pytest


@pytest.fixture(autouse=True)
def sandbox_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCELLIA_HOME", str(tmp_path / "excellia_home"))
    yield


class FakeOllama:
    """Scripted llm.Ollama transport: pops canned /api/chat replies in order.

    Use: llm.Ollama(model="fake", transport=FakeOllama([reply1, reply2...]))
    Each reply is the assistant content STRING for one chat call."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []  # (path, payload) log for assertions

    def __call__(self, path, payload):
        self.requests.append((path, payload))
        if path == "/api/tags":
            return {"models": [{"model": "fake:latest"}]}
        if not self.replies:
            raise AssertionError("FakeOllama ran out of scripted replies")
        return {"message": {"role": "assistant", "content": self.replies.pop(0)}}
