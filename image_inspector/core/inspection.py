from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import cv2
import numpy as np

from image_inspector.core.yolo_models import ModelRegistry, Prediction


@dataclass
class InspectionResult:
    mode: str
    original_image: np.ndarray
    annotated_image: np.ndarray
    summary: str
    status: str
    payload: dict[str, Any]
    inspection_id: str = field(default_factory=lambda: uuid4().hex)
    inference_ms: float = 0.0


class InspectionService:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry()

    def run_simple(self, image: np.ndarray, model_path: Path, confidence: float) -> InspectionResult:
        start = perf_counter()
        model = self.registry.get(model_path, "inspection")
        prediction = model.predict(image, confidence)
        elapsed_ms = (perf_counter() - start) * 1000

        status = "reprovado" if prediction.has_findings else "aprovado"
        return InspectionResult(
            mode="simple",
            original_image=image,
            annotated_image=prediction.annotated_image,
            summary=f"{status.upper()} | {prediction.label} ({prediction.confidence:.2f})",
            status=status,
            inference_ms=elapsed_ms,
            payload={
                "thresholds": {"inspection": confidence},
                "models": {"inspection": _prediction_model_info(prediction)},
                "prediction": _prediction_payload(prediction),
            },
        )

    def run_hybrid(
        self,
        image: np.ndarray,
        detection_model_path: Path,
        classification_model_path: Path,
        detection_confidence: float,
        classification_confidence: float,
    ) -> InspectionResult:
        start = perf_counter()
        detector = self.registry.get(detection_model_path, "detection")
        classifier = self.registry.get(classification_model_path, "classification")

        detection = detector.predict(image, detection_confidence)
        annotated = image.copy()
        classifications: list[dict[str, Any]] = []

        for i, item in enumerate(detection.detections, start=1):
            x1, y1, x2, y2 = _clamp_box(item.bbox, image.shape)
            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            cls_prediction = classifier.predict(crop, classification_confidence)
            classifications.append(
                {
                    "detection": {
                        "bbox": [x1, y1, x2, y2],
                        "class_id": item.class_id,
                        "class_name": item.class_name,
                        "confidence": item.confidence,
                    },
                    "classification": {
                        "label": cls_prediction.label,
                        "confidence": cls_prediction.confidence,
                        "has_findings": cls_prediction.has_findings,
                    },
                }
            )
            color = (0, 0, 255) if cls_prediction.has_findings else (0, 180, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
            cv2.putText(
                annotated,
                f"{i}: {cls_prediction.label} {cls_prediction.confidence:.2f}",
                (x1, max(24, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
                cv2.LINE_AA,
            )

        elapsed_ms = (perf_counter() - start) * 1000
        has_findings = any(item["classification"]["has_findings"] for item in classifications)
        status = "reprovado" if has_findings else "aprovado"
        summary = f"{status.upper()} | {len(classifications)} item(ns) classificados | {elapsed_ms:.0f} ms"
        return InspectionResult(
            mode="hybrid",
            original_image=image,
            annotated_image=annotated,
            summary=summary,
            status=status,
            inference_ms=elapsed_ms,
            payload={
                "thresholds": {
                    "detection": detection_confidence,
                    "classification": classification_confidence,
                },
                "models": {
                    "detection": _prediction_model_info(detection),
                    "classification": {
                        "name": classifier.model_path.name,
                        "path": str(classifier.model_path),
                        "sha256": classifier.model_hash,
                    },
                },
                "detections": [_detection_payload(item) for item in detection.detections],
                "classifications": classifications,
                "detection_raw": detection.raw,
            },
        )


def _prediction_model_info(prediction: Prediction) -> dict[str, Any]:
    return {
        "name": prediction.model_name,
        "path": prediction.model_path,
        "sha256": prediction.model_hash,
    }


def _prediction_payload(prediction: Prediction) -> dict[str, Any]:
    return {
        "task": prediction.task,
        "label": prediction.label,
        "confidence": prediction.confidence,
        "has_findings": prediction.has_findings,
        "detections": [_detection_payload(item) for item in prediction.detections],
        "raw": prediction.raw,
    }


def _detection_payload(item) -> dict[str, Any]:
    return {
        "bbox": item.bbox,
        "class_id": item.class_id,
        "class_name": item.class_name,
        "confidence": item.confidence,
    }


def _clamp_box(box: list[int], shape: tuple[int, ...]) -> tuple[int, int, int, int]:
    h, w = shape[:2]
    x1, y1, x2, y2 = box
    return max(0, x1), max(0, y1), min(w, x2), min(h, y2)
