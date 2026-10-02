from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from image_inspector.core.basler_camera import BaslerCamera
from image_inspector.core.inspection import InspectionService

log = logging.getLogger(__name__)


class CaptureThread(QThread):
    captured = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, camera: BaslerCamera) -> None:
        super().__init__()
        self.camera = camera

    def run(self) -> None:
        try:
            self.captured.emit(self.camera.capture())
        except Exception as exc:
            log.exception("Erro na thread de captura")
            self.failed.emit(str(exc))


class InspectionThread(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(
        self,
        service: InspectionService,
        image: np.ndarray,
        mode: str,
        simple_models: list[Path],
        detection_model: Path | None,
        classification_model: Path | None,
        confidence: float,
    ) -> None:
        super().__init__()
        self.service = service
        self.image = image
        self.mode = mode
        self.simple_models = simple_models
        self.detection_model = detection_model
        self.classification_model = classification_model
        self.confidence = confidence

    def run(self) -> None:
        try:
            if self.mode == "simple":
                if not self.simple_models:
                    raise ValueError("Selecione ao menos um modelo de inspecao.")
                result = self.service.run_multiple_simple(
                    self.image,
                    self.simple_models,
                    self.confidence,
                    lambda name, index, total: self.progress.emit(f"Analisando {name} ({index}/{total})..."),
                )
            else:
                if self.detection_model is None or self.classification_model is None:
                    raise ValueError("Selecione modelos de deteccao e classificacao.")
                self.progress.emit("Analisando produto...")
                result = self.service.run_hybrid(
                    self.image,
                    self.detection_model,
                    self.classification_model,
                    self.confidence,
                    self.confidence,
                )
            self.completed.emit(result)
        except Exception as exc:
            log.exception("Erro na thread de inspecao")
            self.failed.emit(str(exc))
