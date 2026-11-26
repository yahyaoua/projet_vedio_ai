import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import database, history
from .config import Settings
from .face_api import router as face_router

LOGGER = logging.getLogger(__name__)
EventKind = Literal["verification", "passage"]
EventOutcome = Literal["authorized", "denied", "invalid_capture", "entry", "exit"]

app = FastAPI(title="SmartAccess", version="0.1.0")
app.include_router(face_router)


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["accessible"] = "accessible"


class Person(BaseModel):
    id: int
    name: str


class HistoryEvent(BaseModel):
    occurred_at: datetime
    kind: EventKind
    outcome: EventOutcome
    user_id: int | None
    session_id: str | None
    track_id: int | None
    similarity: float | None
    threshold: float | None


def configured_database() -> Path:
    try:
        return Settings().database
    except ValueError as exc:
        LOGGER.exception("Configuration de SmartAccess invalide")
        raise HTTPException(503, "Configuration de SmartAccess invalide.") from exc


DatabasePath = Annotated[Path, Depends(configured_database)]


@app.exception_handler(sqlite3.Error)
async def database_error(_request: Request, exc: sqlite3.Error) -> JSONResponse:
    LOGGER.error("Opération SQLite impossible", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Base SmartAccess inaccessible ou non initialisée."})


@app.get("/api/health")
def health(path: DatabasePath) -> Health:
    with database.connection(path, read_only=True) as db:
        db.execute("SELECT id, name FROM users LIMIT 1").fetchone()
    history.read_events(path, limit=0)
    return Health()


@app.get("/api/people")
def people(path: DatabasePath) -> list[Person]:
    return [Person(id=user_id, name=name) for user_id, name in database.list_users(path).items()]


@app.get("/api/history")
def event_history(
    path: DatabasePath,
    kind: EventKind | None = None,
    outcome: EventOutcome | None = None,
    session: Annotated[str | None, Query(min_length=1)] = None,
    start: date | None = None,
    end: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[HistoryEvent]:
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "La date de début doit précéder la date de fin ou lui être égale.")
    rows = history.read_events(path, kind=kind, outcome=outcome, session=session, start=start, end=end, limit=limit)
    result = []
    for row in rows:
        occurred_at = datetime.fromisoformat(row.occurred_at)
        occurred_at = occurred_at.replace(tzinfo=timezone.utc) if occurred_at.tzinfo is None else occurred_at
        result.append(HistoryEvent(
            occurred_at=occurred_at.astimezone(timezone.utc),
            kind=row.kind,
            outcome=row.outcome,
            user_id=row.user_id,
            session_id=row.session_id,
            track_id=row.track_id,
            similarity=row.similarity,
            threshold=row.threshold,
        ))
    return result
