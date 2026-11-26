from dataclasses import dataclass

import numpy as np

from . import database
from .config import SFACE, Settings
from .faces import REFERENCE_METHOD, FaceError, get_face_extractor, normalize


@dataclass(frozen=True)
class VerificationResult:
    attempt: database.VerificationAttempt
    capture_error: str | None = None


def decide(similarity: float, threshold: float) -> str:
    return "authorized" if similarity >= threshold else "denied"


def verify(
    settings: Settings, user_id: int, request_id: str, photo: bytes | np.ndarray, *, capture_error: str | None = None,
) -> VerificationResult:
    reference = database.get_reference(settings.database, user_id)
    if reference is None:
        raise ValueError("Ce compte doit avoir une référence faciale avant la vérification.")

    previous = database.get_attempt(settings.database, user_id, request_id)
    if previous is not None:
        return VerificationResult(previous)

    raw_embedding, model, method = reference
    if model != SFACE or method != REFERENCE_METHOD:
        raise ValueError("Référence faciale incompatible. Renouvelle l’enregistrement du volontaire.")
    try:
        reference_vector = normalize(np.frombuffer(raw_embedding, dtype="<f4"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Référence faciale illisible. Renouvelle l’enregistrement du volontaire.") from exc

    threshold = settings.verification_threshold
    if capture_error is not None:
        attempt = database.VerificationAttempt("invalid_capture", None, threshold)
    else:
        extractor = get_face_extractor(settings)
        try:
            probe = extractor.extract_image(photo) if isinstance(photo, np.ndarray) else extractor.extract(photo)
        except FaceError as exc:
            attempt = database.VerificationAttempt("invalid_capture", None, threshold)
            capture_error = str(exc)
        else:
            similarity = float(np.clip(np.dot(probe, reference_vector), -1, 1))
            attempt = database.VerificationAttempt(decide(similarity, threshold), similarity, threshold)

    saved = database.record_attempt(settings.database, user_id, request_id, attempt)
    return VerificationResult(saved, capture_error if saved == attempt else None)
