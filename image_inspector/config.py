from __future__ import annotations

import sys
import os
from pathlib import Path


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
if os.name == "nt":
    _user_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
else:
    _user_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
USER_DATA_DIR = _user_root / "Image Inspector"
MODELS_DIR = USER_DATA_DIR / "models"
INSPECTION_MODELS_DIR = MODELS_DIR / "inspection"
DETECTION_MODELS_DIR = MODELS_DIR / "detection"
CLASSIFICATION_MODELS_DIR = MODELS_DIR / "classification"
PROFILES_DIR = USER_DATA_DIR / "profiles"
DATA_DIR = USER_DATA_DIR / "data"
INSPECTIONS_DIR = DATA_DIR / "inspections"
LOGS_DIR = USER_DATA_DIR / "logs"
SETTINGS_PATH = USER_DATA_DIR / "config" / "runtime_settings.json"
DEFAULT_CONFIDENCE = 0.55
WINDOW_TITLE = "Image Inspector"
REVIEW_LABELS = {
    "tp": "verdadeiro_positivo",
    "tn": "verdadeiro_negativo",
    "fp": "falso_positivo",
    "fn": "falso_negativo",
}


def ensure_project_dirs() -> None:
    for path in (
        INSPECTION_MODELS_DIR,
        DETECTION_MODELS_DIR,
        CLASSIFICATION_MODELS_DIR,
        PROFILES_DIR,
        INSPECTIONS_DIR,
        LOGS_DIR,
        SETTINGS_PATH.parent,
    ):
        path.mkdir(parents=True, exist_ok=True)


def category_reference_dir(model_path: Path) -> Path:
    """Return the per-category assets folder for an inspection model."""
    return INSPECTION_MODELS_DIR / model_path.stem


def ensure_category_assets(model_path: Path) -> Path:
    """Create a category folder and a usable default reference image if needed."""
    import cv2
    import numpy as np

    folder = category_reference_dir(model_path)
    folder.mkdir(parents=True, exist_ok=True)
    reference = folder / "reference.png"
    if not reference.exists():
        bundled_reference = PROJECT_ROOT / "models" / "inspection" / model_path.stem / "reference.png"
        if bundled_reference.exists():
            import shutil
            shutil.copy2(bundled_reference, reference)
            return reference
        image = np.full((240, 360, 3), 246, dtype=np.uint8)
        cv2.rectangle(image, (2, 2), (357, 237), (190, 200, 215), 2)
        cv2.putText(image, model_path.stem[:28], (18, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (45, 60, 80), 2, cv2.LINE_AA)
        cv2.putText(image, "Sem imagem cadastrada", (18, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (95, 105, 120), 1, cv2.LINE_AA)
        cv2.imwrite(str(reference), image)
    return reference
