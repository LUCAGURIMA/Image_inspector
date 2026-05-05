from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
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
    ensure_project_dirs,
)
from image_inspector.core.basler_camera import BaslerCamera
from image_inspector.core.inspection import InspectionResult, InspectionService
from image_inspector.core.runtime import RuntimeSettings, SettingsStore
from image_inspector.core.storage import InspectionStorage
from image_inspector.core.yolo_models import list_models
from image_inspector.ui.threads import CaptureThread, InspectionThread

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
        self.connect_camera()
        log.info("Aplicacao iniciada")

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        self.status_label = QLabel("Inicializando...")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        tabs = QTabWidget()
        tabs.addTab(self._inspection_tab(), "Inspecao")
        tabs.addTab(self._settings_tab(), "Camera e perfis")
        layout.addWidget(tabs, 1)
        self.setCentralWidget(root)

    def _inspection_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        self.image_label = QLabel("Sem imagem")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(520, 360)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setObjectName("imagePanel")
        layout.addWidget(self.image_label, 1)

        side_panel = QWidget()
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)
        operation = QGroupBox("Operacao")
        op_layout = QVBoxLayout(operation)
        self.operator_input = QLineEdit()
        self.operator_input.setPlaceholderText("Operador / turno")
        op_layout.addWidget(QLabel("Operador"))
        op_layout.addWidget(self.operator_input)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Inspecao simples", "simple")
        self.mode_combo.addItem("Inspecao hibrida", "hybrid")
        op_layout.addWidget(QLabel("Modo"))
        op_layout.addWidget(self.mode_combo)

        self.simple_model_label = QLabel("Modelo de inspecao")
        self.simple_model_combo = QComboBox()
        self.detection_model_label = QLabel("Modelo de deteccao")
        self.detection_model_combo = QComboBox()
        self.classification_model_label = QLabel("Modelo de classificacao")
        self.classification_model_combo = QComboBox()
        for widget in (
            self.simple_model_label,
            self.simple_model_combo,
            self.detection_model_label,
            self.detection_model_combo,
            self.classification_model_label,
            self.classification_model_combo,
        ):
            op_layout.addWidget(widget)

        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.05, 0.95)
        self.confidence_spin.setSingleStep(0.05)
        self.confidence_spin.setValue(DEFAULT_CONFIDENCE)
        op_layout.addWidget(QLabel("Confianca minima"))
        op_layout.addWidget(self.confidence_spin)

        self.capture_btn = QPushButton("Capturar")
        self.capture_btn.setMinimumHeight(44)
        self.capture_btn.clicked.connect(self.capture_image)
        self.inspect_btn = QPushButton("Capturar e inspecionar")
        self.inspect_btn.setMinimumHeight(44)
        self.inspect_btn.clicked.connect(self.capture_and_inspect)
        self.run_btn = QPushButton("Inspecionar imagem atual")
        self.run_btn.setMinimumHeight(44)
        self.run_btn.clicked.connect(self.run_inspection)
        op_layout.addWidget(self.capture_btn)
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
        result_layout.addWidget(self.result_details_label)
        side_layout.addWidget(result_box)

        review_box = QGroupBox("Confirmacao manual para dataset")
        review_layout = QVBoxLayout(review_box)
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Observacao opcional")
        review_layout.addWidget(self.note_input)
        buttons = QGridLayout()
        review_buttons = [
            ("tp", "Acertou: produto ruim"),
            ("tn", "Acertou: produto bom"),
            ("fp", "Corrigir: era bom"),
            ("fn", "Corrigir: era ruim"),
        ]
        for row, (code, text) in enumerate(review_buttons):
            btn = QPushButton(text)
            btn.setMinimumHeight(44)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _checked=False, c=code: self.save_review(c))
            buttons.addWidget(btn, row // 2, row % 2)
        review_layout.addLayout(buttons)
        side_layout.addWidget(review_box)

        checklist_box = QGroupBox("Status do sistema")
        checklist_layout = QVBoxLayout(checklist_box)
        self.camera_check_label = QLabel("Camera: verificando")
        self.profile_check_label = QLabel("Perfil: nenhum")
        self.model_check_label = QLabel("Modelos: verifique selecao")
        for label in (self.camera_check_label, self.profile_check_label, self.model_check_label):
            checklist_layout.addWidget(label)
        side_layout.addWidget(checklist_box)
        side_layout.addStretch(1)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setMinimumWidth(360)
        side_scroll.setMaximumWidth(520)
        side_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        side_scroll.setWidget(side_panel)
        layout.addWidget(side_scroll)
        return page

    def _settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        camera_box = QGroupBox("Camera Basler")
        camera_layout = QVBoxLayout(camera_box)
        self.camera_info_label = QLabel("Camera nao conectada")
        camera_layout.addWidget(self.camera_info_label)
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
        layout.addStretch(1)
        return page

    def refresh_lists(self) -> None:
        self._load_combo(self.simple_model_combo, list_models(INSPECTION_MODELS_DIR))
        self._load_combo(self.detection_model_combo, list_models(DETECTION_MODELS_DIR))
        self._load_combo(self.classification_model_combo, list_models(CLASSIFICATION_MODELS_DIR))
        self._load_combo(self.profile_combo, sorted(PROFILES_DIR.glob("*.pfs")))
        self._restore_combo_values()
        self._update_system_status()

    def connect_camera(self) -> None:
        try:
            self.camera.disconnect()
            info = self.camera.connect()
            self.camera_info_label.setText(f"Conectada: {info.model} | Serial {info.serial} | {info.width}x{info.height}")
            self.status_label.setText("Camera Basler conectada")
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

    def capture_image(self) -> None:
        self._set_busy(True, "Capturando imagem...")
        self.capture_thread = CaptureThread(self.camera)
        self.capture_thread.captured.connect(self._on_captured)
        self.capture_thread.failed.connect(self._on_failed)
        self.capture_thread.finished.connect(lambda: self._set_busy(False))
        self.capture_thread.start()

    def capture_and_inspect(self) -> None:
        self._set_busy(True, "Capturando imagem para inspecao...")
        self.capture_thread = CaptureThread(self.camera)
        self.capture_thread.captured.connect(self._on_captured_then_inspect)
        self.capture_thread.failed.connect(self._on_failed)
        self.capture_thread.finished.connect(lambda: self._set_busy(False))
        self.capture_thread.start()

    def run_inspection(self) -> None:
        if self.current_image is None:
            QMessageBox.warning(self, "Inspecao", "Capture uma imagem antes de inspecionar.")
            return
        self._persist_settings()
        self._set_busy(True, "Executando inspecao...")
        self.inspection_thread = InspectionThread(
            service=self.inspection_service,
            image=self.current_image,
            mode=self.mode_combo.currentData(),
            simple_model=self._combo_path(self.simple_model_combo),
            detection_model=self._combo_path(self.detection_model_combo),
            classification_model=self._combo_path(self.classification_model_combo),
            confidence=float(self.confidence_spin.value()),
        )
        self.inspection_thread.completed.connect(self._on_inspected)
        self.inspection_thread.failed.connect(self._on_failed)
        self.inspection_thread.finished.connect(lambda: self._set_busy(False))
        self.inspection_thread.start()

    def save_review(self, code: str) -> None:
        if self.current_result is None:
            QMessageBox.warning(self, "Salvar revisao", "Execute uma inspecao antes de salvar.")
            return
        try:
            path = self.storage.save_review(
                self.current_result,
                code,
                self.note_input.text().strip(),
                context=self._inspection_context(),
            )
            self.status_label.setText(f"Revisao salva em {path}")
            self.note_input.clear()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))
            log.exception("Falha ao salvar revisao")

    def _on_captured(self, image: object) -> None:
        self.current_image = image
        self.current_result = None
        self.result_label.setText("Imagem capturada. Pronta para inspecao.")
        self.result_details_label.setText("ID: - | Tempo: -")
        self._display_image(image)

    def _on_captured_then_inspect(self, image: object) -> None:
        self._on_captured(image)
        self.run_inspection()

    def _on_inspected(self, result: object) -> None:
        self.current_result = result
        self.result_label.setText(result.summary)
        self.result_details_label.setText(f"ID: {result.inspection_id} | Inferencia: {result.inference_ms:.0f} ms")
        self._display_image(result.annotated_image)
        self.status_label.setText("Inspecao concluida")
        log.info("Inspecao concluida | id=%s | status=%s | ms=%.1f", result.inspection_id, result.status, result.inference_ms)

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Erro")
        QMessageBox.critical(self, "Erro", message)

    def _display_image(self, image: np.ndarray) -> None:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimage = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage).scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pixmap)

    def _inspection_context(self) -> dict[str, object]:
        context = self.camera.context()
        context.update(
            {
                "operator": self.operator_input.text().strip(),
                "selected_mode": self.mode_combo.currentData(),
                "selected_models": {
                    "inspection": self.simple_model_combo.currentText(),
                    "detection": self.detection_model_combo.currentText(),
                    "classification": self.classification_model_combo.currentText(),
                },
                "confidence": float(self.confidence_spin.value()),
            }
        )
        return context

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        for widget in (self.capture_btn, self.inspect_btn, self.run_btn):
            widget.setEnabled(not busy)
        if message:
            self.status_label.setText(message)

    def _update_mode_fields(self) -> None:
        simple = self.mode_combo.currentData() == "simple"
        self.simple_model_label.setVisible(simple)
        self.simple_model_combo.setVisible(simple)
        self.detection_model_label.setVisible(not simple)
        self.detection_model_combo.setVisible(not simple)
        self.classification_model_label.setVisible(not simple)
        self.classification_model_combo.setVisible(not simple)
        self._persist_settings()
        self._update_system_status()

    def _update_system_status(self) -> None:
        self.camera_check_label.setText("Camera: OK" if self.camera.is_open else "Camera: indisponivel")
        profile = self.camera.active_profile.name if self.camera.active_profile else self.profile_combo.currentText()
        self.profile_check_label.setText(f"Perfil: {profile or 'nenhum aplicado'}")
        mode = self.mode_combo.currentData()
        if mode == "simple":
            models_ok = bool(self.simple_model_combo.currentData())
        else:
            models_ok = bool(self.detection_model_combo.currentData() and self.classification_model_combo.currentData())
        self.model_check_label.setText("Modelos: OK" if models_ok else "Modelos: selecao incompleta")

    def _persist_settings(self) -> None:
        settings = RuntimeSettings(
            operator_name=self.operator_input.text().strip(),
            mode=self.mode_combo.currentData() or "simple",
            simple_model=self.simple_model_combo.currentText(),
            detection_model=self.detection_model_combo.currentText(),
            classification_model=self.classification_model_combo.currentText(),
            confidence=float(self.confidence_spin.value()),
            profile=self.profile_combo.currentText(),
        )
        self.settings_store.save(settings)
        self.settings = settings

    def _restore_settings(self) -> None:
        self.operator_input.setText(self.settings.operator_name or "")
        self.confidence_spin.setValue(float(self.settings.confidence or DEFAULT_CONFIDENCE))
        index = self.mode_combo.findData(self.settings.mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self._restore_combo_values()

    def _restore_combo_values(self) -> None:
        for combo, value in (
            (self.simple_model_combo, self.settings.simple_model),
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
        self.simple_model_combo.currentIndexChanged.connect(lambda: (self._persist_settings(), self._update_system_status()))
        self.detection_model_combo.currentIndexChanged.connect(lambda: (self._persist_settings(), self._update_system_status()))
        self.classification_model_combo.currentIndexChanged.connect(lambda: (self._persist_settings(), self._update_system_status()))
        self.profile_combo.currentIndexChanged.connect(lambda: (self._persist_settings(), self._update_system_status()))
        self.confidence_spin.valueChanged.connect(lambda: self._persist_settings())
        self.operator_input.editingFinished.connect(self._persist_settings)

    def _combo_path(self, combo: QComboBox) -> Path | None:
        data = combo.currentData()
        return Path(data) if data else None

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
        self.camera.disconnect()
        log.info("Aplicacao encerrada")
        event.accept()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #f4f6f8; color: #18212f; font-size: 14px; }
            QScrollArea { border: 0; background: #f4f6f8; }
            QGroupBox { border: 1px solid #c8d0da; border-radius: 6px; margin-top: 12px; padding: 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton { background: #1f6feb; color: white; border: 0; border-radius: 6px; padding: 10px 12px; font-weight: 600; min-height: 24px; }
            QPushButton:disabled { background: #98a2b3; }
            QComboBox, QLineEdit, QDoubleSpinBox { background: white; border: 1px solid #b8c2cc; border-radius: 5px; padding: 8px; }
            #imagePanel { background: #101828; color: #f8fafc; border-radius: 6px; }
            #statusLabel { background: #172033; color: white; padding: 10px; border-radius: 4px; font-weight: 600; }
            #resultLabel { font-size: 22px; font-weight: 700; padding: 16px; background: white; border-radius: 6px; }
            """
        )


