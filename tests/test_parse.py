from receipt_ocr.parse import detect_merchant, parse_receipt_text

GROCERY = """
HEB
123 MAIN ST
AUSTIN TX 78701
(512) 555-0148
07/04/2026  4:12 PM

BANANAS ORGANIC              2.49
2% MILK GALLON               3.89
SOURDOUGH BREAD              4.29
AVOCADOS HASS            2 @ 1.50     3.00
GROUND TURKEY 93             6.47 T
KROGER COLA 12PK             5.99

SUBTOTAL                    26.13
SALES TAX                    1.83
TOTAL                       27.96
VISA ENDING 1234            27.96
CHANGE                       0.00
THANK YOU FOR SHOPPING
"""

RESTAURANT = """
TACO MORENO
Cedar Park, TX

CARNE ASADA TACO             4.50
PASTOR TACO                  4.25
HORCHATA                     3.00
CHIPS & SALSA                2.50
  GUACAMOLE ADD-ON           1.75

SUBTOTAL                    16.00
TAX                          1.32
TIP                          3.00
TOTAL                       20.32
"""

SPLIT_PRICE = """
TRADER JOE'S

CAGE FREE EGGS
4.99
HONEYCRISP APPLES
3.49
TOTAL 8.48
"""


def test_grocery_pairs_and_skips_totals() -> None:
    parsed = parse_receipt_text(GROCERY)
    names = [item.item.lower() for item in parsed.items]
    assert parsed.merchant == "HEB"
    assert any("banana" in n for n in names)
    assert any("milk" in n for n in names)
    assert any("sourdough" in n for n in names)
    assert any("avocado" in n for n in names)
    assert any("turkey" in n for n in names)
    assert all("total" not in n for n in names)
    assert all("tax" not in n for n in names)
    assert all("visa" not in n for n in names)
    bananas = next(i for i in parsed.items if "banana" in i.item.lower())
    assert bananas.price == 2.49


def test_restaurant_items() -> None:
    parsed = parse_receipt_text(RESTAURANT)
    assert parsed.merchant and "taco" in parsed.merchant.lower()
    assert len(parsed.items) >= 4
    assert {round(i.price, 2) for i in parsed.items} >= {4.50, 4.25, 3.00, 2.50, 1.75}
    assert all("tip" not in i.item.lower() for i in parsed.items)


def test_price_on_following_line() -> None:
    parsed = parse_receipt_text(SPLIT_PRICE)
    names = [i.item.lower() for i in parsed.items]
    assert any("egg" in n for n in names)
    assert any("apple" in n for n in names)
    assert [i.price for i in parsed.items] == [4.99, 3.49]


def test_dollar_signs_and_negatives() -> None:
    text = "WHOLE FOODS\nKALE BUNCH          $2.19\nBOTTLE DEPOSIT     -$0.10\nTOTAL $2.09\n"
    parsed = parse_receipt_text(text)
    assert len(parsed.items) == 2
    assert parsed.items[0].price == 2.19
    assert parsed.items[1].price == -0.10


def test_empty_and_garbage() -> None:
    assert parse_receipt_text("").items == []
    assert parse_receipt_text("WELCOME\nTHANK YOU").items == []


def test_merchant_skips_address() -> None:
    merchant = detect_merchant(
        "512-555-0199\n07/04/2026\nCENTRAL MARKET\n202 MAIN STREET\nAUSTIN TX 78701\n"
    )
    assert merchant and "central market" in merchant.lower()
