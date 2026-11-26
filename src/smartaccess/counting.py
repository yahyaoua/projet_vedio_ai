import logging
from dataclasses import dataclass, replace
from threading import Event, Lock, Thread
from time import perf_counter
from uuid import uuid4

import cv2
from numpy import ndarray

from . import database
from .config import YOLO11N, Settings
from .crossing import CountingLine, CrossingCounter
from .media import MediaError, frames, open_capture

LOGGER = logging.getLogger(__name__)
TRACKER_LOCK = Lock()


def load_yolo(settings: Settings):
    weights = settings.model_path(YOLO11N)
    if not weights.is_file():
        raise ValueError(f"Modèle YOLO11n absent : {weights}. Consulte le README.")
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ValueError("Ultralytics est indisponible. Vérifie l’installation des dépendances.") from exc
    model = YOLO(str(weights), task="detect")
    if model.names.get(0) != "person":
        raise ValueError("Le modèle attendu est YOLO11n entraîné sur COCO.")
    return model


@dataclass(frozen=True)
class Progress:
    frames: int = 0
    entries: int = 0
    exits: int = 0
    fps: float = 0.0
    image: ndarray | None = None
    status: str = "running"
    error: str | None = None
    error_source: str | None = None


def annotate(frame: ndarray, boxes, line: CountingLine) -> dict[int, float]:
    height, width = frame.shape[:2]
    bottom = max(1, height - 1)
    positions = {}
    if boxes is not None:
        coordinates = boxes.xyxy.cpu().tolist()
        ids = boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(coordinates)
        for track_id, (x1, y1, x2, y2) in zip(ids, coordinates, strict=True):
            cv2.rectangle(frame, (round(x1), round(y1)), (round(x2), round(y2)), (80, 230, 90), 2)
            if track_id is None:
                continue
            x = round((x1 + x2) / 2)
            y = min(bottom, max(0, y2))
            positions[track_id] = y / bottom
            cv2.circle(frame, (x, round(y)), 4, (80, 230, 90), -1)
            cv2.putText(frame, f"ID {track_id}", (round(x1), max(15, round(y1) - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 230, 90), 2)

    for fraction, color, thickness in (
        (line.y - line.tolerance, (0, 180, 255), 1),
        (line.y + line.tolerance, (0, 180, 255), 1),
        (line.y, (0, 255, 255), 2),
    ):
        y = round(fraction * bottom)
        cv2.line(frame, (0, y), (width - 1, y), color, thickness)
    draw_directions(frame, line)
    return positions


def draw_directions(frame: ndarray, line: CountingLine) -> None:
    height, width = frame.shape[:2]
    center = round(line.y * (height - 1))
    span = max(1, round(height * max(0.06, line.tolerance + 0.02)))
    top, bottom = max(0, center - span), min(height - 1, center + span)
    scale = min(0.8, width / 650)
    for label, x, down in (
        ("ENTREE", round(width * 0.04), line.entry_down),
        ("SORTIE", round(width * 0.23), not line.entry_down),
    ):
        start, end = (top, bottom) if down else (bottom, top)
        origin = (x + 6, min(height - 2, max(12, center - 5)))
        for color, thickness in (((0, 0, 0), 5), ((255, 255, 255), 2)):
            cv2.arrowedLine(frame, (x, start), (x, end), color, thickness, cv2.LINE_AA, tipLength=0.25)
            cv2.putText(frame, label, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


class CountingRun:
    def __init__(self, settings: Settings, line: CountingLine, *, webcam: bool = False):
        self.session_id = uuid4().hex
        self.webcam = webcam
        self._settings = settings
        self.line = line
        self._stop = Event()
        self._lock = Lock()
        self._progress = Progress()
        self._last_poll = perf_counter()
        self._thread = Thread(target=self._run, name="smartaccess-counting", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def heartbeat(self) -> None:
        with self._lock:
            self._last_poll = perf_counter()

    def _stop_requested(self) -> bool:
        with self._lock:
            expired = self.webcam and perf_counter() - self._last_poll > 30
        return self.stopping or expired

    def snapshot(self) -> Progress:
        with self._lock:
            return self._progress

    def _publish(self, progress: Progress) -> None:
        with self._lock:
            self._progress = progress

    def _run(self) -> None:
        if not TRACKER_LOCK.acquire(blocking=False):
            self._publish(Progress(status="error", error="Un comptage est déjà en cours. Attends sa fin."))
            return
        try:
            final = self._process_video()
        except MediaError as exc:
            LOGGER.exception("Source illisible pour le comptage %s", self.session_id)
            final = replace(self.snapshot(), status="error", error=str(exc), error_source="media")
        except Exception as exc:
            LOGGER.exception("Échec du comptage %s", self.session_id)
            final = replace(self.snapshot(), status="error", error=str(exc) or type(exc).__name__)
        finally:
            TRACKER_LOCK.release()
        self._publish(final)

    def _process_video(self) -> Progress:
        try:
            model = load_yolo(self._settings)
        except Exception as exc:
            LOGGER.exception("Chargement du modèle pour le comptage %s", self.session_id)
            return Progress(status="error", error=str(exc) or type(exc).__name__, error_source="model")

        counter = CrossingCounter(self.line)
        progress = self.snapshot()
        source = self._settings.camera_index if self.webcam else str(self._settings.test_video)
        if self._stop_requested():
            return replace(progress, status="stopped")
        with open_capture(source) as capture:
            started = perf_counter()
            for number, frame in enumerate(frames(capture), start=1):
                if self._stop_requested():
                    break
                result = model.track(
                    frame, persist=True, tracker="bytetrack.yaml", classes=[0],
                    device="cpu", verbose=False,
                )[0]
                passages = counter.observe(number, annotate(frame, result.boxes, self.line))
                if passages:
                    database.record_passages(self._settings.database, self.session_id, passages)
                entries = sum(direction == "entry" for _, direction in passages)
                progress = Progress(
                    frames=number, entries=progress.entries + entries,
                    exits=progress.exits + len(passages) - entries,
                    fps=number / (perf_counter() - started), image=frame,
                )
                self._publish(progress)

        if self._stop_requested():
            return replace(progress, status="stopped")
        if self.webcam:
            raise MediaError("La webcam ne transmet plus d’image. Vérifie sa connexion et réessaie.")
        if not progress.frames:
            raise MediaError("Aucune image n’a pu être décodée depuis la vidéo.")
        return replace(progress, status="done")
