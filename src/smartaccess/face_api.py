import base64
import binascii
import json
import sqlite3
from hashlib import sha256
from io import BytesIO
from typing import Annotated, Literal
from uuid import UUID

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import database, faces, verification
from .config import CAPTURES_REQUIRED, SFACE, Settings

router = APIRouter(prefix="/api")
MAX_PHOTO_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 1920
MAX_ENCODED_PHOTO = 4 * ((MAX_PHOTO_BYTES + 2) // 3)
MAX_ENROLLMENT_BYTES = CAPTURES_REQUIRED * MAX_ENCODED_PHOTO + 1024
IMAGE_TYPES = ("image/jpeg", "image/png")
UNREADABLE = "L’image est illisible. Reprenez une photo JPEG ou PNG."
QUALITY_MESSAGES = {
    faces.FaceQuality.NO_FACE: "Placez votre visage devant la caméra",
    faces.FaceQuality.MULTIPLE: "Une seule personne doit être visible",
    faces.FaceQuality.TOO_SMALL: "Rapprochez-vous de la caméra",
    faces.FaceQuality.BLURRY: "Stabilisez votre position et améliorez l’éclairage",
    faces.FaceQuality.USABLE: "Visage détecté, prêt à capturer",
}


class PersonInput(BaseModel):
    name: str


class CreatedPerson(BaseModel):
    id: int
    name: str


class FaceStatus(BaseModel):
    has_reference: bool
    captures_required: int = CAPTURES_REQUIRED


class Analysis(BaseModel):
    width: int
    height: int
    boxes: tuple[tuple[int, int, int, int], ...]
    quality: str
    message: str


class AccessResult(BaseModel):
    outcome: Literal["authorized", "denied", "invalid_capture"]
    similarity: float | None
    threshold: float | None
    capture_error: str | None


def problem(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def configured_settings() -> Settings:
    try:
        return Settings()
    except ValueError as exc:
        raise problem(503, "configuration", "Configuration de SmartAccess invalide.") from exc


Config = Annotated[Settings, Depends(configured_settings)]
PersonID = Annotated[int, Path(ge=1, le=2**63 - 1)]


async def read_body(request: Request, limit: int, content_types: tuple[str, ...]) -> bytes:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() not in content_types:
        raise problem(415, "content_type", "Le format de l’envoi n’est pas pris en charge.")
    length = request.headers.get("content-length", "")
    if length.isdecimal() and (len(length) > 12 or int(length) > limit):
        raise problem(413, "image_too_large", "L’envoi dépasse la taille autorisée.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise problem(413, "image_too_large", "L’envoi dépasse la taille autorisée.")
        data.extend(chunk)
    return bytes(data)


def check_dimensions(width: int, height: int) -> None:
    if max(width, height) > MAX_DIMENSION:
        raise problem(413, "image_dimensions", f"L’image dépasse {MAX_DIMENSION} pixels sur un côté.")


def check_image_header(photo: bytes) -> None:
    if len(photo) > MAX_PHOTO_BYTES:
        raise problem(413, "image_too_large", "La photo dépasse 2 Mio.")
    try:
        with Image.open(BytesIO(photo), formats=("JPEG", "PNG")) as image:
            check_dimensions(*image.size)
    except Image.DecompressionBombError as exc:
        raise problem(413, "image_dimensions", "Les dimensions de l’image sont trop grandes.") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise problem(422, "unreadable_image", UNREADABLE) from exc


def decode_image(photo: bytes) -> np.ndarray:
    check_image_header(photo)
    try:
        image = cv2.imdecode(np.frombuffer(photo, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as exc:
        raise problem(422, "unreadable_image", UNREADABLE) from exc
    if image is None:
        raise problem(422, "unreadable_image", UNREADABLE)
    check_dimensions(image.shape[1], image.shape[0])
    return image


def extractor(settings: Settings) -> faces.FaceExtractor:
    try:
        return faces.get_face_extractor(settings)
    except faces.FaceError as exc:
        raise problem(503, "face_models", "Les modèles faciaux ne sont pas disponibles. Vérifiez leur installation.") from exc


def person_status(settings: Settings, user_id: int) -> FaceStatus:
    row = database.person_face_status(settings.database, user_id)
    if row is None:
        raise problem(404, "person_missing", "Cette personne n’existe plus. Actualisez la liste des comptes.")
    return FaceStatus(has_reference=row[0] is not None)


@router.post("/people", status_code=201)
def create_person(payload: PersonInput, settings: Config) -> CreatedPerson:
    try:
        user_id = database.create_user(settings.database, payload.name)
    except ValueError as exc:
        raise problem(422, "invalid_name", "Saisissez un nom ou un pseudonyme.") from exc
    return CreatedPerson(id=user_id, name=payload.name.strip())


@router.get("/people/{user_id}/face")
def get_face_status(user_id: PersonID, settings: Config) -> FaceStatus:
    return person_status(settings, user_id)


def analyze_photo(settings: Settings, photo: bytes) -> Analysis:
    image = decode_image(photo)
    engine = extractor(settings)
    try:
        assessment = engine.assess(image)
    except (cv2.error, faces.FaceError) as exc:
        raise problem(422, "face_analysis", "L’image n’a pas pu être analysée. Reprenez la photo.") from exc
    height, width = image.shape[:2]
    return Analysis(width=width, height=height, boxes=assessment.boxes,
                    quality=assessment.quality.name.lower(), message=QUALITY_MESSAGES[assessment.quality])


@router.post("/faces/analyze")
async def analyze(request: Request, settings: Config) -> Analysis:
    photo = await read_body(request, MAX_PHOTO_BYTES, IMAGE_TYPES)
    return await run_in_threadpool(analyze_photo, settings, photo)


def enrollment_photos(body: bytes) -> list[bytes]:
    try:
        payload = json.loads(body)
        encoded = payload.get("photos") if isinstance(payload, dict) else None
    except (ValueError, RecursionError) as exc:
        raise problem(422, "invalid_enrollment", "L’envoi des captures est illisible.") from exc
    if not isinstance(encoded, list) or len(encoded) != CAPTURES_REQUIRED:
        raise problem(422, "capture_count", f"Enregistrez exactement {CAPTURES_REQUIRED} captures.")
    photos = []
    for value in encoded:
        if not isinstance(value, str):
            raise problem(422, "unreadable_image", UNREADABLE)
        if len(value) > MAX_ENCODED_PHOTO:
            raise problem(413, "image_too_large", "Une photo dépasse 2 Mio.")
        try:
            photo = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise problem(422, "unreadable_image", UNREADABLE) from exc
        check_image_header(photo)
        photos.append(photo)
    if len({sha256(photo).digest() for photo in photos}) != len(photos):
        raise problem(422, "duplicate_capture", "Prenez des photos différentes pour chaque capture.")
    return photos


def enroll(settings: Settings, user_id: int, body: bytes, replace: bool) -> FaceStatus:
    status = person_status(settings, user_id)
    if status.has_reference and not replace:
        raise problem(409, "reference_exists", "Une référence existe déjà. Choisissez explicitement le réenregistrement.")
    photos = enrollment_photos(body)
    engine = extractor(settings)
    samples = []
    for index, photo in enumerate(photos, start=1):
        try:
            samples.append(engine.extract_image(decode_image(photo)))
        except faces.FaceError as exc:
            raise problem(422, "invalid_capture", f"Capture {index} à reprendre. {exc}") from exc
    try:
        reference = faces.build_reference(samples)
    except faces.FaceError as exc:
        raise problem(422, "invalid_reference", "La référence est inexploitable. Recommencez les captures.") from exc
    try:
        saved = database.save_reference(settings.database, user_id, reference, SFACE, faces.REFERENCE_METHOD,
                                        len(photos), replace=replace)
    except sqlite3.IntegrityError:
        person_status(settings, user_id)
        raise
    if not saved:
        raise problem(409, "reference_exists", "Une référence a été enregistrée entre-temps. Actualisez le compte.")
    return FaceStatus(has_reference=True)


@router.post("/people/{user_id}/face")
async def save_face(user_id: PersonID, request: Request, settings: Config, replace: bool = False) -> FaceStatus:
    body = await read_body(request, MAX_ENROLLMENT_BYTES, ("application/json",))
    return await run_in_threadpool(enroll, settings, user_id, body, replace)


def verify_photo(settings: Settings, user_id: int, request_id: str, photo: bytes) -> AccessResult:
    if not person_status(settings, user_id).has_reference:
        raise problem(409, "reference_missing", "Enregistrez le visage de cette personne avant la vérification.")
    capture_error = None
    image: bytes | np.ndarray = b""
    try:
        image = decode_image(photo)
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        capture_error = UNREADABLE
    try:
        result = verification.verify(settings, user_id, request_id, image, capture_error=capture_error)
    except faces.FaceError as exc:
        raise problem(503, "face_models", "Les modèles faciaux ne sont pas disponibles. Vérifiez leur installation.") from exc
    except ValueError as exc:
        raise problem(409, "verification_conflict", str(exc)) from exc
    return AccessResult(outcome=result.attempt.outcome, similarity=result.attempt.similarity,
                        threshold=result.attempt.threshold, capture_error=result.capture_error)


@router.post("/people/{user_id}/verify")
async def verify_access(
    user_id: PersonID, request: Request, settings: Config,
    request_id: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> AccessResult:
    photo = await read_body(request, MAX_PHOTO_BYTES, IMAGE_TYPES)
    return await run_in_threadpool(verify_photo, settings, user_id, str(request_id), photo)
