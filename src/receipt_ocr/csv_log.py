"""Append-only CSV logging. Creates the file with a header if it is missing."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from receipt_ocr.config import CSV_COLUMNS
from receipt_ocr.parse import ReceiptItem


def ensure_csv(path: Path) -> None:
    """Create ``path`` with a header row when the file is missing or empty."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(CSV_COLUMNS))


def append_items(
    path: Path,
    items: list[ReceiptItem],
    *,
    merchant: str | None = None,
    source_image: str | Path | None = None,
    timestamp: datetime | None = None,
) -> int:
    """Append item rows. Never truncates an existing file.

    Returns the number of rows written.
    """
    if not items:
        return 0
    ensure_csv(path)
    when = (timestamp or datetime.now()).isoformat(timespec="seconds")
    merchant_value = (merchant or "").strip()
    source = str(source_image) if source_image else ""
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for item in items:
            writer.writerow(
                [
                    when,
                    item.item,
                    f"{item.price:.2f}",
                    merchant_value,
                    source,
                ]
            )
    return len(items)
