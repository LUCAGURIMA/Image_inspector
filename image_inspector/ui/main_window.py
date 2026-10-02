from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from image_inspector.config import (
    CLASSIFICATION_MODELS_DIR,
    DEFAULT_CONFIDENCE,
    DETECTION_MODELS_DIR,
    INSPECTION_MODELS_DIR,
    PROFILES_DIR,
    WINDOW_TITLE,
    category_reference_dir,
    ensure_category_assets,
    ensure_project_dirs,
)
from image_inspector.core.basler_camera import BaslerCamera
from image_inspector.core.inspection import InspectionResult, InspectionService
from image_inspector.core.runtime import RuntimeSettings, SettingsStore
from image_inspector.core.storage import InspectionStorage
from image_inspector.core.yolo_models import list_models, list_profiles
from image_inspector.ui.threads import CaptureThread, InspectionThread
from image_inspector.ui.dataset_tab import DatasetTab

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_project_dirs()
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.camera = BaslerCamera()
        self.inspection_service = InspectionService()
        self.storage = InspectionStorage()
        self.current_image: np.ndarray | None = None
        self.current_result: InspectionResult | None = None
        self.capture_thread: CaptureThread | None = None
        self.inspection_thread: InspectionThread | None = None
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1360, 820)
        self._build_ui()
        self._apply_theme()
        self.refresh_lists()
        self._restore_settings()
        self._connect_settings_signals()
        self._update_mode_fields()
        self.refresh_cameras()
        self.connect_camera()
        log.info("Aplicacao iniciada")

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        self.status_label = QLabel("Inicializando...")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._inspection_tab(), "Operacao")
        self.tabs.addTab(self._settings_tab(), "Configuracao")
        self.dataset_tab = DatasetTab(self.camera, reconnect_camera=self.connect_camera)
        self.dataset_tab_index = self.tabs.addTab(self.dataset_tab, "Criar dataset")
        self.tabs.currentChanged.connect(self._on_main_tab_changed)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)

    def _on_main_tab_changed(self, index: int) -> None:
        if index == self.dataset_tab_index:
            self.dataset_tab.start_preview()
        else:
            self.dataset_tab.stop_preview()

    def _inspection_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        self.image_label = QLabel("Sem imagem")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(0, 0)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setObjectName("imagePanel")

        side_panel = QWidget()
        self.side_panel = side_panel
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        zoom_row.addStretch(1)
        zoom_out = QPushButton("A−")
        zoom_out.setToolTip("Diminuir textos e controles")
        zoom_out.setMinimumSize(54, 50)
        zoom_out.clicked.connect(lambda: self._change_panel_zoom(-0.1))
        zoom_row.addWidget(zoom_out)
        self.zoom_value_label = QLabel("100%")
        self.zoom_value_label.setAlignment(Qt.AlignCenter)
        self.zoom_value_label.setMinimumWidth(54)
        zoom_row.addWidget(self.zoom_value_label)
        zoom_in = QPushButton("A+")
        zoom_in.setToolTip("Aumentar textos e controles")
        zoom_in.setMinimumSize(54, 50)
        zoom_in.clicked.connect(lambda: self._change_panel_zoom(0.1))
        zoom_row.addWidget(zoom_in)
        zoom_reset = QPushButton("100%")
        zoom_reset.setToolTip("Restaurar zoom padrao")
        zoom_reset.setMinimumHeight(50)
        zoom_reset.clicked.connect(self._reset_panel_zoom)
        zoom_row.addWidget(zoom_reset)
        side_layout.addLayout(zoom_row)
        operation = QGroupBox("Operacao")
        op_layout = QVBoxLayout(operation)
        self.operator_input = QLineEdit()
        self.operator_input.setPlaceholderText("Operador / turno")
        op_layout.addWidget(QLabel("Operador"))
        op_layout.addWidget(self.operator_input)

        self.selection_summary_label = QLabel()
        self.selection_summary_label.setWordWrap(True)
        op_layout.addWidget(QLabel("Inspecao configurada"))
        op_layout.addWidget(self.selection_summary_label)

        self.inspect_btn = QPushButton("Capturar e analisar")
        self.inspect_btn.setMinimumHeight(68)
        self.inspect_btn.clicked.connect(self.capture_and_inspect)
        self.run_btn = QPushButton("Reanalisar imagem atual")
        self.run_btn.setMinimumHeight(56)
        self.run_btn.clicked.connect(self.run_inspection)
        self.run_btn.setEnabled(False)
        op_layout.addWidget(self.inspect_btn)
        op_layout.addWidget(self.run_btn)
        side_layout.addWidget(operation)

        result_box = QGroupBox("Resultado")
        result_layout = QVBoxLayout(result_box)
        self.result_label = QLabel("Aguardando inspecao")
        self.result_label.setObjectName("resultLabel")
        self.result_label.setWordWrap(True)
        self.result_details_label = QLabel("ID: - | Tempo: -")
        self.result_details_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)
        self.result_category_combo = QComboBox()
        self.result_category_combo.setMinimumHeight(50)
        self.result_category_combo.hide()
        self.result_category_combo.currentIndexChanged.connect(self._show_category_result)
        result_layout.addWidget(self.result_category_combo)
        result_layout.addWidget(self.result_details_label)
        side_layout.addWidget(result_box)

        review_box = QGroupBox("Confirmar resultado")
        review_layout = QVBoxLayout(review_box)
        review_layout.addWidget(QLabel("Compare a imagem com o resultado e informe se o produto realmente tem defeito."))
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Observacao opcional")
        self.note_input.setMinimumHeight(54)
        review_layout.addWidget(self.note_input)
        self.category_prompt = QLabel("Categorias detectadas nesta imagem:")
        review_layout.addWidget(self.category_prompt)
        self.review_categories_widget = QWidget()
        self.review_categories_layout = QVBoxLayout(self.review_categories_widget)
        self.review_categories_layout.setContentsMargins(0, 0, 0, 0)
        review_layout.addWidget(self.review_categories_widget)
        self.review_category_checks: list[QCheckBox] = []
        self.other_category_input = QLineEdit()
        self.other_category_input.setPlaceholderText("Categoria faltante ou outra categoria")
        self.other_category_input.setMinimumHeight(54)
        review_layout.addWidget(self.other_category_input)
        buttons = QGridLayout()
        review_buttons = [("actual_bad", "Defeito presente"), ("actual_good", "Produto conforme")]
        self.review_buttons: list[QPushButton] = []
        for row, (code, text) in enumerate(review_buttons):
            btn = QPushButton(text)
            btn.setObjectName("reviewBad" if code == "actual_bad" else "reviewGood")
            btn.setMinimumHeight(62)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _checked=False, c=code: self.save_review(c))
            buttons.addWidget(btn, row, 0)
            self.review_buttons.append(btn)
        review_layout.addLayout(buttons)
        side_layout.addWidget(review_box)
        self._set_review_enabled(False)

        checklist_box = QGroupBox("Status do sistema")
        checklist_layout = QVBoxLayout(checklist_box)
        self.camera_check_label = QLabel("Camera: verificando")
        self.profile_check_label = QLabel("Perfil ativo: nenhum")
        self.model_check_label = QLabel("Modelos: verifique selecao")
        for label in (self.camera_check_label, self.profile_check_label, self.model_check_label):
            checklist_layout.addWidget(label)
        side_layout.addWidget(checklist_box)
        side_layout.addStretch(1)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        side_scroll.setMinimumSize(0, 0)
        side_scroll.setMaximumWidth(16777215)
        side_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        side_scroll.setWidget(side_panel)
        self.inspection_splitter = QSplitter(Qt.Horizontal)
        self.inspection_splitter.setChildrenCollapsible(False)
        self.inspection_splitter.addWidget(self.image_label)
        self.inspection_splitter.addWidget(side_scroll)
        self.inspection_splitter.setStretchFactor(0, 3)
        self.inspection_splitter.setStretchFactor(1, 2)
        layout.addWidget(self.inspection_splitter, 1)
        return page

    def _settings_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        layout = QVBoxLayout(content)
        camera_box = QGroupBox("Camera Basler")
        camera_layout = QVBoxLayout(camera_box)
        self.camera_info_label = QLabel("Camera nao conectada")
        camera_layout.addWidget(self.camera_info_label)
        self.camera_combo = QComboBox()
        camera_layout.addWidget(QLabel("Camera"))
        camera_layout.addWidget(self.camera_combo)
        camera_refresh = QPushButton("Atualizar cameras")
        camera_refresh.clicked.connect(self.refresh_cameras)
        camera_layout.addWidget(camera_refresh)
        reconnect_btn = QPushButton("Reconectar camera")
        reconnect_btn.clicked.connect(self.connect_camera)
        camera_layout.addWidget(reconnect_btn)
        layout.addWidget(camera_box)

        profile_box = QGroupBox("Perfil PFS")
        profile_layout = QHBoxLayout(profile_box)
        self.profile_combo = QComboBox()
        profile_layout.addWidget(self.profile_combo, 1)
        apply_btn = QPushButton("Aplicar perfil")
        apply_btn.clicked.connect(self.apply_profile)
        profile_layout.addWidget(apply_btn)
        refresh_btn = QPushButton("Atualizar listas")
        refresh_btn.clicked.connect(self.refresh_lists)
        profile_layout.addWidget(refresh_btn)
        layout.addWidget(profile_box)

        inspection_box = QGroupBox("Configuracao da inspecao")
        inspection_layout = QVBoxLayout(inspection_box)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Categorias de inspecao", "simple")
        self.mode_combo.addItem("Deteccao e classificacao", "hybrid")
        inspection_layout.addWidget(QLabel("Tipo de inspecao"))
        inspection_layout.addWidget(self.mode_combo)

        self.simple_model_label = QLabel("Categorias de inspecao")
        self.simple_model_button = QPushButton("Escolher categorias")
        self.simple_model_button.clicked.connect(self._show_model_picker)
        self.import_model_btn = QPushButton("Importar modelo .pt")
        self.import_model_btn.clicked.connect(self.import_inspection_model)
        self.detection_model_label = QLabel("Modelo de deteccao")
        self.detection_model_combo = QComboBox()
        self.classification_model_label = QLabel("Modelo de classificacao")
        self.classification_model_combo = QComboBox()
        for widget in (
            self.simple_model_label,
            self.simple_model_button,
            self.import_model_btn,
            self.detection_model_label,
            self.detection_model_combo,
            self.classification_model_label,
            self.classification_model_combo,
        ):
            inspection_layout.addWidget(widget)
        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.05, 0.95)
        self.confidence_spin.setSingleStep(0.05)
        self.confidence_spin.setValue(DEFAULT_CONFIDENCE)
        inspection_layout.addWidget(QLabel("Confianca minima (ajustar com suporte tecnico)"))
        inspection_layout.addWidget(self.confidence_spin)
        layout.addWidget(inspection_box)
        layout.addStretch(1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    def refresh_lists(self) -> None:
        self._refresh_model_button()
        self._load_combo(self.detection_model_combo, list_models(DETECTION_MODELS_DIR))
        self._load_combo(self.classification_model_combo, list_models(CLASSIFICATION_MODELS_DIR))
        self._load_combo(self.profile_combo, list_profiles(PROFILES_DIR))
        self._restore_combo_values()
        self._update_system_status()

    def refresh_cameras(self) -> None:
        current = self.camera_combo.currentData() or self.settings.camera_serial
        try:
            devices = self.camera.enumerate_devices()
        except Exception as exc:
            self.camera_combo.clear()
            self.camera_info_label.setText(str(exc))
            return
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        for model, serial in devices:
            self.camera_combo.addItem(f"{model} — {serial}", serial)
        index = self.camera_combo.findData(current) if current else -1
        if index < 0 and len(devices) == 1:
            index = 0
        if index >= 0:
            self.camera_combo.setCurrentIndex(index)
        self.camera_combo.blockSignals(False)

    def connect_camera(self) -> None:
        try:
            self.camera.disconnect()
            info = self.camera.connect(self.camera_combo.currentData())
            self.camera_info_label.setText(f"Conectada: {info.model} | Serie {info.serial} | {info.width}x{info.height}")
            self.status_label.setText("Camera Basler conectada")
            profile = self.profile_combo.currentData()
            if profile and (self.camera.active_profile is None or self.camera.active_profile != Path(profile).resolve()):
                try:
                    self.camera.apply_profile(Path(profile))
                except Exception as exc:
                    self.status_label.setText("Camera conectada; falha ao aplicar perfil")
                    QMessageBox.warning(self, "Perfil da camera", f"A camera conectou, mas o perfil nao foi aplicado.\n{exc}")
            self._persist_settings()
        except Exception as exc:
            self.status_label.setText("Camera indisponivel")
            self.camera_info_label.setText(str(exc))
            log.exception("Falha ao conectar camera")
        self._update_system_status()

    def apply_profile(self) -> None:
        profile = self.profile_combo.currentData()
        if not profile:
            QMessageBox.warning(self, "Perfil", "Nenhum perfil .pfs encontrado em profiles/.")
            return
        try:
            self.camera.apply_profile(Path(profile))
            self.status_label.setText(f"Perfil aplicado: {Path(profile).name}")
            self._persist_settings()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao aplicar perfil", str(exc))
            log.exception("Falha ao aplicar perfil")
        self._update_system_status()

    def _on_camera_selection_changed(self) -> None:
        self._persist_settings()
        self.connect_camera()

    def capture_image(self) -> None:
        self._set_busy(True, "Capturando imagem...")
        self.capture_thread = CaptureThread(self.camera)
        self.capture_thread.captured.connect(self._on_captured)
        self.capture_thread.failed.connect(self._on_failed)
        self.capture_thread.finished.connect(lambda: self._set_busy(False))
        self.capture_thread.start()

    def capture_and_inspect(self) -> None:
        if not self._inspection_configured():
            QMessageBox.warning(self, "Configuracao incompleta", "Fale com o responsavel para configurar as categorias de inspecao.")
            return
        if not self.camera.is_open:
            QMessageBox.warning(self, "Camera", "A camera nao esta conectada. Verifique a camera na aba Configuracao.")
            return
        self._set_busy(True, "Capturando imagem para inspecao...")
        self.capture_thread = CaptureThread(self.camera)
        self.capture_thread.captured.connect(self._on_captured_then_inspect)
        self.capture_thread.failed.connect(self._on_failed)
        self.capture_thread.start()

    def run_inspection(self) -> None:
        if not self._inspection_configured():
            QMessageBox.warning(self, "Configuracao incompleta", "Fale com o responsavel para configurar a inspecao.")
            return
        if self.current_image is None:
            QMessageBox.warning(self, "Inspecao", "Capture uma imagem antes de inspecionar.")
            return
        self.current_result = None
        self._set_review_enabled(False)
        self._persist_settings()
        self._set_busy(True, "Executando inspecao...")
        self.inspection_thread = InspectionThread(
            service=self.inspection_service,
            image=self.current_image,
            mode=self.mode_combo.currentData(),
            simple_models=self._selected_simple_models(),
            detection_model=self._combo_path(self.detection_model_combo),
            classification_model=self._combo_path(self.classification_model_combo),
            confidence=float(self.confidence_spin.value()),
        )
        self.inspection_thread.completed.connect(self._on_inspected)
        self.inspection_thread.failed.connect(self._on_failed)
        self.inspection_thread.progress.connect(lambda text: self._set_busy(True, text))
        self.inspection_thread.finished.connect(lambda: self._set_busy(False))
        self.inspection_thread.start()

    def save_review(self, actual_label: str) -> None:
        if self.current_result is None:
            QMessageBox.warning(self, "Salvar revisao", "Execute uma inspecao antes de salvar.")
            return
        try:
            predicted_bad = self.current_result.status == "reprovado"
            actual_bad = actual_label == "actual_bad"
            code = "tp" if actual_bad and predicted_bad else "fn" if actual_bad else "fp" if predicted_bad else "tn"
            categories = [str(check.property("categoryName") or check.text()) for check in self.review_category_checks if check.isChecked()]
            other_category = self.other_category_input.text().strip()
            if other_category and other_category not in categories:
                categories.append(other_category)
            path = self.storage.save_review(
                self.current_result,
                code,
                self.note_input.text().strip(),
                context={**self._inspection_context(), "actual_has_findings": actual_bad, "review_categories": categories},
            )
            review_names = {"tp": "Verdadeiro positivo", "tn": "Verdadeiro negativo", "fp": "Falso positivo", "fn": "Falso negativo"}
            self.status_label.setText("Revisao salva")
            self.result_label.setText(f"Revisao salva: {review_names[code]}\n{path}")
            self.result_label.setStyleSheet("background: #dcfae6; color: #05603a;")
            self.note_input.clear()
            self.other_category_input.clear()
            self.current_result = None
            self.run_btn.setEnabled(False)
            self._set_review_enabled(False)
            self._set_busy(False)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))
            log.exception("Falha ao salvar revisao")

    def _on_captured(self, image: object) -> None:
        self.current_image = image
        self.current_result = None
        self.result_label.setText("Imagem capturada. Pronta para inspecao.")
        self.result_label.setStyleSheet("background: white; color: #18212f;")
        self.result_details_label.setText("ID: - | Tempo: -")
        self._display_image(image)
        self.run_btn.setEnabled(True)
        self._set_review_enabled(False)
        self.result_category_combo.hide()

    def _on_captured_then_inspect(self, image: object) -> None:
        self._on_captured(image)
        self.run_inspection()

    def _on_inspected(self, result: object) -> None:
        self.current_result = result
        self.result_label.setText(result.summary)
        self.result_label.setStyleSheet(
            "background: #fee4e2; color: #912018;" if result.status == "reprovado"
            else "background: #dcfae6; color: #05603a;"
        )
        self.result_details_label.setText(f"ID: {result.inspection_id} | Inferencia: {result.inference_ms:.0f} ms")
        self.result_category_combo.blockSignals(True)
        self.result_category_combo.clear()
        for category in result.category_images:
            self.result_category_combo.addItem(category, category)
        self.result_category_combo.blockSignals(False)
        if len(result.category_images) > 1:
            self.result_category_combo.show()
            self._show_category_result(0)
        else:
            self.result_category_combo.hide()
            self._display_image(result.annotated_image)
        self._populate_review_categories(result)
        self._set_review_enabled(True)
        self.run_btn.setEnabled(True)
        self.status_label.setText("Inspecao concluida")
        log.info("Inspecao concluida | id=%s | status=%s | ms=%.1f", result.inspection_id, result.status, result.inference_ms)

    def _show_category_result(self, index: int) -> None:
        if self.current_result is None or index < 0:
            return
        category = self.result_category_combo.itemData(index)
        image = self.current_result.category_images.get(category)
        if image is not None:
            self._display_image(image)

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.status_label.setText("Erro")
        QMessageBox.critical(self, "Erro", message)

    def _populate_review_categories(self, result: InspectionResult) -> None:
        while self.review_categories_layout.count():
            item = self.review_categories_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.review_category_checks = []
        choices: dict[str, tuple[bool, str]] = {}
        if result.mode == "simple_multi":
            models = result.payload.get("models", {}).get("inspection", [])
            predictions = result.payload.get("predictions", [])
            for model, prediction in zip(models, predictions):
                category = Path(model.get("name", "")).stem
                if category:
                    choices[category] = (
                        bool(prediction.get("has_findings")),
                        str(prediction.get("label", "sem deteccao")),
                    )
        elif result.mode == "hybrid":
            for detection in result.payload.get("detections", []):
                category = str(detection.get("class_name", "")).strip()
                if category:
                    choices[category] = (True, "detectada")
        if not choices:
            self.category_prompt.setText("Nenhuma categoria detectada. Se houve falha, informe a categoria abaixo.")
            return
        self.category_prompt.setText("Categorias do dataset: confira a analise. Para falso negativo, marque a categoria que faltou.")
        for category, (found, detail) in sorted(choices.items(), key=lambda item: item[0].lower()):
            check = QCheckBox(category)
            check.setProperty("categoryName", category)
            check.setToolTip(f"Resultado da analise: {detail}")
            check.setChecked(found)
            check.setMinimumHeight(48)
            self.review_categories_layout.addWidget(check)
            self.review_category_checks.append(check)
        self._apply_panel_zoom()

    def _set_review_enabled(self, enabled: bool) -> None:
        for button in self.review_buttons:
            button.setEnabled(enabled)
        for check in self.review_category_checks:
            check.setEnabled(enabled)
        self.other_category_input.setEnabled(enabled)

    def _display_image(self, image: np.ndarray) -> None:
        self._display_image_source = image
        self._render_image()

    def _render_image(self) -> None:
        image = getattr(self, "_display_image_source", None)
        if image is None:
            return
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimage = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage).scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pixmap)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "inspection_splitter"):
            orientation = Qt.Horizontal if self.width() >= 950 else Qt.Vertical
            if self.inspection_splitter.orientation() != orientation:
                self.inspection_splitter.setOrientation(orientation)
                if orientation == Qt.Horizontal:
                    self.inspection_splitter.setSizes([self.width() * 3 // 5, self.width() * 2 // 5])
                else:
                    self.inspection_splitter.setSizes([self.height() // 2, self.height() // 2])
        self._render_image()

    def _inspection_context(self) -> dict[str, object]:
        context = self.camera.context()
        context.update(
            {
                "operator": self.operator_input.text().strip(),
                "camera_serial_selected": self.camera_combo.currentData() or "",
                "selected_mode": self.mode_combo.currentData(),
                "selected_models": {
                    "inspection": [p.name for p in self._selected_simple_models()],
                    "detection": self.detection_model_combo.currentText(),
                    "classification": self.classification_model_combo.currentText(),
                },
                "confidence": float(self.confidence_spin.value()),
            }
        )
        return context

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        for widget in (self.inspect_btn, self.run_btn):
            widget.setEnabled(not busy)
        self._set_review_enabled(not busy and self.current_result is not None)
        if hasattr(self, "tabs") and self.tabs.count() > 1:
            self.tabs.setTabEnabled(1, not busy and self.current_result is None)
        if message:
            self.status_label.setText(message)

    def _update_mode_fields(self) -> None:
        simple = self.mode_combo.currentData() == "simple"
        self.simple_model_label.setVisible(simple)
        self.simple_model_button.setVisible(simple)
        self.import_model_btn.setVisible(simple)
        self.detection_model_label.setVisible(not simple)
        self.detection_model_combo.setVisible(not simple)
        self.classification_model_label.setVisible(not simple)
        self.classification_model_combo.setVisible(not simple)
        self.selection_summary_label.setText(self._selected_models_summary())
        self._persist_settings()
        self._update_system_status()

    def _update_system_status(self) -> None:
        self.camera_check_label.setText("Camera: OK" if self.camera.is_open else "Camera: indisponivel")
        profile = self.camera.active_profile.name if self.camera.active_profile else "nenhum aplicado"
        self.profile_check_label.setText(f"Perfil ativo: {profile}")
        mode = self.mode_combo.currentData()
        if mode == "simple":
            models_ok = bool(self._selected_simple_models())
        else:
            models_ok = bool(self.detection_model_combo.currentData() and self.classification_model_combo.currentData())
        self.model_check_label.setText("Modelos: OK" if models_ok else "Modelos: selecao incompleta")
        if hasattr(self, "selection_summary_label"):
            self.selection_summary_label.setText(self._selected_models_summary())

    def _persist_settings(self) -> None:
        settings = RuntimeSettings(
            operator_name=self.operator_input.text().strip(),
            mode=self.mode_combo.currentData() or "simple",
            simple_model=(self.selected_model_names[0] if getattr(self, "selected_model_names", []) else ""),
            simple_models=[p.name for p in self._selected_simple_models()],
            detection_model=self.detection_model_combo.currentText(),
            classification_model=self.classification_model_combo.currentText(),
            confidence=float(self.confidence_spin.value()),
            profile=self.profile_combo.currentText(),
            camera_serial=self.camera_combo.currentData() or self.settings.camera_serial,
            ui_zoom=getattr(self, "panel_zoom", 1.0),
        )
        self.settings_store.save(settings)
        self.settings = settings

    def _restore_settings(self) -> None:
        self.operator_input.setText(self.settings.operator_name or "")
        self.selected_model_names = list(self.settings.simple_models or ([self.settings.simple_model] if self.settings.simple_model else []))
        self._refresh_model_button()
        self.confidence_spin.setValue(float(self.settings.confidence or DEFAULT_CONFIDENCE))
        self.panel_zoom = min(1.3, max(0.8, float(self.settings.ui_zoom or 1.0)))
        self._apply_panel_zoom()
        index = self.mode_combo.findData(self.settings.mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self._restore_combo_values()

    def _restore_combo_values(self) -> None:
        for combo, value in (
            (self.detection_model_combo, self.settings.detection_model),
            (self.classification_model_combo, self.settings.classification_model),
            (self.profile_combo, self.settings.profile),
        ):
            if value:
                index = combo.findText(value)
                if index >= 0:
                    combo.setCurrentIndex(index)

    def _connect_settings_signals(self) -> None:
        self.mode_combo.currentIndexChanged.connect(self._update_mode_fields)
        self.detection_model_combo.currentIndexChanged.connect(lambda: (self._persist_settings(), self._update_system_status()))
        self.classification_model_combo.currentIndexChanged.connect(lambda: (self._persist_settings(), self._update_system_status()))
        self.profile_combo.currentIndexChanged.connect(lambda: (self._persist_settings(), self._update_system_status()))
        self.camera_combo.currentIndexChanged.connect(self._on_camera_selection_changed)
        self.confidence_spin.valueChanged.connect(lambda: self._persist_settings())
        self.operator_input.editingFinished.connect(self._persist_settings)

    def _change_panel_zoom(self, delta: float) -> None:
        self.panel_zoom = min(1.3, max(0.8, self.panel_zoom + delta))
        self._apply_panel_zoom()
        self._persist_settings()

    def _reset_panel_zoom(self) -> None:
        self.panel_zoom = 1.0
        self._apply_panel_zoom()
        self._persist_settings()

    def _apply_panel_zoom(self) -> None:
        scale = self.panel_zoom
        font_size = round(17 * scale)
        control_height = round(50 * scale)
        self.zoom_value_label.setText(f"{round(scale * 100)}%")
        self.side_panel.setStyleSheet(
            f"QWidget {{ font-size: {font_size}px; }} "
            f"QPushButton {{ font-size: {font_size}px; min-height: {round(24 * scale)}px; }} "
            f"QComboBox, QLineEdit, QDoubleSpinBox {{ font-size: {font_size}px; min-height: {control_height}px; }} "
            f"QCheckBox {{ font-size: {font_size}px; min-height: {control_height}px; }} "
            f"#resultLabel {{ font-size: {round(22 * scale)}px; }}"
        )
        for widget in self.side_panel.findChildren(QWidget):
            base_height = widget.property("panelZoomBaseHeight")
            if base_height is None:
                base_height = widget.minimumHeight()
                widget.setProperty("panelZoomBaseHeight", base_height)
            if base_height:
                widget.setMinimumHeight(max(24, round(int(base_height) * scale)))

    def _combo_path(self, combo: QComboBox) -> Path | None:
        data = combo.currentData()
        return Path(data) if data else None

    def _selected_simple_models(self) -> list[Path]:
        available = {path.name: path for path in list_models(INSPECTION_MODELS_DIR)}
        return [available[name] for name in self.selected_model_names if name in available]

    def _selected_models_summary(self) -> str:
        if self.mode_combo.currentData() == "simple":
            names = [path.stem for path in self._selected_simple_models()]
            return ", ".join(names) if names else "Nenhuma categoria selecionada. Procure o responsavel pela configuracao."
        detection = self.detection_model_combo.currentText() or "sem modelo de deteccao"
        classification = self.classification_model_combo.currentText() or "sem modelo de classificacao"
        return f"Deteccao: {detection}\nClassificacao: {classification}"

    def _inspection_configured(self) -> bool:
        if self.mode_combo.currentData() == "simple":
            return bool(self._selected_simple_models())
        return bool(self._combo_path(self.detection_model_combo) and self._combo_path(self.classification_model_combo))

    def _refresh_model_button(self) -> None:
        available = {path.name for path in list_models(INSPECTION_MODELS_DIR)}
        self.selected_model_names = [name for name in getattr(self, "selected_model_names", []) if name in available]
        self.simple_model_button.setText(
            f"Selecionar categorias ({len(self.selected_model_names)})"
            if self.selected_model_names else "Selecionar categorias"
        )

    def _show_model_picker(self) -> None:
        dialog = QDialog(self, Qt.Popup)
        dialog.setWindowTitle("Categorias de inspecao")
        dialog.setMinimumWidth(440)
        outer = QVBoxLayout(dialog)
        outer.addWidget(QLabel("Selecione uma ou mais categorias para analisar a mesma imagem:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(250)
        scroll.setMaximumHeight(480)
        cards = QWidget()
        cards_layout = QVBoxLayout(cards)
        cards_layout.setContentsMargins(4, 4, 4, 4)
        self._picker_previews = {}
        for path in list_models(INSPECTION_MODELS_DIR):
            ensure_category_assets(path)
            selected = path.name in self.selected_model_names
            card = QFrame()
            card.setStyleSheet(
                "QFrame { border: 2px solid %s; border-radius: 8px; background: white; }"
                % ("#1f6feb" if selected else "#d0d5dd")
            )
            row = QHBoxLayout(card)
            preview = QLabel()
            pixmap = QPixmap(str(ensure_category_assets(path)))
            preview.setPixmap(pixmap.scaled(120, 82, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            preview.setFixedSize(124, 86)
            self._picker_previews[path.name] = preview
            row.addWidget(preview)
            details = QVBoxLayout()
            details.addWidget(QLabel(f"<b>{path.stem}</b>"))
            details.addWidget(QLabel(path.name))
            details.addStretch(1)
            row.addLayout(details, 1)
            check = QCheckBox("Selecionada")
            check.setChecked(selected)
            row.addWidget(check)
            check.toggled.connect(lambda checked, p=path, c=card: self._toggle_model_card(p, checked, c))
            card.mousePressEvent = lambda event, cb=check: cb.setChecked(not cb.isChecked())
            cards_layout.addWidget(card)
            reference_btn = QPushButton("Adicionar/trocar imagem de referencia")
            reference_btn.clicked.connect(lambda _checked=False, p=path, d=dialog: self._choose_reference(p, d))
            cards_layout.addWidget(reference_btn)
        if not list_models(INSPECTION_MODELS_DIR):
            cards_layout.addWidget(QLabel("Nenhum arquivo .pt importado."))
        scroll.setWidget(cards)
        outer.addWidget(scroll)
        close_btn = QPushButton("Concluir")
        close_btn.clicked.connect(dialog.accept)
        outer.addWidget(close_btn)
        dialog.resize(500, min(560, 140 + len(list_models(INSPECTION_MODELS_DIR)) * 150))
        dialog.exec_()
        self._refresh_model_button()
        self._persist_settings()
        self._update_system_status()

    def _toggle_model_card(self, path: Path, selected: bool, card: QFrame) -> None:
        if selected and path.name not in self.selected_model_names:
            self.selected_model_names.append(path.name)
        elif not selected:
            self.selected_model_names = [name for name in self.selected_model_names if name != path.name]
        card.setStyleSheet(
            "QFrame { border: 2px solid %s; border-radius: 8px; background: white; }"
            % ("#1f6feb" if selected else "#d0d5dd")
        )

    def _choose_reference(self, model_path: Path, dialog: QDialog) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            dialog, "Imagem de referencia", "", "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not filename:
            return
        image = cv2.imread(filename)
        if image is None:
            QMessageBox.warning(dialog, "Imagem invalida", "Nao foi possivel abrir essa imagem.")
            return
        ensure_category_assets(model_path)
        destination = category_reference_dir(model_path) / "reference.png"
        if not cv2.imwrite(str(destination), image):
            QMessageBox.critical(dialog, "Erro", "Nao foi possivel salvar a imagem de referencia.")
            return
        preview = getattr(self, "_picker_previews", {}).get(model_path.name)
        if preview:
            pixmap = QPixmap(str(destination))
            preview.setPixmap(pixmap.scaled(120, 82, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def import_inspection_model(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Importar modelo YOLO", "", "Modelos YOLO (*.pt)")
        if not filename:
            return
        source = Path(filename)
        destination = INSPECTION_MODELS_DIR / source.name
        if destination.exists():
            answer = QMessageBox.question(self, "Modelo existente", f"{source.name} ja existe. Substituir?")
            if answer != QMessageBox.Yes:
                return
        try:
            import shutil
            shutil.copy2(source, destination)
            ensure_category_assets(destination)
            if destination.name not in self.selected_model_names:
                self.selected_model_names.append(destination.name)
            self.refresh_lists()
            self._persist_settings()
            self.status_label.setText(f"Modelo importado: {destination.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao importar modelo", str(exc))

    @staticmethod
    def _load_combo(combo: QComboBox, paths: list[Path]) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        for path in paths:
            combo.addItem(path.name, str(path))
        if current:
            index = combo.findText(current)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def closeEvent(self, event) -> None:
        self._persist_settings()
        self.dataset_tab.close_tab()
        self.camera.disconnect()
        log.info("Aplicacao encerrada")
        event.accept()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #f4f6f8; color: #18212f; font-size: 17px; }
            QScrollArea { border: 0; background: #f4f6f8; }
            QGroupBox { border: 1px solid #c8d0da; border-radius: 6px; margin-top: 12px; padding: 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton { background: #1f6feb; color: white; border: 0; border-radius: 6px; padding: 10px 12px; font-weight: 600; min-height: 24px; }
            QPushButton:disabled { background: #98a2b3; }
            QComboBox, QLineEdit, QDoubleSpinBox { background: white; border: 1px solid #b8c2cc; border-radius: 5px; padding: 8px; }
            QPushButton { font-size: 17px; }
            QComboBox, QLineEdit, QDoubleSpinBox { min-height: 50px; font-size: 17px; }
            QCheckBox { min-height: 50px; spacing: 12px; font-size: 17px; }
            QTabBar::tab { min-height: 56px; min-width: 140px; padding: 10px 18px; font-size: 18px; }
            QPushButton#reviewBad { background: #b42318; min-height: 62px; font-size: 19px; }
            QPushButton#reviewGood { background: #067647; min-height: 62px; font-size: 19px; }
            QPushButton#reviewBad:disabled, QPushButton#reviewGood:disabled { background: #98a2b3; }
            #imagePanel { background: #101828; color: #f8fafc; border-radius: 6px; }
            #statusLabel { background: #172033; color: white; padding: 10px; border-radius: 4px; font-weight: 600; }
            #resultLabel { font-size: 22px; font-weight: 700; padding: 16px; background: white; border-radius: 6px; }
            """
        )
