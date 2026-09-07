"""Webcam capture via OpenCV (AVFoundation on macOS)."""

from __future__ import annotations

import logging
import platform
import threading
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

FrameCallback = Callable[[np.ndarray], None]


def _open_capture(index: int):
    import cv2

    if platform.system() == "Darwin":
        cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
        if cap.isOpened():
            return cap
        cap.release()
    cap = cv2.VideoCapture(index)
    return cap


class Camera:
    """Background webcam reader. Latest frame is always BGR."""

    def __init__(self, index: int = 0, width: int = 1280, height: int = 720) -> None:
        self.index = index
        self.width = width
        self.height = height
        self._cap = None
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._error: str | None = None

    @property
    def error(self) -> str | None:
        return self._error

    def start(self) -> bool:
        try:
            import cv2
        except ImportError:
            self._error = "opencv-python is not installed"
            return False
        cap = _open_capture(self.index)
        if not cap.isOpened():
            self._error = (
                f"Could not open camera {self.index}. On a Mac, grant Camera "
                "access to Terminal (or iTerm) in System Settings → Privacy."
            )
            cap.release()
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def _loop(self) -> None:
        assert self._cap is not None
        while self._running:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                continue
            with self._lock:
                self._latest = frame

    def latest_frame(self) -> np.ndarray | None:
        with self._lock:
            if self._latest is None:
                return None
            return self._latest.copy()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                log.debug("camera release failed", exc_info=True)
            self._cap = None
