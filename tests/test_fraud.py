"""fraud.py: honest training on synthetic labelled data.

The synthetic set has a KNOWN signal (high amount + night hours + new
payee -> fraud, with noise), so we can assert a metrics floor. Refusals
and the leakage detector are asserted by message.
"""

import numpy as np
import pandas as pd
import pytest

from excellia.core import fraud, store

RNG = np.random.default_rng(42)


def make_labelled(n=600, flip=0.03) -> pd.DataFrame:
    amount = RNG.gamma(2.0, 2000, n).round(2)
    hour = RNG.integers(0, 24, n)
    payee_age_days = RNG.integers(0, 1000, n)
    channel = RNG.choice(["upi", "neft", "card", "cash"], n)
    # any 2 of 3 risk markers -> fraud (learnable ~10% positive rate), light noise
    risk = ((amount > 5000).astype(int) + ((hour < 6) | (hour > 22)).astype(int)
            + (payee_age_days < 60).astype(int))
    noise = RNG.random(n) < flip
    label = np.where((risk >= 2) ^ noise, "fraud", "ok")
    return pd.DataFrame({
        "txn_id": [f"T{i:05d}" for i in range(n)],
        "amount": amount, "hour": hour, "payee_age_days": payee_age_days,
        "channel": channel, "label": label,
    })


@pytest.fixture(scope="module")
def labelled():
    return make_labelled()


@pytest.fixture()
def trained(labelled):
    return fraud.train(labelled, "label", "test-model")


def test_train_card_metrics_floor(trained):
    card = trained
    assert card["cv_metrics"]["f1"] > 0.6, card["cv_metrics"]
    assert card["cv_metrics"]["roc_auc"] > 0.85
    assert card["positive_label"] == "fraud"
    assert card["rows"] == 600
    assert "txn_id" in card["features_dropped"]  # high-cardinality id excluded
    assert card["top_features"]
    assert "risk" in card["wording"].lower()
    assert "never" in card["wording"].lower()


def test_train_persists_model(trained):
    assert "test-model" in store.list_models()
    cards = fraud.list_models()
    assert any(c["name"] == "test-model" for c in cards)


def test_score_bands_and_factors(trained, labelled):
    fresh = make_labelled(n=50).drop(columns=["label"])
    # plant one screaming row
    fresh.loc[0, ["amount", "hour", "payee_age_days"]] = [50000, 2, 3]
    out = fraud.score(fresh, "test-model")
    assert len(out["scores"]) == 50
    s0 = out["scores"][0]
    assert s0["row"] == 2  # Excel numbering
    assert s0["fraud_probability"] > 0.5
    assert s0["risk_band"] in ("high", "critical")
    assert s0["top_factors"], "planted fraud row must carry factors"
    assert all(f["contribution"] > 0 for f in s0["top_factors"])
    assert out["model_card"]["name"] == "test-model"
    assert "not accusations" in out["summary"]["note"].lower() or "risk" in out["summary"]["note"].lower()


def test_score_schema_drift_refused(trained):
    with pytest.raises(fraud.FraudError) as e:
        fraud.score(pd.DataFrame({"amount": [1.0]}), "test-model")
    msg = str(e.value)
    assert "missing columns" in msg and "hour" in msg


def test_evaluate_holdout(trained):
    holdout = make_labelled(n=300)
    out = fraud.evaluate(holdout, "label", "test-model")
    assert out["holdout_metrics"]["f1"] > 0.5
    assert out["cv_metrics_at_training"] == trained["cv_metrics"]
    assert out["rows_evaluated"] == 300


def test_refuses_missing_label(labelled):
    with pytest.raises(fraud.FraudError, match="not found"):
        fraud.train(labelled, "no_such_col", "m")


def test_refuses_single_class(labelled):
    df = labelled.copy()
    df["label"] = "ok"
    with pytest.raises(fraud.FraudError, match="single class"):
        fraud.train(df, "label", "m")


def test_refuses_too_few_rows():
    with pytest.raises(fraud.FraudError, match="200"):
        fraud.train(make_labelled(n=50), "label", "m")


def test_refuses_numeric_leakage(labelled):
    df = labelled.copy()
    df["is_fraud_flag"] = (df["label"] == "fraud").astype(int)  # the label in disguise
    with pytest.raises(fraud.FraudError, match="leakage"):
        fraud.train(df, "label", "m")


def test_refuses_categorical_leakage(labelled):
    df = labelled.copy()
    df["outcome"] = np.where(df["label"] == "fraud", "bad", "fine")
    with pytest.raises(fraud.FraudError, match="leakage"):
        fraud.train(df, "label", "m")


def test_unknown_model_lists_available(trained):
    with pytest.raises(store.StoreError) as e:
        fraud.score(pd.DataFrame({"a": [1]}), "ghost")
    assert "test-model" in str(e.value)


def test_unknown_algorithm_is_instructive(labelled):
    with pytest.raises(fraud.FraudError, match="gradient_boosting"):
        fraud.train(labelled, "label", "m", algorithm="deep_magic")
