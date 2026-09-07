"""Heuristics for typical US grocery and restaurant receipts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PRICE_RE = re.compile(r"(?<![\d/])(-?\$?\d{1,4}\.\d{2})(?!\d)")
BARE_PRICE_RE = re.compile(r"^(-?\$?\d{1,4}\.\d{2})$")
PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b"
)
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b", re.I)
STORE_NUM_RE = re.compile(r"\b(?:store|st(?:ore)?\s*#|unit)\b", re.I)

# Lines that are almost never food items.
SKIP_LINE_RE = re.compile(
    r"""
    ^(?:
        (?:sub\s*)?total|grand\s*total|amount\s*due|balance(?:\s*due)?|
        (?:sales\s*)?tax|taxable|hst|gst|pst|vat|
        tip|gratuity|suggested\s*tip|
        change(?:\s*due)?|cash(?:\s*tender(?:ed)?)?|credit|debit|
        visa|mastercard|amex|american\s*express|discover|
        payment|tender|approved|auth(?:orization)?|
        account|card\s*\#|chip\s*read|contactless|
        change|cash\s*back|
        you\s*saved|savings|coupon|promo|
        thank\s*you|thanks\s*for|come\s*again|welcome|
        visit\s*us|www\.|http|receipt\s*\#|
        items?\s*sold|item\s*count|\#\s*items|
        trans(?:action)?(?:\s*\#)?|ref(?:erence)?\s*\#|
        cashier|server|associate|register|lane|
        tel|phone|fax|
        member|rewards?|points
    )\b
    """,
    re.I | re.X,
)

SKIP_CONTAINS = (
    "subtotal",
    "sub-total",
    "amount due",
    "balance due",
    "change due",
    "sales tax",
    "authorized",
    "approval",
    "aid:",
    "tvr:",
    "tsi:",
    "arqc",
    "mid:",
    "tid:",
)

# Quantity / weight prefixes we strip from the item name.
QTY_PREFIX_RE = re.compile(
    r"""^(?:
        \d+\s*[x@×]\s*\$?\d+\.\d{2}\s*|
        \d+(?:\.\d+)?\s*(?:lb|lbs|oz|ct|pk|ea|kg|g)\b\s*(?:@\s*\$?\d+\.\d{2})?\s*|
        \d+\s+
    )""",
    re.I | re.X,
)


@dataclass
class ReceiptItem:
    item: str
    price: float


@dataclass
class ParsedReceipt:
    merchant: str | None
    items: list[ReceiptItem] = field(default_factory=list)
    raw_text: str = ""


def _normalize_spaces(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def _price_to_float(token: str) -> float | None:
    cleaned = token.replace("$", "").replace(",", "").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if abs(value) > 9999:
        return None
    return round(value, 2)


def _looks_like_skip(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if SKIP_LINE_RE.search(stripped):
        return True
    lower = stripped.lower()
    return any(token in lower for token in SKIP_CONTAINS)


def _clean_description(desc: str) -> str:
    desc = desc.replace("*", " ")
    desc = re.sub(r"[|•·]+", " ", desc)
    desc = re.sub(r"\s+[A-Z]\s*$", "", desc)  # trailing taxable flag (T / F)
    desc = re.sub(r"\s+\d{10,}\s*$", "", desc)  # long SKU / UPC at end
    desc = QTY_PREFIX_RE.sub("", desc)
    desc = _normalize_spaces(desc)
    desc = desc.strip(" -._")
    return desc


def _is_plausible_item(name: str) -> bool:
    if len(name) < 2:
        return False
    letters = sum(ch.isalpha() for ch in name)
    if letters < 2:
        return False
    if PHONE_RE.search(name) or DATE_RE.search(name):
        return False
    if re.fullmatch(r"[\d\s./#-]+", name):
        return False
    return True


def _candidate_merchant_lines(lines: list[str]) -> list[str]:
    candidates: list[str] = []
    for line in lines[:12]:
        text = _normalize_spaces(line)
        if not text or _looks_like_skip(text):
            continue
        if PRICE_RE.search(text):
            break
        if PHONE_RE.search(text) or DATE_RE.search(text) or TIME_RE.search(text):
            continue
        if STORE_NUM_RE.search(text):
            continue
        if re.search(r"\d{3,}\s+\w+\s+(st|ave|rd|blvd|dr|ln|way)\b", text, re.I):
            continue
        if re.search(r"\b\d{5}(?:-\d{4})?\b", text):  # ZIP
            continue
        if re.fullmatch(r"[\d\s./#:*-]+", text):
            continue
        letters = sum(ch.isalpha() for ch in text)
        if letters < 3:
            continue
        candidates.append(text)
        if len(candidates) >= 3:
            break
    return candidates


def detect_merchant(text: str) -> str | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    candidates = _candidate_merchant_lines(lines)
    if not candidates:
        return None
    # Prefer a short-ish all-caps banner line (store name).
    for line in candidates:
        if line.isupper() and 3 <= len(line) <= 40:
            return line if len(line) <= 8 else line.title()
    first = candidates[0]
    return first if first.isupper() and len(first) <= 8 else (first.title() if first.isupper() else first)


def parse_receipt_text(text: str, merchant: str | None = None) -> ParsedReceipt:
    """Extract (item, price) pairs from OCR text.

    Designed for typical US grocery/restaurant layouts: description on the
    left, ``$X.XX`` or ``X.XX`` on the right. Totals, tax, tenders, and
    boilerplate are dropped.
    """
    raw = text or ""
    lines = [_normalize_spaces(ln) for ln in raw.splitlines()]
    items: list[ReceiptItem] = []
    pending_desc: str | None = None

    for line in lines:
        if not line:
            pending_desc = None
            continue

        prices = list(PRICE_RE.finditer(line))
        if not prices:
            if not _looks_like_skip(line) and _is_plausible_item(line):
                # Description-only line; price may appear on the next line.
                pending_desc = line
            continue

        last = prices[-1]
        price = _price_to_float(last.group(1))
        if price is None:
            pending_desc = None
            continue

        desc = _normalize_spaces(line[: last.start()])
        if not desc and pending_desc:
            desc = pending_desc
        pending_desc = None

        if _looks_like_skip(desc or line):
            continue
        # Whole-line total still has leftover words like "ORDER TOTAL 12.34".
        if _looks_like_skip(line):
            continue

        desc = _clean_description(desc)
        if not _is_plausible_item(desc):
            continue
        if abs(price) < 0.01:
            continue

        items.append(ReceiptItem(item=desc, price=price))

    resolved_merchant = merchant if merchant is not None else detect_merchant(raw)
    return ParsedReceipt(merchant=resolved_merchant, items=items, raw_text=raw)
