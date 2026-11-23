"""Turn parsed receipt lines into qualifying food spend, with tax share."""

from __future__ import annotations

from receipt_ocr.catalog import Catalog, default_catalog
from receipt_ocr.parse import ParsedReceipt, ReceiptItem


def allocate_tax(items: list[ReceiptItem], tax_total: float | None) -> None:
    """Split the receipt tax across *all* taxable lines, by price.

    Qualifying food only receives the share that belongs to those lines.
    Beer tax must not be dumped onto bananas. Pennies of remainder go to
    the last taxable item so the shares still add up to the receipt tax.
    """
    for item in items:
        item.tax = 0.0
        item.total = round(item.price, 2)

    if tax_total is None:
        return
    tax_total = round(float(tax_total), 2)
    if abs(tax_total) < 0.005:
        return

    taxable = [item for item in items if item.taxable and item.price > 0]
    base = round(sum(item.price for item in taxable), 2)
    if not taxable or base <= 0:
        return

    remaining = tax_total
    for index, item in enumerate(taxable):
        if index == len(taxable) - 1:
            share = remaining
        else:
            share = round(tax_total * (item.price / base), 2)
            remaining = round(remaining - share, 2)
        item.tax = share
        item.total = round(item.price + item.tax, 2)


def qualify_receipt(parsed: ParsedReceipt, catalog: Catalog | None = None) -> ParsedReceipt:
    """Fill food / category / include / taxable / tax on each line."""
    catalog = catalog or default_catalog()
    kind = parsed.kind or catalog.merchant_kind(parsed.merchant)
    parsed.kind = kind
    for item in parsed.items:
        food, category, include = catalog.classify(item.item)
        item.food = food or item.item
        item.category = category
        item.include = include
        item.taxable = catalog.infer_taxable(item.item, category, kind, item.taxable)
    allocate_tax(parsed.items, parsed.tax_total)
    return parsed


def qualifying_totals(items: list[ReceiptItem]) -> tuple[float, float, float]:
    chosen = [item for item in items if item.include]
    price = round(sum(item.price for item in chosen), 2)
    tax = round(sum(item.tax for item in chosen), 2)
    total = round(sum(item.total for item in chosen), 2)
    return price, tax, total
