"""Paths and runtime settings. Everything stays on disk locally."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Receipt Scanner"
CSV_COLUMNS = ("timestamp", "item", "price", "merchant", "source_image")

# Repo root: src/receipt_ocr/config.py → parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_CSV = PROJECT_ROOT / "data" / "receipts.csv"
DEFAULT_DOCUMENTS_CSV = Path.home() / "Documents" / "receipts.csv"
DEFAULT_CAPTURE_DIR = PROJECT_ROOT / "data" / "captures"


def _expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def resolve_csv_path(explicit: str | Path | None = None) -> Path:
    """Pick a CSV path without ever overwriting an existing file.

    Order: ``--csv`` / explicit arg, ``RECEIPT_CSV`` env, project
    ``data/receipts.csv``, otherwise ``~/Documents/receipts.csv``.
    """
    if explicit:
        return _expand(explicit)
    env = os.environ.get("RECEIPT_CSV", "").strip()
    if env:
        return _expand(env)
    return DEFAULT_PROJECT_CSV


def resolve_capture_dir(explicit: str | Path | None = None) -> Path:
    if explicit:
        return _expand(explicit)
    env = os.environ.get("RECEIPT_CAPTURE_DIR", "").strip()
    if env:
        return _expand(env)
    return DEFAULT_CAPTURE_DIR


@dataclass(frozen=True)
class Settings:
    csv_path: Path
    capture_dir: Path
    camera_index: int = 0
    save_captures: bool = True
    ocr_engine: str = "auto"  # auto | tesseract | vision

    @classmethod
    def from_cli(
        cls,
        *,
        csv_path: str | Path | None = None,
        capture_dir: str | Path | None = None,
        camera_index: int = 0,
        save_captures: bool = True,
        ocr_engine: str = "auto",
    ) -> Settings:
        return cls(
            csv_path=resolve_csv_path(csv_path),
            capture_dir=resolve_capture_dir(capture_dir),
            camera_index=camera_index,
            save_captures=save_captures,
            ocr_engine=ocr_engine,
        )
