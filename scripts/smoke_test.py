import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

BASE = "http://127.0.0.1:8000"


def send(method, path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def main():
    for _ in range(30):
        try:
            if send("GET", "/health")[0] == 200:
                break
        except (OSError, ValueError):
            pass
        time.sleep(1)
    else:
        sys.exit(
            "FAIL: API never became healthy. Run docker compose logs api migrate db"
        )

    event_id = "evt_smoke_" + uuid4().hex
    original = {
        "event_id": event_id,
        "source": "smoke_test",
        "message": "High CPU",
        "timestamp": "2026-11-11T08:00:00Z",
    }
    start = time.monotonic()
    status, first = send("POST", "/webhook", original)
    duration = time.monotonic() - start
    assert status == 201, (status, first)
    assert duration >= 2.7, f"Expected approximately 3 seconds, got {duration:.2f}s"
    status, second = send("POST", "/webhook", original)
    assert status == 200 and first == second, (status, second)
    status, conflict = send("POST", "/webhook", {**original, "message": "Changed"})
    assert status == 409, (status, conflict)
    status, alerts = send("GET", "/alerts")
    assert status == 200 and sum(a["event_id"] == event_id for a in alerts) == 1
    independent = [
        {**original, "event_id": "evt_parallel_" + uuid4().hex} for _ in range(3)
    ]
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(lambda item: send("POST", "/webhook", item), independent)
        )
    parallel_seconds = time.monotonic() - start
    assert all(code == 201 for code, _ in results), results
    assert parallel_seconds < 8.5, f"Requests seem serialized: {parallel_seconds:.2f}s"

    concurrent_event = {**original, "event_id": "evt_race_" + uuid4().hex}
    with ThreadPoolExecutor(max_workers=3) as pool:
        race_results = list(
            pool.map(lambda _: send("POST", "/webhook", concurrent_event), range(3))
        )
    assert sorted(code for code, _ in race_results) == [200, 200, 201], race_results
    status, alerts = send("GET", "/alerts")
    assert status == 200
    assert sum(a["event_id"] == concurrent_event["event_id"] for a in alerts) == 1

    print(
        f"PASS: creation ({duration:.2f}s), duplicate retry, conflict, persistence, "
        f"health, concurrent requests ({parallel_seconds:.2f}s), duplicate race"
    )


if __name__ == "__main__":
    main()
