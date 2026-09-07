# Receipt Scanner

A local Mac app: hold a grocery or restaurant receipt up to the webcam, OCR it, confirm the food items and prices, and **append** them to a CSV. Nothing is sent to a cloud OCR service.

```
./run.sh
```

## Daily use

1. Run `./run.sh` (or double-click `Receipt Scanner.command` in Finder).
2. Hold the receipt in the camera until the text looks sharp.
3. Press **Space** or click **Capture** to freeze the frame.
4. Edit anything the parser got wrong. Add or delete rows.
5. Click **Append to CSV**. Existing rows are never overwritten.

No camera? Use **Open image…** or:

```bash
./run.sh --image ~/Desktop/receipt.jpg
```

## Install (once)

### System dependencies (Homebrew)

```bash
brew install python tesseract
# If `python3 -c "import tkinter"` fails:
brew install python-tk
```

Grant **Camera** access to Terminal (or iTerm) the first time you launch:
**System Settings → Privacy & Security → Camera**.

Optional, often more accurate on Apple Silicon / recent macOS:

```bash
source .venv/bin/activate
pip install pyobjc-framework-Vision pyobjc-framework-Quartz
```

`./run.sh` prefers Apple Vision when those packages import cleanly, otherwise Tesseract.

### First launch

```bash
git clone https://github.com/LukeConran/ocr-receipt-reader.git
cd ocr-receipt-reader
chmod +x run.sh "Receipt Scanner.command"
./run.sh
```

The script creates `.venv`, installs this package, and opens the UI.

## CSV schema

Default file: **`data/receipts.csv`** (created on first save if missing).

| Column | Meaning |
| --- | --- |
| `timestamp` | Local ISO time of the save (`2026-09-07T08:30:00`) |
| `item` | Food / line-item name (editable in the review step) |
| `price` | Decimal dollars, two places (`2.49`). Negatives allowed (deposits / voids). |
| `merchant` | Store or restaurant if the header parsed, else blank / whatever you typed |
| `source_image` | Path to the photo used (`data/captures/…` for webcam frames, or the file you opened) |

The file is **append-only**. A header is written only when the path is new or empty.

### Where the CSV lives

| Priority | Source |
| --- | --- |
| 1 | `./run.sh --csv /path/to/receipts.csv` |
| 2 | `RECEIPT_CSV` environment variable |
| 3 | Project `data/receipts.csv` |

To log under Documents instead:

```bash
export RECEIPT_CSV="$HOME/Documents/receipts.csv"
./run.sh
```

The path is also editable in the UI before you save.

## Project layout

```
src/receipt_ocr/
  camera.py      live webcam (OpenCV / AVFoundation)
  preprocess.py  crop, denoise, deskew, threshold
  ocr.py         Tesseract + optional Apple Vision
  parse.py       pair descriptions with $X.XX, drop totals/tax
  csv_log.py     create-with-header / append
  app.py         Tk review UI
  config.py      paths and settings
```

## CLI extras

```bash
./run.sh --help
./run.sh --engine tesseract --image tests/fixtures/sample_receipt.png --print-only
./run.sh --csv ~/Documents/receipts.csv
```

`--print-only` is for sanity checks: OCR + parse, no window.

## Privacy

Camera frames, captured JPEGs, and the CSV stay on this Mac. There is no default network OCR. Captures land in `data/captures/` so you can see what was logged; delete that folder anytime.

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| Black / no preview | Camera permission for Terminal; try `--camera 1` |
| “Tesseract is not on PATH” | `brew install tesseract` then restart the app |
| UI will not start | `brew install python-tk` (Homebrew Python) |
| Garbled items | Flatten the paper, fill more of the frame, better light; then edit the review table |
| `.command` blocked | Right-click → Open, or `chmod +x "Receipt Scanner.command"` |

## Tests

```bash
source .venv/bin/activate   # after the first ./run.sh
pytest -q
```

Parser and CSV tests do not need a camera. The synthetic-receipt OCR test needs `tesseract` on `PATH`.
