# Receipt Scanner

A local Mac app: hold a grocery or restaurant receipt up to the webcam, OCR it, **keep only the food**, attach that food’s share of sales tax, and append those rows to a CSV. Nothing is sent to a cloud OCR service.

```
./run.sh
```

## Daily use

1. Run `./run.sh` (or double-click `Receipt Scanner.command` in Finder).
2. Hold the receipt in the camera until the text looks sharp.
3. Press **Space** or click **Capture** to freeze the frame.
4. Review the table:
   - **Keep** is checked for food, unchecked for alcohol, clothes, appliances, household, pharmacy.
   - **Food** is the roll-up name (`BNN ORG` → `Banana`) so you can total “how much I spend on bananas.”
   - **T** means the line was taxable. Receipt tax is split across taxable lines by price — beer tax does not get dumped onto bananas.
5. Click **Append qualifying food to CSV**. Existing rows are never overwritten.

No camera? Use **Open image…** or:

```bash
./run.sh --image ~/Desktop/receipt.jpg
```

Spend so far, grouped by food:

```bash
./run.sh --summary
```

## Why not use the receipt total?

A HEB trip might mix bananas, beer, paper towels, and an air fryer. The printed total is not “food spend.” The app:

1. Reads every priced line (layouts differ; the review step is the safety net).
2. Expands store abbreviations onto a stable **food** key (`MLK 2% GAL` → `Milk`).
3. Drops non-qualifying categories by default (alcohol, household, appliances, clothes, pharmacy, pet). Tick the box if you actually want a line.
4. Parses the **SALES TAX** total and any `T` / `F` flags on grocery lines.
5. Allocates tax as `receipt_tax × (line_price / sum of all taxable line prices)`. Only checked food rows are written, each with its own `tax` and `total`.

In Texas, most grocery staples are untaxed (`F`) while alcohol, soda, and household goods are taxed (`T`). Restaurant food is treated as taxable. You can override the **T** checkbox before saving.

Rename a **Food** cell when the guess is wrong — that mapping is saved to `data/catalog.json` so the next `BNN ORG` lands on Banana automatically. Copy `data/catalog.example.json` to `data/catalog.json` to add your own aliases / exclude phrases.

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
| `timestamp` | Local ISO time of the save (`2026-11-23T13:52:00`) |
| `item` | Text as printed on the receipt |
| `food` | Canonical name used for per-food totals (`Banana`) |
| `category` | `food`, `alcohol`, `household`, … |
| `price` | Pre-tax dollars (`2.49`) |
| `tax` | This line’s share of the receipt tax (`0.00` if exempt) |
| `total` | `price + tax` — this is what to sum for “spend on this food” |
| `included` | `yes` for rows that were checked |
| `taxable` | `yes` if this line was in the tax base |
| `merchant` | Store or restaurant |
| `source_image` | Photo used (`data/captures/…` or the file you opened) |

Only checked food rows are appended. An older 5-column file is upgraded in place (rows kept, new columns filled).

### Where the CSV lives

| Priority | Source |
| --- | --- |
| 1 | `./run.sh --csv /path/to/receipts.csv` |
| 2 | `RECEIPT_CSV` environment variable |
| 3 | Project `data/receipts.csv` |

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
  parse.py       pair descriptions with $X.XX; capture tax total and T/F flags
  catalog.py     abbreviations, food keys, exclude lists
  qualify.py     include/exclude + tax allocation
  summary.py     spend per food
  csv_log.py     create-with-header / append
  app.py         Tk review UI
  config.py      paths and settings
```

## CLI extras

```bash
./run.sh --help
./run.sh --engine tesseract --image tests/fixtures/sample_receipt.png --print-only
./run.sh --summary
./run.sh --csv ~/Documents/receipts.csv
```

`--print-only` is for sanity checks: OCR + qualify, no window.

## Privacy

Camera frames, captured JPEGs, the CSV, and `data/catalog.json` stay on this Mac. There is no default network OCR. Captures land in `data/captures/`; delete that folder anytime.

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| Black / no preview | Camera permission for Terminal; try `--camera 1` |
| “Tesseract is not on PATH” | `brew install tesseract` then restart the app |
| UI will not start | `brew install python-tk` (Homebrew Python) |
| Garbled items | Flatten the paper, fill more of the frame, better light; then edit the review table |
| Wrong food name | Type the canonical name in **Food**; it is remembered in `data/catalog.json` |
| Tax looks high on groceries | Uncheck **T** on exempt staples, or set **Receipt tax** from the printed line |
| `.command` blocked | Right-click → Open, or `chmod +x "Receipt Scanner.command"` |

## Tests

```bash
source .venv/bin/activate   # after the first ./run.sh
pytest -q
```

Parser, catalog, tax, and CSV tests do not need a camera. The synthetic-receipt OCR test needs `tesseract` on `PATH`.
