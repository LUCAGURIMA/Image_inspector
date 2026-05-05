from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from image_inspector.config import LOGS_DIR, SETTINGS_PATH, ensure_project_dirs


@dataclass
class RuntimeSettings:
    operator_name: str = ""
    mode: str = "simple"
    simple_model: str = ""
    detection_model: str = ""
    classification_model: str = ""
    confidence: float = 0.55
    profile: str = ""


class SettingsStore:
    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path

    def load(self) -> RuntimeSettings:
        if not self.path.exists():
            return RuntimeSettings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = RuntimeSettings.__dataclass_fields__.keys()
            return RuntimeSettings(**{key: data.get(key) for key in allowed if key in data})
        except Exception:
            logging.getLogger(__name__).exception("Falha ao carregar configuracoes persistidas")
            return RuntimeSettings()

    def save(self, settings: RuntimeSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")


def setup_logging() -> None:
    ensure_project_dirs()
    log_file = LOGS_DIR / "system.log"
    error_file = LOGS_DIR / "errors.log"

    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    error_handler = logging.FileHandler(error_file, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)


def jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return jsonable(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "shape"):
        return f"<array shape={value.shape}>"
    return value
