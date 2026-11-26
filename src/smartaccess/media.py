import argparse
from contextlib import contextmanager
from threading import Lock

import cv2

from .config import Settings

CAMERA_LOCK = Lock()


class MediaError(ValueError):
    pass


@contextmanager
def open_capture(source: int | str, backend: int = cv2.CAP_ANY):
    webcam = isinstance(source, int)
    if webcam and not CAMERA_LOCK.acquire(blocking=False):
        raise MediaError("La webcam est déjà utilisée dans SmartAccess. Arrête le comptage ou attends la fin de la capture.")
    try:
        capture = cv2.VideoCapture()
        try:
            try:
                opened = capture.open(source, backend)
            except cv2.error as exc:
                raise MediaError(f"OpenCV n’a pas pu ouvrir la source : {source}.") from exc
            if not opened:
                if webcam:
                    raise MediaError(f"Webcam {source} inaccessible. Vérifie l’index, les permissions Windows et les applications ouvertes.")
                raise MediaError(f"Vidéo inaccessible : {source}. Vérifie le chemin et le codec.")
            yield capture
        finally:
            capture.release()
    finally:
        if webcam:
            CAMERA_LOCK.release()


def frames(capture):
    while True:
        try:
            success, image = capture.read()
        except cv2.error as exc:
            raise MediaError("OpenCV n’a pas pu lire l’image.") from exc
        if not success or image is None:
            return
        yield image


def take_photo(index: int) -> bytes:
    try:
        with open_capture(index) as capture:
            image = next(frames(capture), None)
            if image is None:
                raise ValueError("Webcam ouverte, mais aucune image reçue. Réessaie après avoir vérifié la caméra.")
        success, encoded = cv2.imencode(".jpg", image)
    except cv2.error as exc:
        raise ValueError("OpenCV ne peut pas lire la webcam. Vérifie l’index et les permissions Windows.") from exc
    if not success:
        raise ValueError("Impossible d’encoder la photo de la webcam.")
    return encoded.tobytes()


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostic OpenCV, sans enregistrement d’image.")
    commands = parser.add_subparsers(dest="command", required=True)
    webcam = commands.add_parser("webcam", help="Lire une image de la webcam puis la libérer")
    webcam.add_argument("--index", type=int, default=0)
    webcam.add_argument("--backend", choices=("auto", "dshow", "msmf"), default="auto")
    video = commands.add_parser("video", help="Décoder les images de la vidéo de test")
    video.add_argument("path", nargs="?")
    args = parser.parse_args()

    try:
        if args.command == "webcam":
            backends = {"auto": cv2.CAP_ANY, "dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}
            with open_capture(args.index, backends[args.backend]) as capture:
                image = next(frames(capture), None)
                if image is None:
                    raise ValueError("Webcam ouverte, mais aucune image reçue.")
                height, width = image.shape[:2]
                print(f"Image reçue : {width} × {height}, via {capture.getBackendName()}.")
        else:
            source = args.path or str(Settings().test_video)
            with open_capture(source) as capture:
                count = sum(1 for _ in frames(capture))
                if not count:
                    raise ValueError("La vidéo est ouverte, mais aucune image n’a été décodée.")
                print(f"{count} images décodées.")
    except (ValueError, cv2.error) as exc:
        parser.exit(1, f"Erreur : {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
