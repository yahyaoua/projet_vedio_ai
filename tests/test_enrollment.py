from threading import Lock
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from src.smartaccess import database, preview
from src.smartaccess.config import Settings
from src.smartaccess.faces import FaceError, FaceExtractor, FaceQuality, build_reference
from src.smartaccess.media import open_capture


def test_reference_lifecycle(tmp_path):
    path = tmp_path / "test.sqlite3"
    database.initialize(path)
    database.create_user(path, "O'Neil")
    user_id, name = next(iter(database.list_users(path).items()))
    assert name == "O'Neil"
    vectors = np.eye(128, dtype=np.float32)[:3]
    with pytest.raises(FaceError):
        build_reference(list(vectors[:2]))
    reference = build_reference(list(vectors))
    np.testing.assert_allclose(np.frombuffer(reference, "<f4")[:3], np.sqrt(1 / 3))
    database.save_reference(path, user_id, reference, "SFace", "test", 3)
    with database.connection(path) as db:
        db.execute("INSERT INTO verification_attempts (user_id, outcome) VALUES (?, ?)", (user_id, "denied"))
    database.initialize(path)
    assert database.reference_count(path, user_id) == 3
    assert database.delete_user(path, user_id)
    assert not database.list_users(path)
    assert database.reference_count(path, user_id) is None
    with database.connection(path) as db:
        assert db.execute("SELECT user_id, outcome FROM verification_attempts").fetchone() == (None, "denied")


@pytest.mark.parametrize(("boxes", "quality", "message"), [
    (None, FaceQuality.NO_FACE, "Aucun visage"),
    ([[10, 10, 110, 110]] * 2, FaceQuality.MULTIPLE, "Plusieurs visages"),
    ([[10, 10, 40, 40]], FaceQuality.TOO_SMALL, "trop petit"),
    ([[10, 10, 110, 110]], FaceQuality.BLURRY, "flou"),
])
def test_reject_invalid_capture(boxes, quality, message):
    extractor = FaceExtractor.__new__(FaceExtractor)
    extractor._lock = Lock()
    extractor.settings = Settings(min_face_pixels=100, min_sharpness=80)
    extractor.detector = SimpleNamespace(
        setInputSize=lambda size: None, detect=lambda image: (1, boxes)
    )
    image = np.zeros((128, 128, 3), dtype=np.uint8)
    assessment = extractor.assess(image)
    assert assessment.quality is quality
    assert len(assessment.boxes) == len(boxes or ())
    _, photo = cv2.imencode(".png", image)
    with pytest.raises(FaceError, match=message):
        extractor.extract(photo.tobytes())


def test_capture_released_after_read_failure(monkeypatch):
    released = []
    capture = SimpleNamespace(open=lambda *args: True, release=lambda: released.append(True))
    monkeypatch.setattr(cv2, "VideoCapture", lambda: capture)
    with pytest.raises(RuntimeError), open_capture(0):
        raise RuntimeError("read failed")
    assert released == [True]


def test_webcam_is_exclusive_and_reopens_after_release(monkeypatch):
    opened = []
    capture = SimpleNamespace(
        open=lambda source, backend: opened.append(source) or True, release=lambda: None,
    )
    monkeypatch.setattr(cv2, "VideoCapture", lambda: capture)
    with open_capture(0):
        with pytest.raises(ValueError, match="déjà utilisée"), open_capture(1):
            pytest.fail("Une deuxième webcam a été ouverte.")
    with open_capture(1):
        pass
    assert opened == [0, 1]


def test_preview_reports_unavailable_if_no_image_is_received(monkeypatch):
    released = []
    camera = SimpleNamespace(
        open=lambda *args: True, read=lambda: (False, None), release=lambda: released.append(True),
    )
    monkeypatch.setattr(cv2, "VideoCapture", lambda: camera)
    monkeypatch.setattr(preview, "get_face_extractor", lambda settings: object())
    run = preview.FacePreview(Settings())
    assert run.snapshot().status == "opening"
    run._run()
    assert run.snapshot().status == "unavailable"
    assert run.snapshot().frame is None
    assert released == [True]


def test_valid_capture_aligns_before_extracting():
    extractor = FaceExtractor.__new__(FaceExtractor)
    extractor._lock = Lock()
    extractor.settings = Settings(min_face_pixels=100, min_sharpness=0)
    detected = np.array([[10, 10, 110, 110]], dtype=np.float32)
    extractor.detector = SimpleNamespace(
        setInputSize=lambda size: None, detect=lambda image: (1, detected)
    )
    aligned = np.ones((112, 112, 3), dtype=np.uint8)

    def align(image, face):
        assert image.shape == (128, 128, 3)
        np.testing.assert_array_equal(face, detected[0])
        return aligned

    def feature(image):
        assert image is aligned
        return np.ones((1, 128), dtype=np.float32)

    extractor.recognizer = SimpleNamespace(alignCrop=align, feature=feature)
    _, photo = cv2.imencode(".png", np.zeros((128, 128, 3), dtype=np.uint8))
    vector = extractor.extract(photo.tobytes())
    assert vector.shape == (128,)
    assert np.linalg.norm(vector) == pytest.approx(1.0)
