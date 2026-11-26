import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple


class VerificationAttempt(NamedTuple):
    outcome: str
    similarity: float | None
    threshold: float | None


@contextmanager
def connection(path: Path, *, read_only: bool = False):
    db = sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True) if read_only else sqlite3.connect(path)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        with db:
            yield db
    finally:
        db.close()


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as db:
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS face_references (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                embedding BLOB NOT NULL,
                model TEXT NOT NULL,
                method TEXT NOT NULL,
                capture_count INTEGER NOT NULL CHECK (capture_count >= 3),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS verification_attempts (
                id INTEGER PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                outcome TEXT NOT NULL CHECK (outcome IN ('authorized', 'denied', 'invalid_capture'))
            );
            CREATE TABLE IF NOT EXISTS passage_events (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                direction TEXT NOT NULL CHECK (direction IN ('entry', 'exit')),
                track_id INTEGER NOT NULL
            );
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(verification_attempts)")}
        if "request_id" not in columns:
            db.execute("ALTER TABLE verification_attempts ADD COLUMN request_id TEXT")
        if "similarity" not in columns:
            db.execute("ALTER TABLE verification_attempts ADD COLUMN similarity REAL")
        if "threshold" not in columns:
            db.execute("ALTER TABLE verification_attempts ADD COLUMN threshold REAL")
        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS verification_request_id
            ON verification_attempts (request_id)
        """)


def create_user(path: Path, name: str) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Saisis le nom ou le pseudonyme du volontaire.")
    with connection(path) as db:
        cursor = db.execute("INSERT INTO users (name) VALUES (?)", (name,))
        return cursor.lastrowid


def list_users(path: Path) -> dict[int, str]:
    with connection(path, read_only=True) as db:
        return dict(db.execute("SELECT id, name FROM users ORDER BY name, id"))


def delete_user(path: Path, user_id: int) -> bool:
    with connection(path) as db:
        return db.execute("DELETE FROM users WHERE id = ?", (user_id,)).rowcount == 1


def reference_count(path: Path, user_id: int) -> int | None:
    with connection(path) as db:
        row = db.execute(
            "SELECT capture_count FROM face_references WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row[0] if row else None


def person_face_status(path: Path, user_id: int) -> tuple[int | None] | None:
    with connection(path, read_only=True) as db:
        return db.execute("""
            SELECT face_references.capture_count
            FROM users LEFT JOIN face_references ON face_references.user_id = users.id
            WHERE users.id = ?
        """, (user_id,)).fetchone()


def save_reference(
    path: Path, user_id: int, embedding: bytes, model: str, method: str, capture_count: int,
    *, replace: bool = True,
) -> bool:
    with connection(path) as db:
        cursor = db.execute("""
            INSERT INTO face_references (user_id, embedding, model, method, capture_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                embedding = excluded.embedding, model = excluded.model,
                method = excluded.method, capture_count = excluded.capture_count,
                updated_at = CURRENT_TIMESTAMP
            WHERE ?
        """, (user_id, embedding, model, method, capture_count, replace))
        return cursor.rowcount == 1


def get_reference(path: Path, user_id: int) -> tuple[bytes, str, str] | None:
    with connection(path) as db:
        return db.execute(
            "SELECT embedding, model, method FROM face_references WHERE user_id = ?", (user_id,)
        ).fetchone()


def get_attempt(path: Path, user_id: int, request_id: str) -> VerificationAttempt | None:
    with connection(path) as db:
        return _get_attempt(db, user_id, request_id)


def _get_attempt(db, user_id: int, request_id: str) -> VerificationAttempt | None:
    row = db.execute("""
        SELECT user_id, outcome, similarity, threshold
        FROM verification_attempts WHERE request_id = ?
    """, (request_id,)).fetchone()
    if row is None:
        return None
    if row[0] != user_id:
        raise ValueError("Cette demande de vérification appartient à un autre compte ou a été supprimée.")
    return VerificationAttempt(*row[1:])


def record_attempt(
    path: Path, user_id: int, request_id: str, attempt: VerificationAttempt
) -> VerificationAttempt:
    with connection(path) as db:
        db.execute("""
            INSERT INTO verification_attempts (user_id, request_id, outcome, similarity, threshold)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO NOTHING
        """, (user_id, request_id, *attempt))
        saved = _get_attempt(db, user_id, request_id)
        if saved is None:
            raise sqlite3.DatabaseError("La tentative n’a pas été enregistrée.")
        return saved


def record_passages(path: Path, session_id: str, passages: list[tuple[int, str]]) -> None:
    with connection(path) as db:
        db.executemany("""
            INSERT INTO passage_events (session_id, track_id, direction)
            VALUES (?, ?, ?)
        """, ((session_id, track_id, direction) for track_id, direction in passages))
