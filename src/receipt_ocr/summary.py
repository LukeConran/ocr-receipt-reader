"""Roll the CSV up by canonical food so you can see spend per item."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from receipt_ocr.csv_log import ensure_csv


@dataclass
class FoodSpend:
    food: str
    trips: int
    price: float
    tax: float
    total: float


def summarize_csv(path: Path) -> list[FoodSpend]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    ensure_csv(path)
    totals: dict[str, FoodSpend] = defaultdict(lambda: FoodSpend("", 0, 0.0, 0.0, 0.0))
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            included = (row.get("included") or "yes").strip().lower()
            if included in {"no", "false", "0"}:
                continue
            food = (row.get("food") or row.get("item") or "").strip()
            if not food:
                continue
            bucket = totals[food.lower()]
            bucket.food = bucket.food or food
            bucket.trips += 1
            bucket.price += _money(row.get("price"))
            bucket.tax += _money(row.get("tax"))
            total = _money(row.get("total"))
            if total == 0:
                total = _money(row.get("price")) + _money(row.get("tax"))
            bucket.total += total
    rows = list(totals.values())
    for row in rows:
        row.price = round(row.price, 2)
        row.tax = round(row.tax, 2)
        row.total = round(row.total, 2)
    rows.sort(key=lambda row: (-row.total, row.food.lower()))
    return rows


def format_summary(rows: list[FoodSpend]) -> str:
    if not rows:
        return "No qualifying food rows yet."
    lines = [f"{'food':<24} {'n':>4} {'price':>10} {'tax':>8} {'total':>10}"]
    lines.append("-" * 60)
    price = tax = total = trips = 0
    for row in rows:
        lines.append(
            f"{row.food:<24} {row.trips:>4} {row.price:>10.2f} {row.tax:>8.2f} {row.total:>10.2f}"
        )
        trips += row.trips
        price += row.price
        tax += row.tax
        total += row.total
    lines.append("-" * 60)
    lines.append(f"{'TOTAL':<24} {trips:>4} {price:>10.2f} {tax:>8.2f} {total:>10.2f}")
    return "\n".join(lines)


def _money(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return 0.0
