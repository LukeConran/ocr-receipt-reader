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


def write_sample_receipt(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 700, 900
    image = Image.new("RGB", (width, height), (255, 255, 248))
    draw = ImageDraw.Draw(image)
    font = _font(28)
    y = 60
    for line in RECEIPT_LINES:
        draw.text((48, y), line, fill=(20, 20, 20), font=font)
        y += 48
    image.save(path)
    return path


if __name__ == "__main__":
    dest = Path("tests/fixtures/sample_receipt.png")
    write_sample_receipt(dest)
    print(dest.resolve())
