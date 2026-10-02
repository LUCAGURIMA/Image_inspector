"""Tela de coleta manual de imagens para criar datasets rotulados."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
from PyQt5.QtCore import QSize, QThread, QTimer, pyqtSignal, Qt
from PyQt5.QtGui import QImage, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QVBoxLayout, QWidget,
)

from image_inspector.config import DATA_DIR
from image_inspector.core.basler_camera import BaslerCamera
from image_inspector.core.dataset_collection import (
    DatasetCategory, example_image, load_categories, safe_name,
    save_categories, save_dataset_capture, set_example_image,
    signal_dataset_export,
)
from image_inspector.ui.threads import CaptureThread

log = logging.getLogger(__name__)


class _PreviewThread(QThread):
    frame_ready = pyqtSignal(object)
    camera_error = pyqtSignal(str)

    def __init__(self, camera: BaslerCamera) -> None:
        super().__init__()
        self.camera = camera
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                self.frame_ready.emit(self.camera.capture())
            except Exception as exc:
                if self._running:
                    self.camera_error.emit(str(exc))
                self.msleep(500)

    def stop(self) -> None:
        self._running = False
        self.wait(6500)


class DatasetTab(QWidget):
    def __init__(self, camera: BaslerCamera, reconnect_camera=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.camera = camera
        self.reconnect_camera = reconnect_camera
        self.dataset_dir = DATA_DIR / "dataset"
        self.config_path = self.dataset_dir / "categories.json"
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        self.categories = load_categories(self.config_path, self.dataset_dir)
        self.selected_category: DatasetCategory | None = None
        self.saved_paths: list[Path] = []
        self._preview_thread: _PreviewThread | None = None
        self._capture_thread: CaptureThread | None = None
        self._preview_frozen = False
        self._resume_preview_timer = QTimer(self)
        self._resume_preview_timer.setSingleShot(True)
        self._resume_preview_timer.setInterval(1800)
        self._resume_preview_timer.timeout.connect(self._resume_preview)
        self._last_frame = None
        self.category_buttons: dict[DatasetCategory, QPushButton] = {}
        self._build_ui()
        self._rebuild_categories()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QWidget { font-size: 18px; } "
            "QPushButton { min-height: 56px; padding: 10px; font-weight: bold; }"
        )
        outer = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.preview = QLabel("Abra a aba para iniciar a visualização da câmera")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(0, 0)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setStyleSheet("background: #111; color: white; border-radius: 8px;")
        self.splitter.addWidget(self.preview)

        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.addWidget(QLabel("Operador"))
        self.operator_input = QLineEdit()
        self.operator_input.setPlaceholderText("Nome do operador (opcional)")
        panel_layout.addWidget(self.operator_input)
        panel_layout.addWidget(QLabel("Selecione um defeito"))
        self.category_scroll = QScrollArea()
        self.category_scroll.setWidgetResizable(True)
        self.category_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.category_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.category_list = QWidget()
        self.category_layout = QVBoxLayout(self.category_list)
        self.category_layout.setContentsMargins(4, 4, 4, 4)
        self.category_scroll.setWidget(self.category_list)
        panel_layout.addWidget(self.category_scroll, 1)

        category_actions = QHBoxLayout()
        add_button = QPushButton("+ CATEGORIA")
        add_button.clicked.connect(self.add_category)
        remove_button = QPushButton("REMOVER")
        remove_button.setStyleSheet("background: #a42020; color: white;")
        remove_button.clicked.connect(self.remove_category)
        category_actions.addWidget(add_button)
        category_actions.addWidget(remove_button)
        panel_layout.addLayout(category_actions)
        self.reference_button = QPushButton("ADICIONAR / TROCAR IMAGEM")
        self.reference_button.clicked.connect(self.choose_reference)
        panel_layout.addWidget(self.reference_button)
        self.capture_button = QPushButton("TIRAR FOTO")
        self.capture_button.setMinimumHeight(68)
        self.capture_button.setStyleSheet("background: #087f23; color: white; font-size: 25px;")
        self.capture_button.clicked.connect(self.capture)
        panel_layout.addWidget(self.capture_button)
        self.export_button = QPushButton("ENVIAR / EXPORTAR")
        self.export_button.clicked.connect(self.export_session)
        panel_layout.addWidget(self.export_button)
        self.status = QLabel("Pronto para capturar.")
        self.status.setWordWrap(True)
        panel_layout.addWidget(self.status)
        self.splitter.addWidget(panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        outer.addWidget(self.splitter, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        orientation = Qt.Horizontal if self.width() >= 950 else Qt.Vertical
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
            if orientation == Qt.Horizontal:
                self.splitter.setSizes([self.width() * 3 // 5, self.width() * 2 // 5])
            else:
                self.splitter.setSizes([self.height() // 2, self.height() // 2])
        self._render_frame()

    def start_preview(self) -> None:
        if not self.camera.is_open:
            self.status.setText("Câmera indisponível. Conecte a câmera na aba Configuração.")
            self.preview.setText("Câmera não conectada")
            return
        if self._preview_thread and self._preview_thread.isRunning():
            return
        self._preview_frozen = False
        self._preview_thread = _PreviewThread(self.camera)
        self._preview_thread.frame_ready.connect(self._show_frame)
        self._preview_thread.camera_error.connect(self._show_camera_error)
        self._preview_thread.start()

    def stop_preview(self) -> None:
        thread = self._preview_thread
        self._preview_thread = None
        if thread and thread.isRunning():
            thread.stop()

    def _show_frame(self, frame) -> None:
        if self._preview_frozen:
            return
        self._last_frame = frame.copy()
        self._render_frame()

    def _render_frame(self) -> None:
        if self._last_frame is None or self.preview.width() < 2 or self.preview.height() < 2:
            return
        rgb = cv2.cvtColor(self._last_frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _show_camera_error(self, message: str) -> None:
        self.status.setText(f"Visualização da câmera: {message}")

    def _rebuild_categories(self) -> None:
        while self.category_layout.count():
            item = self.category_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.category_buttons.clear()
        for category in self.categories:
            button = QPushButton()
            button.setCheckable(True)
            button.setMinimumHeight(135)
            button.setToolTip(f"Pasta: {category.folder}")
            button.clicked.connect(lambda _checked=False, item=category: self.select_category(item))
            reference = example_image(category)
            if reference:
                pixmap = QPixmap(str(reference))
                if not pixmap.isNull():
                    button.setIcon(QIcon(pixmap))
                    button.setIconSize(QSize(120, 90))
            if reference:
                button.setText(category.name)
            else:
                button.setText(f"{category.name}\nSem imagem de referência")
            button.setToolTip("Toque para selecionar esta categoria")
            button.setStyleSheet("text-align: left; padding: 12px; color: #18212f; border: 2px solid #777; border-radius: 10px; background: #f5f5f5;")
            self.category_layout.addWidget(button)
            self.category_buttons[category] = button
        self.category_layout.addStretch(1)
        if self.selected_category not in self.category_buttons:
            self.selected_category = None
        self._refresh_selection()

    def select_category(self, category: DatasetCategory) -> None:
        self.selected_category = category
        self._refresh_selection()
        self.status.setText(f"Categoria selecionada: {category.name}")

    def _refresh_selection(self) -> None:
        for category, button in self.category_buttons.items():
            selected = category == self.selected_category
            button.blockSignals(True)
            button.setChecked(selected)
            button.blockSignals(False)
            border = "4px solid #1786d1" if selected else "2px solid #777"
            background = "#dff0ff" if selected else "#f5f5f5"
            button.setStyleSheet(f"text-align: left; padding: 12px; color: #18212f; border: {border}; border-radius: 10px; background: {background};")

    def add_category(self) -> None:
        name, accepted = QInputDialog.getText(self, "Nova categoria", "Nome da categoria:")
        name = name.strip()
        if not accepted or not name:
            return
        if any(item.name.casefold() == name.casefold() for item in self.categories):
            QMessageBox.warning(self, "Categoria existente", "Já existe uma categoria com esse nome.")
            return
        folder = self.dataset_dir / "captures" / safe_name(name)
        category = DatasetCategory(name, folder)
        self.categories.append(category)
        try:
            category.folder.mkdir(parents=True, exist_ok=True)
            save_categories(self.config_path, self.categories)
        except Exception as exc:
            self.categories.remove(category)
            QMessageBox.critical(self, "Erro ao criar categoria", str(exc))
            return
        self.selected_category = category
        self._rebuild_categories()
        self.status.setText(f"Categoria criada: {name}")

    def remove_category(self) -> None:
        if not self.selected_category:
            QMessageBox.information(self, "Categoria", "Selecione a categoria que deseja remover da lista.")
            return
        if len(self.categories) <= 1:
            QMessageBox.warning(self, "Última categoria", "Mantenha ao menos uma categoria no dataset.")
            return
        category = self.selected_category
        answer = QMessageBox.question(self, "Remover categoria", f"Remover '{category.name}' da lista?\nAs fotos e a pasta não serão apagadas.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.categories = [item for item in self.categories if item != category]
        self.selected_category = None
        save_categories(self.config_path, self.categories)
        self._rebuild_categories()
        self.status.setText(f"Categoria removida da lista: {category.name}")

    def choose_reference(self) -> None:
        if not self.selected_category:
            QMessageBox.information(self, "Imagem de referência", "Selecione uma categoria primeiro.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Imagem de referência", "", "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not filename:
            return
        try:
            saved = set_example_image(self.selected_category, Path(filename))
            self._rebuild_categories()
            self.status.setText(f"Imagem de referência salva: {saved.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Erro na imagem de referência", str(exc))

    def capture(self) -> None:
        if not self.selected_category:
            QMessageBox.information(self, "Categoria", "Selecione uma categoria antes de tirar a foto.")
            return
        if not self.camera.is_open and self.reconnect_camera:
            self.status.setText("Reconectando à câmera...")
            self.reconnect_camera()
        if not self.camera.is_open:
            QMessageBox.warning(self, "Não foi possível tirar a foto", "Verifique se a câmera Basler está conectada e disponível.")
            return
        self.stop_preview()
        self.capture_button.setEnabled(False)
        self.status.setText("Capturando e salvando imagem...")
        self._capture_thread = CaptureThread(self.camera)
        self._capture_thread.captured.connect(self._save_capture)
        self._capture_thread.failed.connect(self._capture_failed)
        self._capture_thread.finished.connect(self._capture_finished)
        self._capture_thread.start()

    def _save_capture(self, frame) -> None:
        try:
            category = self.selected_category
            if category is None:
                raise RuntimeError("Selecione uma categoria antes de capturar.")
            serial = self.camera.last_info.serial if self.camera.last_info else "desconhecida"
            path = save_dataset_capture(frame, category, serial, self.operator_input.text())
            self.saved_paths.append(path)
            self._last_frame = frame.copy()
            self._preview_frozen = True
            self._render_frame()
            self._resume_preview_timer.start()
            self.status.setText(f"Foto salva em {category.name}: {path}")
        except Exception as exc:
            log.exception("Falha ao salvar captura do dataset")
            QMessageBox.critical(self, "Erro ao salvar captura", str(exc))

    def _capture_failed(self, message: str) -> None:
        self.status.setText(f"Falha na captura: {message}")
        QMessageBox.warning(self, "Falha na captura", message)

    def _capture_finished(self) -> None:
        self.capture_button.setEnabled(True)
        if self.isVisible():
            self.start_preview()

    def _resume_preview(self) -> None:
        self._preview_frozen = False

    def export_session(self) -> None:
        if not self.saved_paths:
            QMessageBox.information(self, "Sem capturas", "Ainda não há fotos capturadas nesta sessão.")
            return
        queue = signal_dataset_export(self.dataset_dir, self.saved_paths)
        self.status.setText(f"Exportação sinalizada: {queue}")

    def close_tab(self) -> None:
        self._resume_preview_timer.stop()
        self.stop_preview()
        if self._capture_thread and self._capture_thread.isRunning():
            self._capture_thread.wait(6500)
