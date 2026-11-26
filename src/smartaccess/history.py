import csv
from datetime import date
from io import StringIO
from pathlib import Path
from typing import NamedTuple

from .database import connection

EVENT_TYPES = {"verification": "Vérification", "passage": "Passage"}
OUTCOMES = {
    "authorized": "Autorisé", "denied": "Refusé", "invalid_capture": "Capture invalide",
    "entry": "Entrée", "exit": "Sortie",
}
HEADERS = ("Date UTC", "Type", "Résultat", "Compte", "Session", "ID de suivi", "Similarité", "Seuil")


class Event(NamedTuple):
    occurred_at: str
    kind: str
    outcome: str
    user_id: int | None
    session_id: str | None
    track_id: int | None
    similarity: float | None
    threshold: float | None


def sessions(path: Path) -> list[str]:
    with connection(path) as db:
        return [row[0] for row in db.execute("""
            SELECT session_id FROM passage_events
            GROUP BY session_id ORDER BY MAX(occurred_at) DESC, session_id
        """)]


def read_events(
    path: Path, *, kind: str | None = None, outcome: str | None = None,
    session: str | None = None, start: date | None = None, end: date | None = None,
    limit: int = -1,
) -> list[Event]:
    filters = {
        "kind": kind, "outcome": outcome, "session": session,
        "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
        "limit": limit,
    }
    with connection(path, read_only=True) as db:
        rows = db.execute("""
            WITH events AS (
                SELECT id, occurred_at, 'verification' AS kind, outcome, user_id,
                       NULL AS session_id, NULL AS track_id, similarity, threshold
                FROM verification_attempts
                UNION ALL
                SELECT id, occurred_at, 'passage', direction, NULL,
                       session_id, track_id, NULL, NULL
                FROM passage_events
            )
            SELECT occurred_at, kind, outcome, user_id, session_id, track_id, similarity, threshold
            FROM events
            WHERE (:kind IS NULL OR kind = :kind)
              AND (:outcome IS NULL OR outcome = :outcome)
              AND (:session IS NULL OR session_id = :session)
              AND (:start IS NULL OR substr(occurred_at, 1, 10) >= :start)
              AND (:end IS NULL OR substr(occurred_at, 1, 10) <= :end)
            ORDER BY occurred_at DESC, kind, id DESC
            LIMIT :limit
        """, filters)
        return [Event(*row) for row in rows]


def events(
    path: Path, *, kind: str | None = None, outcome: str | None = None,
    session: str | None = None, start: date | None = None, end: date | None = None,
    limit: int = -1,
) -> list[dict]:
    rows = read_events(path, kind=kind, outcome=outcome, session=session, start=start, end=end, limit=limit)
    return [
        dict(zip(HEADERS, (time, EVENT_TYPES[kind], OUTCOMES[result], *details), strict=True))
        for time, kind, result, *details in rows
    ]


def csv_bytes(rows: list[dict]) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")
