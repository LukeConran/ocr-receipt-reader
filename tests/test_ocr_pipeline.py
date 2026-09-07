from pathlib import Path

import pytest

from receipt_ocr.csv_log import append_items
from receipt_ocr.ocr import image_to_text, tesseract_available
from receipt_ocr.parse import parse_receipt_text
from tests.make_receipt_image import write_sample_receipt

pytestmark = pytest.mark.skipif(
    not tesseract_available(), reason="tesseract binary not installed"
)


def test_ocr_synthetic_receipt_roundtrip(tmp_path: Path) -> None:
    image_path = write_sample_receipt(tmp_path / "sample_receipt.png")
    import cv2

    frame = cv2.imread(str(image_path))
    assert frame is not None
    text = image_to_text(frame, engine="tesseract")
    parsed = parse_receipt_text(text)
    names = " ".join(i.item.lower() for i in parsed.items)
    # OCR can drop a word; require the easy high-contrast grocery lines.
    assert "banana" in names or "milk" in names or "bread" in names
    assert any(i.price in {2.49, 3.89, 4.29, 1.50} for i in parsed.items)
    csv_path = tmp_path / "out.csv"
    written = append_items(csv_path, parsed.items, merchant=parsed.merchant, source_image=image_path)
    assert written == len(parsed.items)
    contents = csv_path.read_text(encoding="utf-8")
    assert contents.startswith("timestamp,item,price,merchant,source_image")
    assert contents.count("\n") >= 2
