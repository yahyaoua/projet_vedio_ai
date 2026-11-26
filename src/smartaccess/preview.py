import logging
from dataclasses import dataclass
from threading import Event, Lock, Thread
from time import monotonic

import cv2
from numpy import ndarray

from .config import Settings
from .faces import FaceAssessment, FaceQuality, get_face_extractor
from .media import MediaError, frames, open_capture

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewFrame:
    image: ndarray
    assessment: FaceAssessment

    def annotated(self) -> ndarray:
        image = self.image.copy()
        color = (80, 230, 90) if self.assessment.quality is FaceQuality.USABLE else (0, 185, 255)
        for left, top, right, bottom in self.assessment.boxes:
            cv2.rectangle(image, (left, top), (right - 1, bottom - 1), color, 2)
        return image

    def photo(self) -> bytes:
        try:
            success, encoded = cv2.imencode(".png", self.image)
        except cv2.error as exc:
            raise MediaError("La photo n’a pas pu être encodée.") from exc
        if not success:
            raise MediaError("La photo n’a pas pu être encodée.")
        return encoded.tobytes()


@dataclass(frozen=True)
class PreviewState:
    status: str = "opening"
    frame: PreviewFrame | None = None
    error: str | None = None
    error_source: str | None = None


class FacePreview:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._state = PreviewState()
        self._lock = Lock()
        self._stop = Event()
        self._last_poll = monotonic()
        self._thread = Thread(target=self._run, name="smartaccess-face-preview", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def snapshot(self) -> PreviewState:
        with self._lock:
            return self._state

    def heartbeat(self) -> None:
        with self._lock:
            self._last_poll = monotonic()

    def _stop_requested(self) -> bool:
        with self._lock:
            expired = monotonic() - self._last_poll > 10
        return self.stopping or expired

    def _publish(self, state: PreviewState) -> None:
        with self._lock:
            self._state = state

    def _run(self) -> None:
        terminal = PreviewState("stopped")
        source = "model"
        try:
            extractor = get_face_extractor(self._settings)
            if self._stop_requested():
                return
            source = "camera"
            with open_capture(self._settings.camera_index) as capture:
                next_analysis = 0.0
                for image in frames(capture):
                    if self._stop_requested():
                        break
                    now = monotonic()
                    if now < next_analysis:
                        continue
                    source = "analysis"
                    frame = PreviewFrame(image, extractor.assess(image))
                    self._publish(PreviewState("active", frame))
                    next_analysis = now + 0.15
                    source = "camera"
                if not self._stop_requested():
                    raise MediaError("La caméra ne fournit plus d’image.")
        except Exception as exc:
            LOGGER.exception("Aperçu facial interrompu (%s)", source)
            terminal = PreviewState(
                "unavailable" if source == "camera" else "stopped",
                error=str(exc) or type(exc).__name__, error_source=source,
            )
        finally:
            self._publish(terminal)
