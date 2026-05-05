from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


class BaslerCameraError(RuntimeError):
    pass


@dataclass(frozen=True)
class CameraInfo:
    model: str
    serial: str
    width: int
    height: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class BaslerCamera:
    def __init__(self) -> None:
        self._camera = None
        self._pylon = None
        self.active_profile: Path | None = None
        self.last_info: CameraInfo | None = None

    @property
    def is_open(self) -> bool:
        return bool(self._camera and self._camera.IsOpen())

    def connect(self) -> CameraInfo:
        try:
            from pypylon import pylon
        except Exception as exc:
            raise BaslerCameraError("pypylon nao esta disponivel nesta venv.") from exc

        self._pylon = pylon
        factory = pylon.TlFactory.GetInstance()
        devices = factory.EnumerateDevices()
        if not devices:
            raise BaslerCameraError("Nenhuma camera Basler foi encontrada.")

        if len(devices) > 1:
            log.warning("Mais de uma camera Basler encontrada; usando a primeira. total=%s", len(devices))

        self._camera = pylon.InstantCamera(factory.CreateDevice(devices[0]))
        self._camera.Open()
        self.last_info = self.info()
        log.info("Camera Basler conectada | %s", self.last_info)
        return self.last_info

    def disconnect(self) -> None:
        if self._camera:
            try:
                if self._camera.IsGrabbing():
                    self._camera.StopGrabbing()
                if self._camera.IsOpen():
                    self._camera.Close()
                log.info("Camera Basler desconectada")
            finally:
                self._camera = None

    def info(self) -> CameraInfo:
        if not self._camera:
            raise BaslerCameraError("Camera Basler nao conectada.")
        device = self._camera.GetDeviceInfo()
        return CameraInfo(
            model=device.GetModelName(),
            serial=device.GetSerialNumber(),
            width=int(self._camera.Width.Value),
            height=int(self._camera.Height.Value),
        )

    def apply_profile(self, profile_path: Path) -> None:
        if not self._camera or not self._pylon:
            raise BaslerCameraError("Conecte a camera antes de aplicar perfil.")
        if not profile_path.exists():
            raise BaslerCameraError(f"Perfil nao encontrado: {profile_path}")
        self._pylon.FeaturePersistence.Load(str(profile_path), self._camera.GetNodeMap(), True)
        self.active_profile = profile_path.resolve()
        self.last_info = self.info()
        log.info("Perfil PFS aplicado | profile=%s", self.active_profile)

    def capture(self, timeout_ms: int = 5000) -> np.ndarray:
        if not self._camera or not self._pylon:
            raise BaslerCameraError("Camera Basler nao conectada.")

        result = self._camera.GrabOne(timeout_ms)
        if not result.GrabSucceeded():
            error = result.GetErrorDescription()
            result.Release()
            log.error("Falha na captura Basler | %s", error)
            raise BaslerCameraError(f"Falha na captura Basler: {error}")

        try:
            image = result.Array
            if image.ndim == 2:
                frame = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            else:
                frame = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            log.info("Imagem capturada | shape=%s", frame.shape)
            return frame
        finally:
            result.Release()

    def context(self) -> dict[str, object]:
        return {
            "camera": self.last_info.to_dict() if self.last_info else {},
            "profile": {
                "name": self.active_profile.name if self.active_profile else "",
                "path": str(self.active_profile) if self.active_profile else "",
            },
        }
