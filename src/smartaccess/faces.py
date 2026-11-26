from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from hashlib import file_digest
from pathlib import Path
from threading import Lock

import cv2
import numpy as np

from .config import CAPTURES_REQUIRED, FACE_MODEL_HASHES, SFACE, YUNET, Settings

REFERENCE_METHOD = "mean_l2_normalized_float32_le_v1"
EMBEDDING_DIMENSION = 128


class FaceError(ValueError):
    pass


class FaceQuality(Enum):
    NO_FACE = "Aucun visage détecté. Place-toi face à la caméra."
    MULTIPLE = "Plusieurs visages détectés. Une seule personne doit être dans le cadre."
    TOO_SMALL = "Le visage visible est trop petit. Approche-toi de la caméra."
    BLURRY = "Le visage paraît flou. Reste immobile et améliore l’éclairage."
    USABLE = ""


@dataclass(frozen=True)
class FaceAssessment:
    quality: FaceQuality
    boxes: tuple[tuple[int, int, int, int], ...]
    face: np.ndarray | None = None


def verified_face_model(path: Path) -> str:
    try:
        with path.open("rb") as model:
            digest = file_digest(model, "sha256").hexdigest()
    except OSError as exc:
        raise FaceError(f"Modèle introuvable ou illisible : {path}. Consulte docs/enregistrement.md.") from exc
    if digest != FACE_MODEL_HASHES[path.name]:
        raise FaceError(f"Modèle incorrect ou incomplet : {path.name}. Récupère le fichier ONNX officiel.")
    return str(path)


def normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(vector)
    if vector.size != EMBEDDING_DIMENSION or not np.isfinite(norm) or norm <= 0:
        raise FaceError("Le vecteur facial est invalide. Reprends la capture.")
    return vector / norm


def build_reference(samples: list[np.ndarray]) -> bytes:
    if len(samples) < CAPTURES_REQUIRED:
        raise FaceError(f"Il faut au moins {CAPTURES_REQUIRED} captures valides.")
    mean = np.mean([normalize(sample) for sample in samples], axis=0)
    return normalize(mean).astype("<f4").tobytes()


class FaceExtractor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = Lock()
        yunet = verified_face_model(settings.model_path(YUNET))
        sface = verified_face_model(settings.model_path(SFACE))
        try:
            self.detector = cv2.FaceDetectorYN.create(yunet, "", (320, 320))
            self.recognizer = cv2.FaceRecognizerSF.create(sface, "")
        except cv2.error as exc:
            raise FaceError("OpenCV ne peut pas charger YuNet ou SFace. Vérifie l’installation.") from exc

    def assess(self, image: np.ndarray) -> FaceAssessment:
        height, width = image.shape[:2]
        with self._lock:
            self.detector.setInputSize((width, height))
            _, faces = self.detector.detect(image)
        if faces is None or len(faces) == 0:
            return FaceAssessment(FaceQuality.NO_FACE, ())

        boxes = []
        for face in faces:
            x, y, face_width, face_height = map(float, face[:4])
            boxes.append((max(0, int(x)), max(0, int(y)),
                          min(width, int(x + face_width)), min(height, int(y + face_height))))
        bounds = tuple(boxes)
        if len(bounds) > 1:
            return FaceAssessment(FaceQuality.MULTIPLE, bounds)
        left, top, right, bottom = bounds[0]
        if min(right - left, bottom - top) < self.settings.min_face_pixels:
            return FaceAssessment(FaceQuality.TOO_SMALL, bounds)
        gray = cv2.cvtColor(image[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
        if cv2.Laplacian(gray, cv2.CV_64F).var() < self.settings.min_sharpness:
            return FaceAssessment(FaceQuality.BLURRY, bounds)
        return FaceAssessment(FaceQuality.USABLE, bounds, faces[0])

    def extract(self, photo: bytes) -> np.ndarray:
        if not photo:
            raise FaceError("La capture est vide. Reprends une photo.")
        try:
            image = cv2.imdecode(np.frombuffer(photo, dtype=np.uint8), cv2.IMREAD_COLOR)
        except cv2.error as exc:
            raise FaceError("OpenCV n’a pas pu traiter la capture. Reprends une photo.") from exc
        if image is None:
            raise FaceError("La capture est illisible. Reprends une photo.")
        return self.extract_image(image)

    def extract_image(self, image: np.ndarray) -> np.ndarray:
        try:
            assessment = self.assess(image)
            if assessment.face is None:
                raise FaceError(assessment.quality.value)
            with self._lock:
                aligned = self.recognizer.alignCrop(image, assessment.face)
                return normalize(self.recognizer.feature(aligned))
        except cv2.error as exc:
            raise FaceError("OpenCV n’a pas pu traiter la capture. Reprends une photo.") from exc


@lru_cache(maxsize=2)
def _load_extractor(settings: Settings, model_versions: tuple[int, ...]) -> FaceExtractor:
    return FaceExtractor(settings)


_load_lock = Lock()


def get_face_extractor(settings: Settings) -> FaceExtractor:
    try:
        stats = [settings.model_path(name).stat() for name in (YUNET, SFACE)]
    except OSError as exc:
        raise FaceError(f"Modèle facial absent ou illisible dans {settings.models}. Consulte docs/enregistrement.md.") from exc
    versions = tuple(value for stat in stats for value in (stat.st_size, stat.st_mtime_ns))
    with _load_lock:
        return _load_extractor(settings, versions)
