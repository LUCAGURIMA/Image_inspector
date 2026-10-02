from __future__ import annotations

import csv
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2

from image_inspector.config import INSPECTIONS_DIR, REVIEW_LABELS
from image_inspector.core.inspection import InspectionResult
from image_inspector.core.runtime import jsonable

log = logging.getLogger(__name__)


class InspectionStorage:
    def save_review(
        self,
        result: InspectionResult,
        review_code: str,
        operator_note: str = "",
        context: dict[str, Any] | None = None,
    ) -> Path:
        if review_code not in REVIEW_LABELS:
            raise ValueError(f"Revisao invalida: {review_code}")

        now = datetime.now()
        label = REVIEW_LABELS[review_code]
        day_dir = INSPECTIONS_DIR / now.strftime("%Y-%m-%d")
        session_dir = day_dir / label / f"{now:%H%M%S}_{result.inspection_id[:8]}"
        session_dir.mkdir(parents=True, exist_ok=True)

        categories = (context or {}).get("review_categories", [])
        category_prefix = "_".join(
            re.sub(r"[^A-Za-z0-9_-]+", "-", str(category)).strip("-_")[:28]
            for category in categories
        )[:100]
        suffix = f"_{category_prefix}" if category_prefix else ""
        original_path = session_dir / f"original{suffix}.jpg"
        metadata_path = session_dir / "metadata.json"

        if not cv2.imwrite(str(original_path), result.original_image):
            raise OSError(f"Falha ao salvar imagem original em {original_path}")
        annotated_by_category = {}
        if result.category_images:
            for category, image in result.category_images.items():
                slug = re.sub(r"[^A-Za-z0-9_-]+", "-", category).strip("-_")[:48] or "categoria"
                annotated_path = session_dir / f"annotated_{slug}.jpg"
                if not cv2.imwrite(str(annotated_path), image):
                    raise OSError(f"Falha ao salvar imagem anotada em {annotated_path}")
                annotated_by_category[category] = annotated_path.name
            primary_annotated = next(iter(annotated_by_category.values()))
        else:
            annotated_path = session_dir / f"annotated{suffix}.jpg"
            if not cv2.imwrite(str(annotated_path), result.annotated_image):
                raise OSError(f"Falha ao salvar imagem anotada em {annotated_path}")
            primary_annotated = annotated_path.name

        metadata = {
            "inspection_id": result.inspection_id,
            "timestamp": now.isoformat(timespec="seconds"),
            "review": label,
            "operator_note": operator_note,
            "mode": result.mode,
            "status": result.status,
            "summary": result.summary,
            "inference_ms": round(result.inference_ms, 3),
            "context": jsonable(context or {}),
            "payload": jsonable(result.payload),
            "files": {
                "original": original_path.name,
                "annotated": primary_annotated,
                "annotated_by_category": annotated_by_category,
            },
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        self._append_daily_index(day_dir, metadata, session_dir)
        log.info("Revisao salva | id=%s | review=%s | path=%s", result.inspection_id, label, session_dir)
        return session_dir

    def _append_daily_index(self, day_dir: Path, metadata: dict[str, Any], session_dir: Path) -> None:
        index_path = day_dir / "index.csv"
        row = {
            "inspection_id": metadata["inspection_id"],
            "timestamp": metadata["timestamp"],
            "review": metadata["review"],
            "mode": metadata["mode"],
            "status": metadata["status"],
            "inference_ms": metadata["inference_ms"],
            "operator": metadata.get("context", {}).get("operator", ""),
            "camera_serial": metadata.get("context", {}).get("camera", {}).get("serial", ""),
            "profile": metadata.get("context", {}).get("profile", {}).get("name", ""),
            "categories": ";".join(metadata.get("context", {}).get("review_categories", [])),
            "path": str(session_dir),
        }
        fields: list[str]
        if index_path.exists():
            with index_path.open("r", newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                old_fields = reader.fieldnames or []
                old_rows = list(reader)
            fields = old_fields + [name for name in row if name not in old_fields]
            if fields != old_fields:
                temporary = index_path.with_suffix(".csv.tmp")
                with temporary.open("w", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(old_rows)
                os.replace(temporary, index_path)
        else:
            fields = list(row)
            with index_path.open("w", newline="", encoding="utf-8") as file:
                csv.DictWriter(file, fieldnames=fields).writeheader()
        with index_path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writerow(row)
