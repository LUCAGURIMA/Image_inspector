from __future__ import annotations

import logging
import os
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

    def enumerate_devices(self) -> list[tuple[str, str]]:
        try:
            from pypylon import pylon
        except Exception as exc:
            raise BaslerCameraError("pypylon nao esta disponivel nesta venv.") from exc
        self._pylon = pylon
        factory = pylon.TlFactory.GetInstance()
        return [(device.GetModelName(), device.GetSerialNumber()) for device in factory.EnumerateDevices()]

    def connect(self, serial_number: str | None = None) -> CameraInfo:
        try:
            from pypylon import pylon
        except Exception as exc:
            raise BaslerCameraError("pypylon nao esta disponivel nesta venv.") from exc

        self._pylon = pylon
        factory = pylon.TlFactory.GetInstance()
        devices = factory.EnumerateDevices()
        if not devices:
            raise BaslerCameraError("Nenhuma camera Basler foi encontrada.")
        if serial_number:
            selected = next((device for device in devices if device.GetSerialNumber() == serial_number), None)
            if selected is None:
                raise BaslerCameraError(f"A camera de serie {serial_number} nao foi encontrada.")
        elif len(devices) == 1:
            selected = devices[0]
        else:
            raise BaslerCameraError("Mais de uma camera encontrada. Selecione uma na aba Configuracao.")

        self._camera = pylon.InstantCamera(factory.CreateDevice(selected))
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
                self.active_profile = None

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
            # Follow reference implementation: if we receive a 2D Bayer image,
            # demosaic it to BGR using the BG pattern. If the image already has
            # 3 channels, assume it's already demosaiced and return as-is.
            if image.ndim == 2:
                try:
                    image = cv2.cvtColor(image, cv2.COLOR_BAYER_BG2BGR)
                    log.debug("Imagem Bayer convertida (BG2BGR) | shape=%s", image.shape)
                except cv2.error:
                    image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
                    log.debug("Imagem mono convertida para BGR | shape=%s", image.shape)

            log.info("Imagem capturada | shape=%s | dtype=%s | ndim=%s", image.shape, image.dtype, image.ndim)
            return image
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
