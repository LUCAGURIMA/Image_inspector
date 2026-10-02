"""Armazenamento local para capturas rotuladas do dataset."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2


@dataclass(frozen=True)
class DatasetCategory:
    name: str
    folder: Path


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_") or "categoria"


def default_categories(dataset_dir: Path) -> list[DatasetCategory]:
    names = ("mancha", "rasgo", "contaminacao")
    return [DatasetCategory(name, dataset_dir / "captures" / safe_name(name)) for name in names]


def load_categories(config_path: Path, dataset_dir: Path) -> list[DatasetCategory]:
    if not config_path.exists():
        categories = default_categories(dataset_dir)
        save_categories(config_path, categories)
        return categories
    data = json.loads(config_path.read_text(encoding="utf-8"))
    categories: list[DatasetCategory] = []
    for item in data.get("categories", []):
        name = str(item.get("name", "")).strip()
        folder_value = str(item.get("folder", "")).strip()
        if not name or not folder_value:
            continue
        folder = Path(folder_value)
        if not folder.is_absolute():
            folder = dataset_dir / folder
        categories.append(DatasetCategory(name, folder.resolve()))
    return categories or default_categories(dataset_dir)


def save_categories(config_path: Path, categories: list[DatasetCategory]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "categories": [
            {"name": category.name, "folder": os.path.relpath(category.folder, config_path.parent)}
            for category in categories
        ]
    }
    temporary = config_path.with_name(f".{config_path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, config_path)


def example_descriptor(category: DatasetCategory) -> Path:
    return category.folder / f"{safe_name(category.name)}_example.txt"


def example_image(category: DatasetCategory) -> Path | None:
    descriptor = example_descriptor(category)
    try:
        value = descriptor.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not value:
        return None
    image = Path(value)
    if not image.is_absolute():
        image = descriptor.parent / image
    return image if image.is_file() else None


def set_example_image(category: DatasetCategory, source: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    category.folder.mkdir(parents=True, exist_ok=True)
    destination = category.folder / f"{safe_name(category.name)}_example{source.suffix.lower()}"
    shutil.copy2(source, destination)
    descriptor = example_descriptor(category)
    temporary = descriptor.with_name(f".{descriptor.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(destination.name + "\n", encoding="utf-8")
    os.replace(temporary, descriptor)
    return destination


def save_dataset_capture(
    image,
    category: DatasetCategory,
    camera_serial: str,
    operator: str,
    image_format: str = "jpg",
    jpeg_quality: int = 90,
) -> Path:
    extension = ".png" if image_format.lower() == "png" else ".jpg"
    timestamp = datetime.now()
    filename = f"{safe_name(category.name)}_{timestamp:%Y%m%d_%H%M%S}_{safe_name(camera_serial)}{extension}"
    category.folder.mkdir(parents=True, exist_ok=True)
    image_path = category.folder / filename
    if image_path.exists():
        filename = f"{safe_name(category.name)}_{timestamp:%Y%m%d_%H%M%S_%f}_{safe_name(camera_serial)}{extension}"
        image_path = category.folder / filename
    temporary = category.folder / f".{image_path.stem}.{uuid.uuid4().hex}.tmp{extension}"
    params = [cv2.IMWRITE_JPEG_QUALITY, max(0, min(100, int(jpeg_quality)))] if extension == ".jpg" else []
    if not cv2.imwrite(str(temporary), image, params):
        raise OSError(f"Não foi possível gravar a imagem: {temporary}")
    os.replace(temporary, image_path)
    metadata = {
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "category": category.name,
        "operator": operator.strip(),
        "camera_serial": camera_serial,
        "file_path": str(image_path.resolve()),
    }
    metadata_path = image_path.with_suffix(".json")
    metadata_tmp = metadata_path.with_name(f".{metadata_path.name}.{uuid.uuid4().hex}.tmp")
    metadata_tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(metadata_tmp, metadata_path)
    return image_path


def signal_dataset_export(dataset_dir: Path, image_paths: list[Path]) -> Path:
    queue = dataset_dir / "export_queue.jsonl"
    with queue.open("a", encoding="utf-8") as stream:
        for image_path in image_paths:
            stream.write(json.dumps({"queued_at": datetime.now().isoformat(timespec="seconds"), "file_path": str(image_path)}, ensure_ascii=False) + "\n")
    return queue
