from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
MODELS_DIR = PROJECT_ROOT / "models"
INSPECTION_MODELS_DIR = MODELS_DIR / "inspection"
DETECTION_MODELS_DIR = MODELS_DIR / "detection"
CLASSIFICATION_MODELS_DIR = MODELS_DIR / "classification"
PROFILES_DIR = PROJECT_ROOT / "profiles"
DATA_DIR = PROJECT_ROOT / "data"
INSPECTIONS_DIR = DATA_DIR / "inspections"
LOGS_DIR = PROJECT_ROOT / "logs"
SETTINGS_PATH = PROJECT_ROOT / "config" / "runtime_settings.json"
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
