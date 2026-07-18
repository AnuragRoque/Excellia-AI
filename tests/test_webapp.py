"""Stage D web layer: static app served by the API + the upload door.

The web app owns zero logic, so there is nothing to unit-test in it
beyond delivery; behaviour lives in the API contract tests.
"""

import io
import os

import pandas as pd
from fastapi.testclient import TestClient

from excellia.api.main import app
from excellia.core import store

client = TestClient(app)


def test_root_redirects_to_app():
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/app/"


def test_app_serves_index_and_assets():
    r = client.get("/app/")
    assert r.status_code == 200
    assert "Excellia" in r.text
    assert client.get("/app/app.js").status_code == 200
    assert client.get("/app/styles.css").status_code == 200


def test_webapp_owns_zero_logic():
    """The web layer must be a pure client: no pandas, no compute."""
    import pathlib

    import excellia

    webapp = pathlib.Path(excellia.__file__).parent / "webapp"
    js = (webapp / "app.js").read_text(encoding="utf-8")
    assert "fetch(" in js  # it talks HTTP...
    for html_file in webapp.glob("*.html"):
        assert "pandas" not in html_file.read_text(encoding="utf-8")


def test_upload_roundtrip(tmp_path):
    df = pd.DataFrame({"vendor": ["Acme", "Zen"], "amount": [10, 20]})
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    r = client.post("/upload", files={"file": ("my data (1).csv", buf.getvalue(), "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert os.path.exists(body["path"])
    assert str(store.home() / "uploads") in body["path"]

    # the uploaded path immediately works with every other endpoint
    prof = client.post("/profile", json={"file": body["path"]}).json()
    assert prof["row_count"] == 2


def test_upload_rejects_unsupported_type():
    r = client.post("/upload", files={"file": ("evil.exe", b"MZ", "application/x-msdownload")})
    assert r.status_code == 400
    assert ".xlsx" in r.json()["detail"]
