import asyncio
import base64
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.smartaccess import database

pytest.importorskip("fastapi", reason="Installer requirements-api.txt pour tester l’API")
import httpx
import cv2
import numpy as np

from src.smartaccess.api import app
from src.smartaccess import faces, verification
from src.smartaccess.config import CAPTURES_REQUIRED, SFACE
from src.smartaccess.face_api import MAX_DIMENSION, MAX_PHOTO_BYTES


def send(method, url, **kwargs):
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(request())


def get(url):
    return send("GET", url)


def test_api_reads_existing_data_with_filters(tmp_path, monkeypatch):
    path = tmp_path / "base de test.sqlite3"
    monkeypatch.setenv("SMARTACCESS_DB", str(path))
    database.initialize(path)
    person = database.create_user(path, "Camille")
    database.save_reference(path, person, b"private_embedding", "SFace", "private_method", 3)
    database.record_attempt(path, person, "private_request", database.VerificationAttempt("denied", 0.2, 0.363))
    database.record_passages(path, "session-a", [(7, "entry"), (7, "exit")])
    database.record_passages(path, "session-b", [(9, "entry")])
    with database.connection(path) as db:
        db.execute("UPDATE passage_events SET occurred_at = '2026-01-02 23:59:59' WHERE session_id = 'session-a'")
        db.execute("UPDATE passage_events SET occurred_at = '2026-01-03 00:00:00' WHERE session_id = 'session-b'")

    assert get("/api/health").json() == {"status": "ok", "database": "accessible"}
    assert get("/api/people").json() == [{"id": person, "name": "Camille"}]
    response = get("/api/history?kind=passage&outcome=entry&session=session-a&start=2026-01-02&end=2026-01-02")
    assert response.status_code == 200
    assert response.json() == [{
        "occurred_at": "2026-01-02T23:59:59Z", "kind": "passage", "outcome": "entry",
        "user_id": None, "session_id": "session-a", "track_id": 7, "similarity": None, "threshold": None,
    }]
    denied = get("/api/history?kind=verification&outcome=denied")
    assert denied.json()[0]["similarity"] == 0.2
    assert denied.json()[0]["user_id"] == person
    assert all(value not in denied.text for value in ("embedding", "private_method", "private_request"))
    assert len(get("/api/history?limit=1").json()) == 1
    assert get("/api/history?outcome=authorized").json() == []
    for query in ("kind=other", "outcome=other", "limit=0", "limit=501", "start=bad", "start=2026-02-02&end=2026-02-01"):
        assert get(f"/api/history?{query}").status_code == 422


def test_api_does_not_create_missing_database(tmp_path, monkeypatch):
    path = tmp_path / "missing.sqlite3"
    monkeypatch.setenv("SMARTACCESS_DB", str(path))
    for route in ("health", "people", "history"):
        response = get(f"/api/{route}")
        assert response.status_code == 503
        assert "missing.sqlite3" not in response.text
    assert not path.exists()


def photo(value=0, width=180):
    ok, encoded = cv2.imencode(".png", np.full((130, width, 3), value, dtype=np.uint8))
    assert ok
    return encoded.tobytes()


def post_photo(route, content, key=None):
    headers = {"Content-Type": "image/png"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return send("POST", route, headers=headers, content=content)


@pytest.fixture
def facial_api(tmp_path, monkeypatch):
    path = tmp_path / "facial.sqlite3"
    monkeypatch.setenv("SMARTACCESS_DB", str(path))
    monkeypatch.setenv("SMARTACCESS_VERIFICATION_THRESHOLD", "0.5")
    database.initialize(path)
    user = database.create_user(path, "Compte existant")
    reference = np.eye(1, 128, dtype="<f4")[0]
    database.save_reference(path, user, reference.tobytes(), SFACE, faces.REFERENCE_METHOD, CAPTURES_REQUIRED)
    database.record_passages(path, "session-existante", [(1, "entry")])

    def extract_image(image):
        if image[0, 0, 0] == 0:
            raise faces.FaceError("Aucun visage détecté.")
        return reference if image[0, 0, 0] < 100 else np.roll(reference, 1)

    engine = SimpleNamespace(
        assess=lambda image: faces.FaceAssessment(faces.FaceQuality.USABLE, ((12, 14, 140, 125),)),
        extract_image=extract_image,
    )
    monkeypatch.setattr(faces, "get_face_extractor", lambda settings: engine)
    monkeypatch.setattr(verification, "get_face_extractor", lambda settings: engine)
    return path, user


def test_preview_validates_transport_and_never_writes(facial_api):
    path, _ = facial_api
    route = "/api/faces/analyze"
    result = post_photo(route, photo()).json()
    assert result["boxes"] == [[12, 14, 140, 125]]
    assert (result["width"], result["height"], result["quality"]) == (180, 130, "usable")
    for image, status, code in (
        (b"not a png", 422, "unreadable_image"),
        (b"x" * (MAX_PHOTO_BYTES + 1), 413, "image_too_large"),
        (photo(width=MAX_DIMENSION + 1), 413, "image_dimensions"),
    ):
        response = post_photo(route, image)
        assert response.status_code == status
        assert response.json()["detail"]["code"] == code
    assert get("/api/history?kind=verification").json() == []
    with database.connection(path) as db:
        assert db.execute("SELECT count(*) FROM face_references").fetchone() == (1,)


def test_verification_blocks_missing_people_and_replays_result(facial_api):
    path, user = facial_api
    empty = database.create_user(path, "Sans référence")
    assert post_photo("/api/people/999/verify", photo(1), str(uuid4())).status_code == 404
    assert post_photo(f"/api/people/{empty}/verify", photo(1), str(uuid4())).status_code == 409
    route = f"/api/people/{user}/verify"
    key = str(uuid4())
    authorized = post_photo(route, photo(10), key).json()
    assert authorized == {"outcome": "authorized", "similarity": 1.0, "threshold": 0.5, "capture_error": None}
    assert post_photo(route, photo(110), key).json() == authorized
    assert post_photo(route, photo(110), str(uuid4())).json()["outcome"] == "denied"
    for invalid in (photo(), b"unreadable"):
        result = post_photo(route, invalid, str(uuid4())).json()
        assert result["outcome"] == "invalid_capture"
        assert result["similarity"] is None and result["capture_error"]
    assert len(get("/api/history?kind=verification").json()) == 4
    assert len(get("/api/history?kind=passage").json()) == 1


def test_enrollment_is_atomic_and_replacement_is_explicit(facial_api):
    path, existing = facial_api
    original = database.get_reference(path, existing)
    assert send("POST", "/api/people", json={"name": "  "}).status_code == 422
    created = send("POST", "/api/people", json={"name": "  Camille  "})
    assert created.status_code == 201
    assert created.json()["name"] == "Camille"
    route = f"/api/people/{created.json()['id']}/face"
    assert get(route).json() == {"has_reference": False, "captures_required": CAPTURES_REQUIRED}
    assert get("/api/people/999/face").status_code == 404

    def enroll(target, values):
        payload = {"photos": [base64.b64encode(photo(value)).decode("ascii") for value in values]}
        return send("POST", target, json=payload)

    valid = list(range(110, 110 + CAPTURES_REQUIRED))
    assert enroll(route, valid[:-1]).status_code == 422
    assert enroll(route, [valid[0]] * CAPTURES_REQUIRED).status_code == 422
    assert enroll(route, [0, *valid[1:]]).status_code == 422
    assert get(route).json()["has_reference"] is False
    existing_route = f"/api/people/{existing}/face"
    assert enroll(existing_route, valid).status_code == 409
    assert database.get_reference(path, existing) == original
    assert enroll(route, valid).json()["has_reference"] is True
    assert enroll(existing_route + "?replace=true", valid).status_code == 200
    assert database.get_reference(path, existing) != original
    assert len(get("/api/history").json()) == 1
