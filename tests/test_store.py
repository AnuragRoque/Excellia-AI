"""Workspace store: CRUD, name safety, and the append-only audit trail."""

import os

import pytest

from excellia.core import store


def test_home_creates_layout():
    root = store.home()
    for sub in ("rulesets", "recipes", "profiles", "models", "cache", "jobs"):
        assert (root / sub).is_dir()
    assert str(root).startswith(os.environ["EXCELLIA_HOME"])


def test_save_load_roundtrip():
    spec = {"formats": {"pan": "pan"}, "unique": ["pan"]}
    store.save("rulesets", "my-pack", spec)
    assert store.load("rulesets", "my-pack") == spec
    assert store.list_names("rulesets") == ["my-pack"]


def test_delete():
    store.save("recipes", "tmp", {"steps": []})
    assert store.delete("recipes", "tmp") is True
    assert store.delete("recipes", "tmp") is False
    assert store.list_names("recipes") == []


def test_load_missing_is_instructive():
    store.save("rulesets", "exists", {})
    with pytest.raises(store.StoreError) as e:
        store.load("rulesets", "nope")
    assert "exists" in str(e.value)  # lists what IS available


@pytest.mark.parametrize("bad", ["", "../evil", "a/b", "x" * 65, "-lead", 42])
def test_bad_names_rejected(bad):
    with pytest.raises(store.StoreError):
        store.save("rulesets", bad, {})


def test_bad_kind_rejected():
    with pytest.raises(store.StoreError):
        store.save("wrong", "name", {})


def test_history_append_only_newest_first():
    store.record("profile", summary={"rows": 50})
    store.record("validate", summary={"issues": 3})
    entries = store.history()
    assert [e["op"] for e in entries] == ["validate", "profile"]
    assert all("ts" in e for e in entries)
    # append-only: recording again grows the file, never rewrites
    before = (store.home() / "history.jsonl").read_text(encoding="utf-8")
    store.record("anomalies")
    after = (store.home() / "history.jsonl").read_text(encoding="utf-8")
    assert after.startswith(before)


def test_record_with_file_fingerprint(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    store.record("profile", file=str(f))
    entry = store.history(limit=1)[0]
    assert entry["file"] == "data.csv"
    assert len(entry["file_hash"]) == 16
