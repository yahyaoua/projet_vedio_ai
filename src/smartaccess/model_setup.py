"""Téléchargement officiel et contrôle local des poids SmartAccess."""

import argparse
import os
import shutil
import sys
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import ZipFile

from .config import FACE_MODEL_HASHES, SFACE, YOLO11N, YUNET, Settings

ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
SOURCES = {
    YUNET: f"{ZOO}/face_detection_yunet/{YUNET}",
    SFACE: f"{ZOO}/face_recognition_sface/{SFACE}",
    YOLO11N: f"https://github.com/ultralytics/assets/releases/download/v8.3.0/{YOLO11N}",
}


def check_file(path: Path, name: str) -> None:
    with path.open("rb") as stream:
        header = stream.read(512).lstrip().lower()
        if header.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError("pointeur Git LFS")
        if header.startswith((b"<!doctype html", b"<html")):
            raise ValueError("page HTML")
        if name in FACE_MODEL_HASHES:
            stream.seek(0)
            if file_digest(stream, "sha256").hexdigest() != FACE_MODEL_HASHES[name]:
                raise ValueError("empreinte SHA-256 différente de celle d’OpenCV Zoo")
            return

    with ZipFile(path) as archive:
        if not any(member.endswith("/data.pkl") for member in archive.namelist()):
            raise ValueError("archive PyTorch sans point de contrôle")
        damaged = archive.testzip()
        if damaged is not None:
            raise ValueError(f"archive PyTorch endommagée ({damaged})")


def download_missing(path: Path, name: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as staging:
        temporary = Path(staging) / name
        with urlopen(SOURCES[name], timeout=30) as response, temporary.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        check_file(temporary, name)
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass


def check_load(settings: Settings, name: str) -> str:
    if name == YOLO11N:
        import ultralytics

        from .counting import load_yolo

        load_yolo(settings)
        return f"Ultralytics {ultralytics.__version__}"

    import cv2

    path = str(settings.model_path(name))
    if name == YUNET:
        cv2.FaceDetectorYN.create(path, "", (320, 320))
    else:
        cv2.FaceRecognizerSF.create(path, "")
    return f"OpenCV {cv2.__version__}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Télécharger uniquement les poids manquants")
    args = parser.parse_args()
    settings = Settings()
    failed = False
    for name in SOURCES:
        path = settings.model_path(name)
        try:
            if args.download:
                download_missing(path, name)
            check_file(path, name)
            print(f"{path} — {path.stat().st_size} octets — fichier contrôlé", flush=True)
            print(f"  Chargement réussi avec {check_load(settings, name)}")
        except Exception as exc:
            failed = True
            print(f"{path} — {type(exc).__name__}: {exc}", file=sys.stderr)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
