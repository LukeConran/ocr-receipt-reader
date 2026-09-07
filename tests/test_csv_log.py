import csv
from datetime import datetime
from pathlib import Path

from receipt_ocr.config import CSV_COLUMNS, resolve_csv_path
from receipt_ocr.csv_log import append_items, ensure_csv
from receipt_ocr.parse import ReceiptItem


def test_creates_header_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "receipts.csv"
    ensure_csv(path)
    rows = list(csv.reader(path.open()))
    assert rows == [list(CSV_COLUMNS)]


def test_append_does_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "receipts.csv"
    first = [ReceiptItem("Bananas", 2.49), ReceiptItem("Milk", 3.89)]
    second = [ReceiptItem("Bread", 4.29)]
    n1 = append_items(
        path,
        first,
        merchant="HEB",
        source_image="captures/a.jpg",
        timestamp=datetime(2026, 9, 7, 8, 30, 0),
    )
    n2 = append_items(
        path,
        second,
        merchant="HEB",
        source_image="captures/b.jpg",
        timestamp=datetime(2026, 9, 7, 9, 0, 0),
    )
    assert n1 == 2 and n2 == 1
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == list(CSV_COLUMNS)
    assert len(rows) == 4
    assert rows[1][1] == "Bananas"
    assert rows[1][2] == "2.49"
    assert rows[3][1] == "Bread"
    assert [r[1] for r in rows[1:]] == ["Bananas", "Milk", "Bread"]


def test_empty_append_is_noop(tmp_path: Path) -> None:
    path = tmp_path / "receipts.csv"
    assert append_items(path, []) == 0
    assert not path.exists()


def test_resolve_csv_env_and_explicit(tmp_path: Path, monkeypatch) -> None:
    explicit = tmp_path / "explicit.csv"
    assert resolve_csv_path(explicit) == explicit.resolve()
    monkeypatch.setenv("RECEIPT_CSV", str(tmp_path / "from-env.csv"))
    assert resolve_csv_path() == (tmp_path / "from-env.csv").resolve()
