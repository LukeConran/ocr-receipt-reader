"""Render a high-contrast fake grocery receipt for local OCR checks."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RECEIPT_LINES = [
    "HEB",
    "AUSTIN TX",
    "",
    "BANANAS ORGANIC          2.49",
    "2% MILK GALLON           3.89",
    "SOURDOUGH BREAD          4.29",
    "AVOCADOS HASS            1.50",
    "",
    "SUBTOTAL                12.17",
    "TAX                      0.85",
    "TOTAL                   13.02",
]

MIXED_LINES = [
    "HEB",
    "AUSTIN TX",
    "",
    "BNN ORG                  2.49 F",
    "MLK 2% GAL               3.89 F",
    "ORG STRWBRY              4.50 F",
    "MODELO 12PK             15.99 T",
    "PAPER TOWELS             6.49 T",
    "AIR FRYER 5QT           49.99 T",
    "CREW SOCKS 6PK           8.00 T",
    "",
    "SUBTOTAL                91.35",
    "SALES TAX                6.64",
    "TOTAL                   97.99",
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/Library/Fonts/Courier New.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _write_lines(path: Path, lines: list[str], *, height: int = 900) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 720
    image = Image.new("RGB", (width, height), (255, 255, 248))
    draw = ImageDraw.Draw(image)
    font = _font(26)
    y = 50
    for line in lines:
        draw.text((40, y), line, fill=(20, 20, 20), font=font)
        y += 44
    image.save(path)
    return path


def write_sample_receipt(path: Path) -> Path:
    return _write_lines(path, RECEIPT_LINES, height=900)


def write_mixed_receipt(path: Path) -> Path:
    return _write_lines(path, MIXED_LINES, height=980)


if __name__ == "__main__":
    dest = Path("tests/fixtures/sample_receipt.png")
    write_sample_receipt(dest)
    print(dest.resolve())
    mixed = Path("tests/fixtures/mixed_grocery_receipt.png")
    write_mixed_receipt(mixed)
    print(mixed.resolve())
