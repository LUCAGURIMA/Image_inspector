from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class YoloRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class DetectionItem:
    bbox: list[int]
    class_id: int
    class_name: str
    confidence: float


@dataclass(frozen=True)
class Prediction:
    task: str
    model_name: str
    model_path: str
    model_hash: str
    annotated_image: np.ndarray
    raw: dict[str, Any]
    has_findings: bool
    confidence: float
    label: str
    detections: list[DetectionItem]


class YoloModel:
    def __init__(self, model_path: Path, task: str) -> None:
        if not model_path.exists():
            raise FileNotFoundError(f"Modelo nao encontrado: {model_path}")
        self.model_path = model_path.resolve()
        self.task = task
        self.model_hash = file_sha256(self.model_path)
        log.info("Carregando modelo YOLO | task=%s | path=%s | sha256=%s", task, self.model_path, self.model_hash)
        self.model = self._load_model(self.model_path)

    @staticmethod
    def _load_model(model_path: Path):
        try:
            from ultralytics import YOLO
        except OSError as exc:
            raise YoloRuntimeError(
                "Nao foi possivel carregar o PyTorch/Ultralytics. "
                "No Windows isso normalmente indica DLL de Torch/CUDA incompativel ou dependencia ausente. "
                f"Detalhe tecnico: {exc}"
            ) from exc
        except Exception as exc:
            raise YoloRuntimeError(f"Erro ao importar Ultralytics: {exc}") from exc

        try:
            return YOLO(str(model_path))
        except Exception as exc:
            raise YoloRuntimeError(f"Erro ao carregar modelo {model_path.name}: {exc}") from exc

    def predict(self, image: np.ndarray, confidence: float) -> Prediction:
        result = self.model.predict(image, conf=confidence, verbose=False)[0]
        annotated = result.plot()
        if annotated is None:
            annotated = image.copy()

        boxes = getattr(result, "boxes", None)
        probs = getattr(result, "probs", None)
        detections: list[DetectionItem] = []
        has_findings = False
        label = "sem_deteccoes"
        top_conf = 0.0

        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy().astype(int).tolist()
            confs = boxes.conf.cpu().numpy().tolist()
            classes = boxes.cls.cpu().numpy().astype(int).tolist()
            for bbox, conf, cls_id in zip(xyxy, confs, classes):
                detections.append(
                    DetectionItem(
                        bbox=[int(v) for v in bbox],
                        class_id=int(cls_id),
                        class_name=result.names.get(int(cls_id), str(cls_id)),
                        confidence=float(conf),
                    )
                )
            top = max(detections, key=lambda item: item.confidence)
            label = top.class_name
            top_conf = top.confidence
            has_findings = True

        if probs is not None:
            top_idx = int(probs.top1)
            top_conf = float(probs.top1conf)
            label = result.names.get(top_idx, str(top_idx))
            has_findings = label.lower() not in {"bom", "ok", "good", "normal", "saudavel", "aprovado"}

        return Prediction(
            task=self.task,
            model_name=self.model_path.name,
            model_path=str(self.model_path),
            model_hash=self.model_hash,
            annotated_image=annotated,
            raw={"json": result.tojson()},
            has_findings=has_findings,
            confidence=top_conf,
            label=label,
            detections=detections,
        )


class ModelRegistry:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, int], YoloModel] = {}

    def get(self, model_path: Path, task: str) -> YoloModel:
        resolved = model_path.resolve()
        stat = resolved.stat()
        key = (task, str(resolved), int(stat.st_mtime_ns))
        model = self._cache.get(key)
        if model is None:
            stale_keys = [old for old in self._cache if old[0] == task and old[1] == str(resolved)]
            for old in stale_keys:
                self._cache.pop(old, None)
            model = YoloModel(resolved, task)
            self._cache[key] = model
        return model

    def clear(self) -> None:
        self._cache.clear()


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def list_models(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.pt"))
