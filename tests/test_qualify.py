from receipt_ocr.catalog import Catalog, UserCatalog
from receipt_ocr.parse import parse_receipt_text
from receipt_ocr.qualify import qualify_receipt, qualifying_totals
from receipt_ocr.summary import format_summary, summarize_csv
from receipt_ocr.csv_log import append_items


MIXED_GROCERY = """
HEB
AUSTIN TX

BNN ORG                      2.49 F
MLK 2% GAL                   3.89 F
ORG STRWBRY                  4.50 F
MODELO 12PK                 15.99 T
PAPER TOWELS                 6.49 T
AIR FRYER 5QT               49.99 T
CREW SOCKS 6PK               8.00 T

SUBTOTAL                    91.35
SALES TAX                    6.64
TOTAL                       97.99
"""

RESTAURANT = """
TACO MORENO

CARNE ASADA TACO             4.50
PASTOR TACO                  4.25
MODELO DRAFT                 6.00
CHIPS & SALSA                2.50

SUBTOTAL                    17.25
TAX                          1.42
TIP                          3.00
TOTAL                       21.67
"""


def test_abbreviations_and_excludes() -> None:
    parsed = qualify_receipt(parse_receipt_text(MIXED_GROCERY), Catalog(UserCatalog()))
    by_item = {item.item.lower(): item for item in parsed.items}
    assert by_item["bnn org"].food == "Banana"
    assert by_item["bnn org"].include is True
    assert by_item["bnn org"].taxable is False
    assert by_item["mlk 2% gal"].food == "Milk"
    assert by_item["org strwbry"].food == "Strawberry"
    assert by_item["modelo 12pk"].include is False
    assert by_item["modelo 12pk"].category == "alcohol"
    assert by_item["paper towels"].include is False
    assert by_item["air fryer 5qt"].include is False
    assert by_item["crew socks 6pk"].include is False


def test_tax_stays_on_taxable_lines_not_exempt_food() -> None:
    parsed = qualify_receipt(parse_receipt_text(MIXED_GROCERY), Catalog(UserCatalog()))
    bananas = next(i for i in parsed.items if i.food == "Banana")
    beer = next(i for i in parsed.items if "modelo" in i.item.lower())
    towels = next(i for i in parsed.items if "paper" in i.item.lower())
    assert bananas.tax == 0.0
    assert beer.tax > 0
    assert towels.tax > 0
    # Beer tax must not be dumped onto bananas.
    price, tax, total = qualifying_totals(parsed.items)
    assert price == 2.49 + 3.89 + 4.50
    assert tax == 0.0
    assert total == price
    taxable_tax = round(sum(i.tax for i in parsed.items if i.taxable), 2)
    assert taxable_tax == 6.64


def test_restaurant_food_gets_its_share_of_tax() -> None:
    parsed = qualify_receipt(parse_receipt_text(RESTAURANT), Catalog(UserCatalog()))
    assert parsed.kind == "restaurant"
    beer = next(i for i in parsed.items if "modelo" in i.item.lower())
    assert beer.include is False
    tacos = [i for i in parsed.items if i.include]
    assert all(i.taxable for i in tacos)
    assert all(i.tax > 0 for i in tacos)
    _, tax, total = qualifying_totals(parsed.items)
    # Tax share is proportional to price among ALL taxable lines, including beer.
    all_taxable = sum(i.price for i in parsed.items if i.taxable)
    food_price = sum(i.price for i in tacos)
    expected = round(1.42 * food_price / all_taxable, 2)
    assert abs(tax - expected) <= 0.02
    assert total == round(food_price + tax, 2)


def test_user_alias_overlay() -> None:
    user = UserCatalog(aliases={"weird sku 99": "Chicken"})
    catalog = Catalog(user)
    food, category, include = catalog.classify("WEIRD SKU 99")
    assert food == "Chicken"
    assert include is True
    assert category == "food"


def test_wine_vinegar_is_food() -> None:
    catalog = Catalog(UserCatalog())
    food, category, include = catalog.classify("RED WINE VINEGAR")
    assert include is True
    assert food == "Vinegar"
    assert category == "food"


def test_summary_groups_by_food(tmp_path) -> None:
    from receipt_ocr.parse import ReceiptItem
    from datetime import datetime

    path = tmp_path / "receipts.csv"
    first = [
        ReceiptItem(item="BNN ORG", price=2.49, food="Banana", tax=0.0, total=2.49, include=True),
        ReceiptItem(item="MODELO", price=15.99, food="Modelo", tax=1.32, total=17.31, include=False),
    ]
    second = [
        ReceiptItem(item="BANANAS", price=1.20, food="Banana", tax=0.0, total=1.20, include=True),
    ]
    append_items(path, first, merchant="HEB", timestamp=datetime(2026, 11, 23, 8, 0, 0))
    append_items(path, second, merchant="HEB", timestamp=datetime(2026, 11, 23, 9, 0, 0))
    rows = summarize_csv(path)
    assert len(rows) == 1
    assert rows[0].food == "Banana"
    assert rows[0].trips == 2
    assert round(rows[0].total, 2) == 3.69
    text = format_summary(rows)
    assert "Banana" in text
    assert "3.69" in text
