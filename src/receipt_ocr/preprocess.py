"""Receipt-oriented image cleanup before OCR."""

from __future__ import annotations

import cv2
import numpy as np


def _largest_textish_region(gray: np.ndarray) -> np.ndarray:
    """Crop toward the receipt paper when the frame is mostly desk/hand."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 140)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return gray
    h, w = gray.shape[:2]
    frame_area = float(h * w)
    best = None
    best_area = 0.0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < frame_area * 0.12 or area > frame_area * 0.98:
            continue
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < 80 or ch < 80:
            continue
        if area > best_area:
            best_area = area
            best = (x, y, cw, ch)
    if best is None:
        return gray
    x, y, cw, ch = best
    pad = 12
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(w, x + cw + pad)
    y1 = min(h, y + ch + pad)
    return gray[y0:y1, x0:x1]


def _deskew(gray: np.ndarray) -> np.ndarray:
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 50:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.4 or abs(angle) > 20:
        return gray
    h, w = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def preprocess_for_ocr(image_bgr: np.ndarray) -> np.ndarray:
    """Return a high-contrast grayscale image tuned for receipt text."""
    if image_bgr.ndim == 3:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_bgr.copy()

    gray = _largest_textish_region(gray)

    h, w = gray.shape[:2]
    # Tesseract likes a reasonably large character height.
    min_width = 1400
    if w < min_width:
        scale = min_width / max(w, 1)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.fastNlMeansDenoising(gray, None, 15, 7, 21)
    gray = _deskew(gray)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        12,
    )
    return binary
