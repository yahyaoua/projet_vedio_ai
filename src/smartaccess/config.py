import math
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"
YOLO11N = "yolo11n.pt"
FACE_MODEL_HASHES = {
    YUNET: "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    SFACE: "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
}
CAPTURES_REQUIRED = 3


def local_path(variable: str, default: str) -> Path:
    path = Path(os.environ.get(variable, default)).expanduser()
    return ROOT / path


@dataclass(frozen=True)
class Settings:
    database: Path = field(default_factory=lambda: local_path("SMARTACCESS_DB", "data/smartaccess.sqlite3"))
    models: Path = field(default_factory=lambda: local_path("SMARTACCESS_MODELS", "models"))
    test_video: Path = field(default_factory=lambda: local_path("SMARTACCESS_VIDEO", "data/test.mp4"))
    camera_index: int = field(default_factory=lambda: int(os.getenv("SMARTACCESS_CAMERA_INDEX", "0")))
    min_face_pixels: int = field(default_factory=lambda: int(os.getenv("SMARTACCESS_MIN_FACE_PX", "100")))
    min_sharpness: float = field(default_factory=lambda: float(os.getenv("SMARTACCESS_MIN_SHARPNESS", "80")))
    verification_threshold: float = field(
        default_factory=lambda: float(os.getenv("SMARTACCESS_VERIFICATION_THRESHOLD", "0.363"))
    )

    def model_path(self, filename: str) -> Path:
        return self.models / filename

    def __post_init__(self):
        if self.camera_index < 0:
            raise ValueError("L’index de la webcam doit être positif ou nul.")
        if self.min_face_pixels < 1 or not math.isfinite(self.min_sharpness) or self.min_sharpness < 0:
            raise ValueError("Les seuils de taille et de netteté doivent être valides et positifs ou nuls (taille au moins 1).")
        if not -1 <= self.verification_threshold <= 1:
            raise ValueError("Le seuil de similarité doit être compris entre -1 et 1.")
