import csv
from datetime import date
from io import StringIO

from src.smartaccess import database, history


def test_history_and_csv_use_the_same_filtered_metadata(tmp_path):
    path = tmp_path / "test.sqlite3"
    database.initialize(path)
    database.create_user(path, "Volontaire")
    user_id = next(iter(database.list_users(path)))
    database.save_reference(path, user_id, b"private_embedding", "SFace", "test", 3)
    database.record_attempt(path, user_id, "request", database.VerificationAttempt("denied", 0.2, 0.363))
    database.record_passages(path, "session-a", [(1, "entry"), (1, "exit")])
    database.record_passages(path, "session-b", [(2, "entry")])
    with database.connection(path) as db:
        db.execute("UPDATE passage_events SET occurred_at = '2026-01-02 23:59:59' WHERE session_id = 'session-a'")

    filters = dict(kind="passage", outcome="entry", session="session-a", start=date(2026, 1, 2), end=date(2026, 1, 2))
    assert history.read_events(path, **filters) == [
        history.Event("2026-01-02 23:59:59", "passage", "entry", None, "session-a", 1, None, None),
    ]
    rows = history.events(path, **filters)
    assert len(rows) == 1
    assert rows[0]["Résultat"] == "Entrée"
    data = history.csv_bytes(rows).decode("utf-8-sig")
    assert "private_embedding" not in data
    assert list(csv.DictReader(StringIO(data))) == [{
        key: "" if value is None else str(value) for key, value in rows[0].items()
    }]
    assert history.events(path, kind="verification", outcome="denied")[0]["Compte"] == user_id
    assert set(history.sessions(path)) == {"session-a", "session-b"}
