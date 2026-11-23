"""Append-only CSV logging. Creates the file with a header if it is missing."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from receipt_ocr.config import CSV_COLUMNS
from receipt_ocr.parse import ReceiptItem

_LEGACY_COLUMNS = ("timestamp", "item", "price", "merchant", "source_image")


def _row_from_item(
    item: ReceiptItem,
    *,
    when: str,
    merchant: str,
    source: str,
) -> dict[str, str]:
    return {
        "timestamp": when,
        "item": item.item,
        "food": (item.food or item.item).strip(),
        "category": item.category or "",
        "price": f"{item.price:.2f}",
        "tax": f"{item.tax:.2f}",
        "total": f"{item.total:.2f}",
        "included": "yes" if item.include else "no",
        "taxable": "yes" if item.taxable else "no",
        "merchant": merchant,
        "source_image": source,
    }


def ensure_csv(path: Path) -> None:
    """Create ``path`` with a header row, or add any missing columns.

    Existing receipt rows are kept. New columns on old rows are left blank
    (except ``food``/``total``, which copy ``item``/``price`` when we can).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(list(CSV_COLUMNS))
        return

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        existing = tuple(reader.fieldnames or [])
        rows = list(reader)
    if existing == CSV_COLUMNS:
        return

    upgraded: list[dict[str, str]] = []
    for row in rows:
        merged = {column: row.get(column, "") or "" for column in CSV_COLUMNS}
        if not merged["food"]:
            merged["food"] = row.get("item", "")
        if not merged["total"]:
            merged["total"] = row.get("price", "")
        if not merged["tax"]:
            merged["tax"] = "0.00" if row.get("price") else ""
        if not merged["included"]:
            merged["included"] = "yes"
        upgraded.append(merged)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        writer.writerows(upgraded)


def append_items(
    path: Path,
    items: list[ReceiptItem],
    *,
    merchant: str | None = None,
    source_image: str | Path | None = None,
    timestamp: datetime | None = None,
    included_only: bool = True,
) -> int:
    """Append item rows. Never truncates an existing file.

    By default only ``include=True`` rows are written — skipped alcohol /
    household lines stay off the food log. Returns the number of rows written.
    """
    chosen = [item for item in items if item.include] if included_only else list(items)
    if not chosen:
        return 0
    ensure_csv(path)
    when = (timestamp or datetime.now()).isoformat(timespec="seconds")
    merchant_value = (merchant or "").strip()
    source = str(source_image) if source_image else ""
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        for item in chosen:
            if item.total == 0 and item.price:
                item.total = round(item.price + item.tax, 2)
            writer.writerow(
                _row_from_item(item, when=when, merchant=merchant_value, source=source)
            )
    return len(chosen)
