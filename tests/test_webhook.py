from datetime import datetime

PAYLOAD = {
    "event_id": "evt_98765",
    "source": "server_1",
    "message": "High CPU",
    "timestamp": "2026-11-11T08:00:00Z",
}


def test_new_alert_is_saved(client):
    response = client.post("/webhook", json=PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["event_id"] == PAYLOAD["event_id"]
    assert body["timestamp"] == "2026-11-11T08:00:00Z"
    assert datetime.fromisoformat(body["processed_at"]).tzinfo is not None
    records = client.get("/alerts").json()
    assert len(records) == 1
    assert records[0]["event_id"] == PAYLOAD["event_id"]


def test_duplicate_is_idempotent(client):
    first = client.post("/webhook", json=PAYLOAD)
    second = client.post("/webhook", json=PAYLOAD)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["processed_at"] == second.json()["processed_at"]
    assert len(client.get("/alerts").json()) == 1


def test_conflicting_event_id_is_rejected(client):
    assert client.post("/webhook", json=PAYLOAD).status_code == 201
    modified = {**PAYLOAD, "message": "Different alert"}
    assert client.post("/webhook", json=modified).status_code == 409
    assert len(client.get("/alerts").json()) == 1


def test_bad_payload_is_rejected(client):
    assert client.post("/webhook", json={"event_id": "evt_1"}).status_code == 422
    assert (
        client.post("/webhook", json={**PAYLOAD, "timestamp": "not a date"}).status_code
        == 422
    )
    assert (
        client.post(
            "/webhook", json={**PAYLOAD, "timestamp": "2026-11-11T08:00:00"}
        ).status_code
        == 422
    )
    assert client.get("/alerts").json() == []


def test_alerts_are_returned_newest_first(client):
    assert client.post("/webhook", json=PAYLOAD).status_code == 201
    second = {**PAYLOAD, "event_id": "evt_98766"}
    assert client.post("/webhook", json=second).status_code == 201
    records = client.get("/alerts").json()
    assert [item["event_id"] for item in records] == ["evt_98766", "evt_98765"]


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_failure_never_returns_success():
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError

    from app.main import create_app

    class BrokenSession:
        async def __aenter__(self):
            raise OperationalError("SELECT 1", {}, RuntimeError("connection down"))

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    with TestClient(
        create_app(session_factory=BrokenSession, processing_delay_seconds=0)
    ) as broken:
        assert broken.post("/webhook", json=PAYLOAD).status_code == 503
        assert broken.get("/alerts").status_code == 503
        assert broken.get("/health").status_code == 503
