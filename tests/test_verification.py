from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import numpy as np
import pytest

from src.smartaccess import database, verification
from src.smartaccess.config import SFACE, Settings
from src.smartaccess.faces import REFERENCE_METHOD, FaceError


@pytest.mark.parametrize(("similarity", "expected"), [
    (0.3629, "denied"),
    (0.363, "authorized"),
    (0.3631, "authorized"),
])
def test_decision_at_threshold(similarity, expected):
    assert verification.decide(similarity, 0.363) == expected


@pytest.fixture
def enrolled(tmp_path):
    settings = Settings(database=tmp_path / "test.sqlite3", verification_threshold=0.5)
    database.initialize(settings.database)
    database.create_user(settings.database, "Volontaire")
    user_id = next(iter(database.list_users(settings.database)))
    reference = np.zeros(128, dtype="<f4")
    reference[0] = 1
    database.save_reference(settings.database, user_id, reference.tobytes(), SFACE, REFERENCE_METHOD, 3)
    return settings, user_id, reference


def test_replaying_request_uses_first_result(enrolled, monkeypatch):
    settings, user_id, reference = enrolled
    photos = []

    def extract(photo):
        photos.append(photo)
        return reference

    monkeypatch.setattr(verification, "get_face_extractor", lambda settings: SimpleNamespace(extract=extract))
    first = verification.verify(settings, user_id, "same-request", b"photo")
    replay = verification.verify(settings, user_id, "same-request", b"photo")
    saved = database.record_attempt(
        settings.database, user_id, "same-request", database.VerificationAttempt("denied", 0.0, 0.5)
    )
    assert first.attempt == replay.attempt == saved == ("authorized", 1.0, 0.5)
    assert photos == [b"photo"]
    with database.connection(settings.database) as db:
        assert db.execute("SELECT count(*) FROM verification_attempts").fetchone() == (1,)


def test_invalid_capture_has_no_similarity(enrolled, monkeypatch):
    settings, user_id, reference = enrolled
    processed = []

    def extract(photo):
        processed.append(photo)
        if photo == b"invalid":
            raise FaceError("Aucun visage")
        return reference

    monkeypatch.setattr(verification, "get_face_extractor", lambda settings: SimpleNamespace(extract=extract))
    result = verification.verify(settings, user_id, "invalid-request", b"invalid")
    assert result.capture_error == "Aucun visage"
    assert result.attempt == ("invalid_capture", None, 0.5)
    assert database.get_attempt(settings.database, user_id, "invalid-request") == result.attempt
    replay = verification.verify(settings, user_id, "invalid-request", b"invalid")
    retry = verification.verify(settings, user_id, "fresh-request", b"valid")
    assert replay.attempt == result.attempt
    assert retry.attempt == ("authorized", 1.0, 0.5)
    assert processed == [b"invalid", b"valid"]
    with database.connection(settings.database) as db:
        assert db.execute("SELECT count(*) FROM verification_attempts").fetchone() == (2,)


def test_concurrent_writes_keep_one_result_per_request(enrolled):
    settings, user_id, _ = enrolled
    ready = Barrier(2)
    candidates = [
        database.VerificationAttempt("authorized", 0.9, 0.5),
        database.VerificationAttempt("denied", 0.1, 0.5),
    ]

    def submit(candidate):
        ready.wait(timeout=5)
        return database.record_attempt(settings.database, user_id, "same-request", candidate)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(submit, candidates)
    assert first == second
    assert first in candidates
    with database.connection(settings.database) as db:
        assert db.execute("SELECT count(*) FROM verification_attempts").fetchone() == (1,)


def test_missing_reference_blocks_capture(enrolled, monkeypatch):
    settings, enrolled_id, _ = enrolled
    database.create_user(settings.database, "Autre compte")
    user_id = next(key for key in database.list_users(settings.database) if key != enrolled_id)
    monkeypatch.setattr(verification, "get_face_extractor", lambda settings: pytest.fail("Extraction inattendue"))
    with pytest.raises(ValueError, match="référence faciale"):
        verification.verify(settings, user_id, "no-reference", b"photo")
    assert database.get_attempt(settings.database, user_id, "no-reference") is None


def test_migration_preserves_existing_attempt(tmp_path):
    path = tmp_path / "old.sqlite3"
    with database.connection(path) as db:
        db.execute("""
            CREATE TABLE verification_attempts (
                id INTEGER PRIMARY KEY, user_id INTEGER, occurred_at TEXT, outcome TEXT
            )
        """)
        db.execute("INSERT INTO verification_attempts VALUES (9, 1, '2026-01-01', 'denied')")

    database.initialize(path)
    database.initialize(path)
    with database.connection(path) as db:
        assert db.execute("SELECT * FROM verification_attempts").fetchone() == (
            9, 1, "2026-01-01", "denied", None, None, None
        )
