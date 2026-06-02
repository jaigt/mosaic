"""Tests for backend.api.observability — request-ID middleware + structured logging.

No network / LLM involved. Uses TestClient against a tiny app that only mounts
the middleware, plus direct unit tests of the pure helpers.
"""
import json
import logging
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import observability as obs


def _build_app() -> FastAPI:
    app = FastAPI()
    obs.install_request_id_middleware(app)

    @app.get("/ping")
    def ping():
        return {"request_id": obs.get_request_id()}

    return app


def test_generates_request_id_when_absent():
    client = TestClient(_build_app())
    resp = client.get("/ping")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-ID")
    assert rid
    # Valid UUID
    uuid.UUID(rid)
    # The same id is visible inside the handler via the contextvar.
    assert resp.json()["request_id"] == rid


def test_propagates_incoming_request_id():
    client = TestClient(_build_app())
    incoming = "client-supplied-123"
    resp = client.get("/ping", headers={"X-Request-ID": incoming})
    assert resp.headers.get("X-Request-ID") == incoming
    assert resp.json()["request_id"] == incoming


def test_get_request_id_defaults_outside_request():
    # Outside any request context there is no bound id.
    assert obs.get_request_id() == "-"


def test_structured_log_emits_json(caplog):
    with caplog.at_level(logging.INFO):
        obs.log_event("INFO", "test_event", foo="bar", n=3)
    # Find our record
    recs = [r for r in caplog.records if r.getMessage().strip().startswith("{")]
    assert recs, "expected a JSON-formatted log line"
    payload = json.loads(recs[-1].getMessage())
    assert payload["event"] == "test_event"
    assert payload["foo"] == "bar"
    assert payload["n"] == 3
    assert "request_id" in payload
