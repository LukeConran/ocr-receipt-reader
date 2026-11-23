"""Tkinter UI: live camera, capture, review, append to CSV."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Sequence

import numpy as np
from PIL import Image, ImageTk

from receipt_ocr.camera import Camera
from receipt_ocr.catalog import Catalog, UserCatalog, default_catalog
from receipt_ocr.config import APP_NAME, Settings
from receipt_ocr.csv_log import append_items, ensure_csv
from receipt_ocr.ocr import (
    OCRError,
    describe_ocr_backend,
    image_to_text,
    load_image_bgr,
    tesseract_available,
    vision_available,
)
from receipt_ocr.parse import ParsedReceipt, ReceiptItem, parse_receipt_text
from receipt_ocr.qualify import allocate_tax, qualify_receipt, qualifying_totals
from receipt_ocr.summary import format_summary, summarize_csv

log = logging.getLogger(__name__)

PREVIEW_W = 640
PREVIEW_H = 480
BG = "#1c1c1e"
PANEL = "#2c2c2e"
FG = "#f2f2f7"
MUTED = "#8e8e93"
ACCENT = "#0a84ff"


@dataclass
class RowState:
    include: tk.BooleanVar
    item: tk.StringVar
    food: tk.StringVar
    category: tk.StringVar
    price: tk.StringVar
    tax: tk.StringVar
    taxable: tk.BooleanVar
    frame: ttk.Frame


class ReceiptApp(tk.Tk):
    def __init__(self, settings: Settings, startup_image: Path | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.catalog: Catalog = default_catalog()
        self.title(APP_NAME)
        self.minsize(1280, 720)
        self.configure(bg=BG)

        self.camera = Camera(index=settings.camera_index)
        self._photo: ImageTk.PhotoImage | None = None
        self._frozen: np.ndarray | None = None
        self._live = True
        self._busy = False
        self._source_image: Path | None = None
        self._rows: list[RowState] = []
        self._tax_total: float | None = None
        self._kind = "unknown"
        self._syncing = False

        self._build_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<space>", self._on_space)
        self.bind("<Escape>", lambda _e: self._retake())

        self.after(100, self._boot, startup_image)

    def _build_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("App.TLabel", background=BG, foreground=FG, font=("Helvetica", 13))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Helvetica", 11))
        style.configure("Panel.TLabel", background=PANEL, foreground=FG, font=("Helvetica", 12))
        style.configure("Tiny.TLabel", background=PANEL, foreground=MUTED, font=("Helvetica", 10))
        style.configure("Title.TLabel", background=BG, foreground=FG, font=("Helvetica", 20, "bold"))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Helvetica", 11))
        style.configure("Accent.TButton", font=("Helvetica", 13, "bold"), padding=(14, 8))
        style.configure("App.TButton", font=("Helvetica", 12), padding=(10, 6))
        style.configure("App.TCheckbutton", background=PANEL, foreground=FG)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="App.TFrame", padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side=tk.LEFT)
        self.backend_var = tk.StringVar(value=f"OCR: {describe_ocr_backend(self.settings.ocr_engine)}")
        ttk.Label(header, textvariable=self.backend_var, style="Muted.TLabel").pack(
            side=tk.RIGHT, padx=(12, 0)
        )

        body = ttk.Frame(root, style="App.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        right = ttk.Frame(body, style="Panel.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew")

        self.preview = tk.Label(
            left,
            bg="#000000",
            fg=MUTED,
            text="Starting camera…\nHold a receipt in view, then press Space or Capture.",
            font=("Helvetica", 14),
            width=PREVIEW_W // 8,
            height=PREVIEW_H // 18,
        )
        self.preview.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(left, style="App.TFrame")
        controls.pack(fill=tk.X, pady=(10, 0))
        self.capture_btn = ttk.Button(
            controls, text="Capture", style="Accent.TButton", command=self.capture
        )
        self.capture_btn.pack(side=tk.LEFT)
        ttk.Button(controls, text="Retake", style="App.TButton", command=self._retake).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(
            controls, text="Open image…", style="App.TButton", command=self._open_image
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(right, text="Review qualifying food", style="Panel.TLabel").pack(anchor="w")
        ttk.Label(
            right,
            text="Check the foods to keep. Uncheck alcohol, clothes, gadgets. Tax is split only onto taxable lines.",
            style="Muted.TLabel",
            wraplength=520,
        ).pack(anchor="w", pady=(0, 8))

        merchant_row = ttk.Frame(right, style="Panel.TFrame")
        merchant_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(merchant_row, text="Merchant", style="Panel.TLabel").pack(side=tk.LEFT)
        self.merchant_var = tk.StringVar()
        ttk.Entry(merchant_row, textvariable=self.merchant_var, width=28).pack(
            side=tk.LEFT, padx=(8, 8), fill=tk.X, expand=True
        )
        ttk.Label(merchant_row, text="Receipt tax", style="Panel.TLabel").pack(side=tk.LEFT)
        self.tax_total_var = tk.StringVar(value="")
        ttk.Entry(merchant_row, textvariable=self.tax_total_var, width=8).pack(side=tk.LEFT, padx=(8, 0))
        self.tax_total_var.trace_add("write", lambda *_: self._recompute_tax())

        header_row = ttk.Frame(right, style="Panel.TFrame")
        header_row.pack(fill=tk.X)
        ttk.Label(header_row, text="Keep", style="Tiny.TLabel", width=5).pack(side=tk.LEFT)
        ttk.Label(header_row, text="Receipt line", style="Tiny.TLabel").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(header_row, text="Food", style="Tiny.TLabel", width=14).pack(side=tk.LEFT)
        ttk.Label(header_row, text="Price", style="Tiny.TLabel", width=8).pack(side=tk.LEFT)
        ttk.Label(header_row, text="Tax", style="Tiny.TLabel", width=7).pack(side=tk.LEFT)
        ttk.Label(header_row, text="T", style="Tiny.TLabel", width=3).pack(side=tk.LEFT)

        canvas_wrap = ttk.Frame(right, style="Panel.TFrame")
        canvas_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.rows_canvas = tk.Canvas(canvas_wrap, bg=PANEL, highlightthickness=0, height=280)
        scroll = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self.rows_canvas.yview)
        self.rows_frame = ttk.Frame(self.rows_canvas, style="Panel.TFrame")
        self.rows_frame.bind(
            "<Configure>",
            lambda _e: self.rows_canvas.configure(scrollregion=self.rows_canvas.bbox("all")),
        )
        self._rows_window = self.rows_canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_canvas.configure(yscrollcommand=scroll.set)
        self.rows_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.rows_canvas.bind(
            "<Configure>",
            lambda e: self.rows_canvas.itemconfigure(self._rows_window, width=e.width),
        )

        row_btns = ttk.Frame(right, style="Panel.TFrame")
        row_btns.pack(fill=tk.X)
        ttk.Button(row_btns, text="Add row", style="App.TButton", command=self._add_blank_row).pack(
            side=tk.LEFT
        )
        self.totals_var = tk.StringVar(value="No qualifying food yet.")
        ttk.Label(row_btns, textvariable=self.totals_var, style="Panel.TLabel").pack(
            side=tk.RIGHT
        )

        self.save_btn = ttk.Button(
            right, text="Append qualifying food to CSV", style="Accent.TButton", command=self._save
        )
        self.save_btn.pack(fill=tk.X, pady=(12, 0))

        csv_row = ttk.Frame(right, style="Panel.TFrame")
        csv_row.pack(fill=tk.X, pady=(8, 0))
        self.csv_var = tk.StringVar(value=str(self.settings.csv_path))
        ttk.Entry(csv_row, textvariable=self.csv_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(csv_row, text="Browse…", style="App.TButton", command=self._browse_csv).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.status_var = tk.StringVar(value="Ready. Point the camera at a receipt.")
        ttk.Label(root, textvariable=self.status_var, style="Status.TLabel").pack(
            fill=tk.X, pady=(10, 0)
        )

    def _boot(self, startup_image: Path | None) -> None:
        backend = describe_ocr_backend(self.settings.ocr_engine)
        self.backend_var.set(f"OCR: {backend}")
        if startup_image:
            self._load_path(startup_image)
            return
        opened = self.camera.start()
        if opened:
            self.status_var.set("Live preview. Space or Capture when the receipt is sharp.")
            self._tick_preview()
            return
        self.preview.configure(
            text=(
                "No camera detected.\n\n"
                "Use Open image… to scan a photo,\n"
                "or grant Camera access and restart.\n\n"
                f"{self.camera.error or ''}"
            )
        )
        self.status_var.set(self.camera.error or "Camera unavailable — open an image instead.")

    def _tick_preview(self) -> None:
        if not self._live:
            return
        frame = self.camera.latest_frame()
        if frame is not None:
            self._show_frame(frame)
        self.after(33, self._tick_preview)

    def _show_frame(self, frame_bgr: np.ndarray) -> None:
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        image.thumbnail((PREVIEW_W, PREVIEW_H), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)
        self.preview.configure(image=self._photo, text="")

    def _on_space(self, event: tk.Event) -> str | None:  # type: ignore[type-arg]
        widget = event.widget
        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
            return None
        self.capture()
        return "break"

    def capture(self) -> None:
        if self._busy:
            return
        frame = self.camera.latest_frame()
        if frame is None:
            messagebox.showinfo(APP_NAME, "No camera frame yet. Open an image instead.")
            return
        self._freeze_and_ocr(frame, source_label="camera")

    def _open_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Open receipt image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.heic *.webp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._load_path(Path(path))

    def _load_path(self, path: Path) -> None:
        try:
            frame = load_image_bgr(path)
        except OCRError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self._source_image = path
        self._freeze_and_ocr(frame, source_label=str(path))

    def _freeze_and_ocr(self, frame: np.ndarray, source_label: str) -> None:
        self._live = False
        self._frozen = frame
        self._show_frame(frame)
        self.status_var.set(f"Reading text ({describe_ocr_backend(self.settings.ocr_engine)})…")
        self._busy = True
        self.capture_btn.state(["disabled"])
        self.save_btn.state(["disabled"])
        thread = threading.Thread(
            target=self._ocr_worker, args=(frame.copy(), source_label), daemon=True
        )
        thread.start()

    def _ocr_worker(self, frame: np.ndarray, source_label: str) -> None:
        try:
            text = image_to_text(frame, engine=self.settings.ocr_engine)
            parsed = qualify_receipt(parse_receipt_text(text), self.catalog)
            error = None
        except OCRError as exc:
            parsed = ParsedReceipt(merchant=None, items=[], raw_text="")
            error = str(exc)
        except Exception as exc:  # noqa: BLE001
            log.exception("OCR failed")
            parsed = ParsedReceipt(merchant=None, items=[], raw_text="")
            error = str(exc)
        self.after(0, self._apply_parse, parsed, source_label, error)

    def _apply_parse(self, parsed: ParsedReceipt, source_label: str, error: str | None) -> None:
        self._busy = False
        self.capture_btn.state(["!disabled"])
        self.save_btn.state(["!disabled"])
        if error:
            self.status_var.set(error)
            messagebox.showerror(APP_NAME, error)
            return
        if parsed.merchant:
            self.merchant_var.set(parsed.merchant)
        self._kind = parsed.kind or self.catalog.merchant_kind(parsed.merchant)
        self._tax_total = parsed.tax_total
        self.tax_total_var.set("" if parsed.tax_total is None else f"{parsed.tax_total:.2f}")
        self._set_rows(parsed.items)
        kept = sum(1 for item in parsed.items if item.include)
        skipped = len(parsed.items) - kept
        price, tax, total = qualifying_totals(parsed.items)
        extra = f" Skipped {skipped} non-food line(s)." if skipped else ""
        if parsed.items:
            self.status_var.set(
                f"{kept} qualifying food line(s) from {source_label} → ${total:.2f}"
                f" (price ${price:.2f} + tax ${tax:.2f}).{extra} Review, then append."
            )
        else:
            self.status_var.set(
                "No priced items found. Add rows by hand or retake with the receipt flatter / closer."
            )

    def _clear_rows(self) -> None:
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows.clear()

    def _set_rows(self, items: Sequence[ReceiptItem]) -> None:
        self._clear_rows()
        if items:
            for item in items:
                self._add_row(item)
        else:
            self._add_blank_row()
        self._recompute_tax()

    def _add_blank_row(self) -> None:
        self._add_row(ReceiptItem(item="", price=0.0, include=True, category="food", food=""))

    def _add_row(self, item: ReceiptItem) -> None:
        include = tk.BooleanVar(value=item.include)
        item_var = tk.StringVar(value=item.item)
        food_var = tk.StringVar(value=item.food or item.item)
        category_var = tk.StringVar(value=item.category or "unknown")
        price_var = tk.StringVar(value="" if item.item == "" and item.price == 0 else f"{item.price:.2f}")
        tax_var = tk.StringVar(value=f"{item.tax:.2f}")
        taxable = tk.BooleanVar(value=bool(item.taxable))

        row = ttk.Frame(self.rows_frame, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=3)
        ttk.Checkbutton(row, variable=include, command=self._recompute_tax).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=item_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        ttk.Entry(row, textvariable=food_var, width=14).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(row, textvariable=price_var, width=8).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(row, textvariable=tax_var, width=7).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Checkbutton(row, variable=taxable, command=self._recompute_tax).pack(side=tk.LEFT)
        state = RowState(
            include=include,
            item=item_var,
            food=food_var,
            category=category_var,
            price=price_var,
            tax=tax_var,
            taxable=taxable,
            frame=row,
        )
        ttk.Button(row, text="✕", width=3, command=lambda s=state: self._remove_row(s)).pack(side=tk.LEFT)
        self._rows.append(state)
        price_var.trace_add("write", lambda *_: self._recompute_tax())
        item_var.trace_add("write", lambda *_: self._on_item_edited(state))

    def _on_item_edited(self, state: RowState) -> None:
        if self._syncing:
            return
        name = state.item.get().strip()
        if not name:
            return
        food, category, include = self.catalog.classify(name)
        if not state.food.get().strip():
            state.food.set(food or name)
        state.category.set(category)
        if category not in {"food", "unknown"}:
            state.include.set(include)
            merchant = self.merchant_var.get().strip()
            kind = self.catalog.merchant_kind(merchant) if merchant else self._kind
            state.taxable.set(self.catalog.infer_taxable(name, category, kind, None))
        self._recompute_tax()

    def _remove_row(self, state: RowState) -> None:
        if state in self._rows:
            self._rows.remove(state)
        state.frame.destroy()
        self._recompute_tax()

    def _parse_tax_total(self) -> float | None:
        raw = self.tax_total_var.get().strip().replace("$", "")
        if not raw:
            return None
        try:
            return round(float(raw), 2)
        except ValueError:
            return self._tax_total

    def _collect_items(self, *, require_names: bool = True) -> list[ReceiptItem]:
        items: list[ReceiptItem] = []
        for state in self._rows:
            name = state.item.get().strip()
            food = state.food.get().strip()
            raw_price = state.price.get().strip().replace("$", "").replace(",", "")
            if not name and not raw_price and not food:
                continue
            if require_names and not name:
                raise ValueError("Every saved row needs the original item name (or type it in).")
            if not raw_price:
                continue
            try:
                price = float(raw_price)
            except ValueError as exc:
                raise ValueError(f"“{name or food}” has an invalid price: {state.price.get()!r}") from exc
            try:
                tax = float(state.tax.get().strip().replace("$", "") or "0")
            except ValueError:
                tax = 0.0
            items.append(
                ReceiptItem(
                    item=name or food,
                    price=round(price, 2),
                    food=food or name,
                    category=state.category.get() or "unknown",
                    include=bool(state.include.get()),
                    taxable=bool(state.taxable.get()),
                    tax=round(tax, 2),
                    total=round(price + tax, 2),
                )
            )
        return items

    def _recompute_tax(self) -> None:
        if self._syncing:
            return
        try:
            items = self._collect_items(require_names=False)
        except ValueError:
            return
        allocate_tax(items, self._parse_tax_total())
        self._syncing = True
        try:
            filled = [state for state in self._rows if state.price.get().strip() or state.item.get().strip()]
            for state, item in zip(filled, items):
                state.tax.set(f"{item.tax:.2f}")
        finally:
            self._syncing = False
        price, tax, total = qualifying_totals(items)
        skipped = sum(1 for item in items if not item.include)
        skipped_dollars = round(sum(item.price for item in items if not item.include), 2)
        allocated = round(sum(item.tax for item in items), 2)
        receipt_tax = self._parse_tax_total()
        extra = f"  ·  skip {skipped} (${skipped_dollars:.2f})" if skipped else ""
        if receipt_tax and allocated == 0:
            extra += f"  ·  ${receipt_tax:.2f} tax unassigned (tick T on taxed food)"
        self.totals_var.set(
            f"Keep ${total:.2f}  (${price:.2f} + tax ${tax:.2f})" + extra
        )

    def _browse_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            title="CSV log (created if missing, always appended)",
            defaultextension=".csv",
            initialfile="receipts.csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.csv_var.set(path)

    def _save(self) -> None:
        try:
            items = self._collect_items()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        allocate_tax(items, self._parse_tax_total())
        kept = [item for item in items if item.include]
        if not kept:
            messagebox.showinfo(APP_NAME, "Nothing checked as food. Tick the lines you want to log.")
            return
        csv_path = Path(self.csv_var.get()).expanduser()
        source = self._persist_capture()
        try:
            written = append_items(
                csv_path,
                items,
                merchant=self.merchant_var.get().strip() or None,
                source_image=source,
            )
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Could not write CSV:\n{exc}")
            return
        self._remember_aliases(kept)
        price, tax, total = qualifying_totals(items)
        self.status_var.set(
            f"Appended {written} food row(s) totaling ${total:.2f} to {csv_path}"
        )
        messagebox.showinfo(
            APP_NAME,
            f"Saved {written} food item(s)\n${price:.2f} + tax ${tax:.2f} = ${total:.2f}\n{csv_path}",
        )

    def _remember_aliases(self, items: Sequence[ReceiptItem]) -> None:
        for item in items:
            if item.food and item.item and item.food.strip().lower() != item.item.strip().lower():
                self.catalog.user.remember_alias(item.item, item.food)
        self.catalog = Catalog(UserCatalog.load())

    def _persist_capture(self) -> Path | None:
        if not self.settings.save_captures:
            return self._source_image
        if self._source_image is not None:
            return self._source_image
        if self._frozen is None:
            return None
        import cv2

        folder = self.settings.capture_dir
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = folder / f"capture-{stamp}.jpg"
        cv2.imwrite(str(path), self._frozen)
        self._source_image = path
        return path

    def _retake(self) -> None:
        if self._busy:
            return
        self._frozen = None
        self._source_image = None
        if self.camera.latest_frame() is None and self.camera.error is None:
            self.camera.start()
        self._live = True
        if self.camera.latest_frame() is not None or self.camera.error is None:
            self.status_var.set("Live preview. Space or Capture when the receipt is sharp.")
            self._tick_preview()
        else:
            self.preview.configure(image="", text="Open an image or reconnect the camera.")
            self._photo = None
            self.status_var.set(self.camera.error or "Open an image to scan.")

    def _on_close(self) -> None:
        self._live = False
        self.camera.stop()
        self.destroy()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan a receipt with the Mac camera, review qualifying food, append to CSV."
    )
    parser.add_argument("--csv", dest="csv_path", help="CSV path (created if missing).")
    parser.add_argument(
        "--image",
        dest="image",
        help="Skip the camera and OCR this image instead.",
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default 0).")
    parser.add_argument(
        "--engine",
        choices=("auto", "tesseract", "vision"),
        default="auto",
        help="OCR backend. auto prefers Apple Vision on macOS when installed.",
    )
    parser.add_argument(
        "--no-save-captures",
        action="store_true",
        help="Do not write captured frames under data/captures/.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="OCR an --image and print parsed rows (no GUI). Useful for checks.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print spend per food from the CSV and exit.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def _print_only(settings: Settings, image: Path) -> int:
    frame = load_image_bgr(image)
    text = image_to_text(frame, engine=settings.ocr_engine)
    parsed = qualify_receipt(parse_receipt_text(text))
    print(f"engine: {describe_ocr_backend(settings.ocr_engine)}")
    print(f"merchant: {parsed.merchant or ''}")
    print(f"kind: {parsed.kind or ''}")
    print(f"receipt tax: {'' if parsed.tax_total is None else f'{parsed.tax_total:.2f}'}")
    print("--- raw ---")
    print(text.rstrip() or "(empty)")
    print("--- lines ---")
    if not parsed.items:
        print("(none)")
        return 0
    for item in parsed.items:
        flag = "keep" if item.include else "skip"
        taxable = "T" if item.taxable else "F"
        print(
            f"{flag}\t{taxable}\t{item.item}\t{item.food}\t{item.category}\t"
            f"{item.price:.2f}\t{item.tax:.2f}\t{item.total:.2f}"
        )
    price, tax, total = qualifying_totals(parsed.items)
    print("--- qualifying ---")
    print(f"price {price:.2f} + tax {tax:.2f} = {total:.2f}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    settings = Settings.from_cli(
        csv_path=args.csv_path,
        camera_index=args.camera,
        save_captures=not args.no_save_captures,
        ocr_engine=args.engine,
    )
    startup = Path(args.image).expanduser() if args.image else None
    if args.summary:
        print(format_summary(summarize_csv(settings.csv_path)))
        return 0
    if args.print_only:
        if not startup:
            print("--print-only requires --image", file=sys.stderr)
            return 2
        return _print_only(settings, startup)
    if not tesseract_available() and not vision_available():
        print(
            "No local OCR engine found.\n"
            "  brew install tesseract\n"
            "  optional: pip install pyobjc-framework-Vision pyobjc-framework-Quartz",
            file=sys.stderr,
        )
    ensure_csv(settings.csv_path)
    try:
        app = ReceiptApp(settings, startup_image=startup)
    except tk.TclError as exc:
        print(f"Could not start the UI ({exc}). On Homebrew Python: brew install python-tk", file=sys.stderr)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
