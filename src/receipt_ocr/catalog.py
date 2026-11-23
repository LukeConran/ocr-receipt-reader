"""Local food catalog: abbreviations, categories, include/exclude.

Receipt printers truncate names (BNN, MLK 2%, ORG STRWBRY). Different
stores use different shorthand. This module maps those strings onto a
stable *food* key you can total later, and flags lines that are usually
not groceries (alcohol, clothes, appliances, household, pharmacy).

Defaults live in code. Personal aliases go in ``data/catalog.json`` and
win over the defaults — the review UI writes an alias when you rename a
food.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from receipt_ocr.config import PROJECT_ROOT

USER_CATALOG_PATH = PROJECT_ROOT / "data" / "catalog.json"

# Tokens we strip before matching a food name.
NOISE_TOKENS = {
    "org",
    "organic",
    "whl",
    "whole",
    "frzn",
    "frozen",
    "frsh",
    "fresh",
    "bnls",
    "boneless",
    "sknls",
    "skinless",
    "sel",
    "select",
    "essentials",
    "store",
    "brand",
    "pk",
    "pack",
    "ct",
    "count",
    "lb",
    "lbs",
    "oz",
    "gal",
    "gallon",
    "half",
    "ea",
    "each",
    "lg",
    "large",
    "sm",
    "small",
    "med",
    "md",
    "medium",
    "nr",
    "natures",
    "nat",
    "rstd",
    "roasted",
    "grd",
    "ground",
    "slcd",
    "sliced",
    "chunk",
    "chunks",
    "piece",
    "pieces",
    "extra",
    "virgin",
    "reduced",
    "fat",
    "free",
    "low",
    "2%",
    "1%",
    "skim",
    "nonfat",
    "ss",
    "size",
    "value",
    "family",
    "club",
    "premium",
    "grade",
    "choice",
    "a",
    "the",
    "and",
    "with",
    "in",
    "of",
    "heb",
    "kroger",
    "great",
    "value",
    "marketside",
    "signature",
    "private",
    "selection",
    "trader",
    "joes",
    "joe's",
}

# Canonical food → extra aliases (beyond the name itself).
FOOD_ALIASES: dict[str, tuple[str, ...]] = {
    "Apple": ("apples", "apl", "honeycrisp", "gala", "fuji"),
    "Avocado": ("avocados", "avoc", "hass avocado", "hass"),
    "Banana": ("bananas", "bnn", "bnna"),
    "Blueberry": ("blueberries", "blubry", "blu berry"),
    "Strawberry": ("strawberries", "strwbry", "strwberry", "strawbery"),
    "Grape": ("grapes", "grp"),
    "Orange": ("oranges", "navel"),
    "Lemon": ("lemons", "lmn"),
    "Lime": ("limes",),
    "Berry": ("berries", "mixed berry"),
    "Melon": ("watermelon", "cantaloupe", "honeydew"),
    "Peach": ("peaches",),
    "Pear": ("pears",),
    "Pineapple": ("pineappl", "pnappl"),
    "Mango": ("mangos", "mangoes"),
    "Tomato": ("tomatoes", "tmt", "roma", "grape tomato"),
    "Potato": ("potatoes", "poto", "russet", "yukon"),
    "Onion": ("onions", "onn"),
    "Garlic": ("garlc",),
    "Carrot": ("carrots", "crrt"),
    "Celery": ("clry",),
    "Broccoli": ("broc", "brocolli"),
    "Spinach": ("spnch",),
    "Lettuce": ("lttc", "romaine", "iceberg"),
    "Kale": ("kale bunch",),
    "Cucumber": ("cucmbr", "cuke"),
    "Pepper": ("peppers", "bell pepper", "jalapeno", "jalapeño"),
    "Mushroom": ("mushrooms", "mshrm"),
    "Corn": ("sweet corn",),
    "Cabbage": ("cbbg",),
    "Zucchini": ("squash",),
    "Milk": ("mlk", "whole milk", "2% milk", "skim milk", "alfredo milk"),
    "Oat milk": ("oatmlk", "oatly"),
    "Almond milk": ("almd mlk",),
    "Cream": ("half & half", "half and half", "h&h", "heavy cream"),
    "Butter": ("btr", "bttr"),
    "Cheese": ("chs", "cheddar", "mozzarella", "swiss", "colby", "provolone"),
    "Yogurt": ("ygrt", "yog", "chobani", "fage"),
    "Egg": ("eggs", "egg", "cage free eggs"),
    "Chicken": ("chkn", "chcken", "poultry"),
    "Turkey": ("turky", "grnd turkey"),
    "Beef": ("steak", "ground beef", "grnd beef", "chuck", "sirloin"),
    "Pork": ("bacon", "ham", "sausage", "pork chop"),
    "Bacon": ("bcn",),
    "Fish": ("salmon", "tilapia", "cod", "tuna steak"),
    "Tuna": ("tuna can", "canned tuna"),
    "Shrimp": ("shrmp",),
    "Tofu": ("bean curd",),
    "Bread": ("brd", "sourdough", "baguette", "loaf", "wheat bread"),
    "Tortilla": ("tortillas", "tort",),
    "Rice": ("basmati", "jasmine rice"),
    "Pasta": ("spaghetti", "macaroni", "penne", "noodle", "noodles"),
    "Cereal": ("cheerios", "oats cereal"),
    "Oat": ("oatmeal", "rolled oats", "oats"),
    "Bean": ("beans", "black beans", "pinto", "chickpea", "garbanzo", "lentil"),
    "Peanut butter": ("pnutspr", "pnut btr", "pb"),
    "Jam": ("jelly", "preserves"),
    "Honey": ("hny",),
    "Oil": ("olive oil", "evoo", "canola", "veg oil", "vegetable oil"),
    "Vinegar": ("vngr",),
    "Sauce": ("salsa", "marinara", "hot sauce", "soy sauce", "ketchup", "mustard", "mayo", "mayonnaise"),
    "Soup": ("broth", "stock"),
    "Snack": ("crackers", "chips", "pretzel", "popcorn"),
    "Nut": ("almonds", "walnuts", "cashews", "peanuts", "pistachio"),
    "Chocolate": ("cocoa",),
    "Coffee": ("k-cup", "kcup", "espresso"),
    "Tea": ("teabag",),
    "Juice": ("oj", "orange juice", "apple juice"),
    "Water": ("sparkling water", "topo chico", "la croix"),
    "Soda": ("cola", "coke", "pepsi", "sprite", "dr pepper", "root beer", "mountain dew"),
    "Taco": ("carne asada taco", "pastor taco", "street taco"),
    "Burger": ("cheeseburger", "hamburger"),
    "Pizza": ("pepperoni pizza",),
    "Sandwich": ("sub", "hoagie", "wrap"),
    "Salad": ("caesar",),
    "Soup cup": ("chili cup",),
    "Fries": ("frys", "french fry"),
    "Chips and salsa": ("chips & salsa", "chips and salsa"),
    "Guacamole": ("guac",),
    "Horchata": (),
}

# Non-food (or out-of-scope) categories. First matching list wins.
EXCLUDE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "alcohol": (
        "beer",
        "ipa",
        "lager",
        "ale",
        "stout",
        "pilsner",
        "wine",
        "cabernet",
        "chardonnay",
        "pinot",
        "merlot",
        "prosecco",
        "champagne",
        "vodka",
        "whiskey",
        "whisky",
        "bourbon",
        "scotch",
        "rum",
        "gin",
        "tequila",
        "mezcal",
        "brandy",
        "cognac",
        "liqueur",
        "liquor",
        "malt liquor",
        "hard seltzer",
        "white claw",
        "truly",
        "seltzer alc",
        "michelob",
        "bud light",
        "coors",
        "modelo",
        "corona",
        "heineken",
        "guinness",
        "hard cider",
        "moonshine",
    ),
    "household": (
        "paper towel",
        "paper towels",
        "toilet paper",
        "bath tissue",
        "tissue",
        "trash bag",
        "garbage bag",
        "ziploc",
        "aluminum foil",
        "plastic wrap",
        "parchment",
        "detergent",
        "laundry",
        "fabric softener",
        "bleach",
        "clorox",
        "lysol",
        "windex",
        "cleaner",
        "disinfectant",
        "sponge",
        "dish soap",
        "dawn",
        "cascade",
        "swiffer",
        "mop",
        "broom",
        "glade",
        "air freshener",
        "candle",
        "light bulb",
        "battery",
        "batteries",
        "trash can",
    ),
    "appliance": (
        "air fryer",
        "toaster",
        "blender",
        "microwave",
        "slow cooker",
        "instapot",
        "instant pot",
        "mixer",
        "coffee maker",
        "kettle",
        "skillet",
        "frying pan",
        "saucepan",
        "baking sheet",
        "cutting board",
        "knife set",
        "utensil",
        "plate set",
        "glassware",
        "tupperware",
        "food processor",
        "vacuum",
    ),
    "clothing": (
        "shirt",
        "t-shirt",
        "hoodie",
        "sweatshirt",
        "jeans",
        "pants",
        "shorts",
        "socks",
        "underwear",
        "bra",
        "jacket",
        "coat",
        "hat",
        "baseball cap",
        "shoes",
        "sneakers",
        "sandals",
        "boots",
        "belt",
        "gloves",
    ),
    "pharmacy": (
        "ibuprofen",
        "advil",
        "tylenol",
        "acetaminophen",
        "aleve",
        "band-aid",
        "bandaid",
        "bandage",
        "antacid",
        "tums",
        "vitamin",
        "supplement",
        "shampoo",
        "conditioner",
        "toothpaste",
        "toothbrush",
        "deodorant",
        "razor",
        "lotion",
        "sunscreen",
        "tampon",
        "diaper",
        "wipes",
        "neosporin",
        "cough",
        "nyquil",
        "dayquil",
    ),
    "pet": (
        "dog food",
        "cat food",
        "pet food",
        "litter",
        "kibble",
        "puppy",
        "chew toy",
    ),
    "other": (
        "gift card",
        "reusable bag",
        "shopping bag",
        "plastic bag",
        "magazine",
        "lottery",
        "phone card",
        "postage",
        "stamps",
        "charcoal",
        "lighter fluid",
        "propane",
        "firewood",
        "ice bag",
        "solo cup",
        "paper plate",
        "plastic fork",
        "napkin pack",
    ),
}

RESTAURANT_HINTS = (
    "taco",
    "grill",
    "cafe",
    "café",
    "coffee",
    "pizza",
    "sushi",
    "burger",
    "diner",
    "kitchen",
    "bistro",
    "bar &",
    "cantina",
    "taqueria",
    "noodle",
    "pho",
    "bbq",
    "steakhouse",
    "pizz",
    "wings",
    "bakery",
    "donut",
    "ihop",
    "chipotle",
    "mcdonald",
    "whataburger",
    "chick-fil",
    "wendy",
    "panda express",
)

GROCERY_HINTS = (
    "heb",
    "kroger",
    "walmart",
    "target",
    "aldi",
    "costco",
    "sam's",
    "sams club",
    "trader joe",
    "whole foods",
    "central market",
    "food lion",
    "safeway",
    "publix",
    "sprouts",
    "market",
    "grocery",
    "supermarket",
)

# Grocery staples are often sales-tax exempt in Texas; these usually are not.
TAXABLE_FOOD_HINTS = (
    "soda",
    "cola",
    "coke",
    "pepsi",
    "candy",
    "gum",
    "energy drink",
    "gatorade",
    "powerade",
    "prepared",
    "hot bar",
    "deli sandwich",
    "rotisserie",
    "sushi tray",
    "fountain",
)


def _norm(text: str) -> str:
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9%]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> list[str]:
    return [tok for tok in _norm(text).split() if tok]


def _skeleton(word: str) -> str:
    """Consonant skeleton used by many POS abbreviations (banana → bnn)."""
    letters = re.sub(r"[^a-z]", "", word.lower())
    if len(letters) < 3:
        return letters
    return letters[0] + re.sub(r"[aeiou]", "", letters[1:])


def _contains_any(haystack: str, needles: tuple[str, ...] | list[str]) -> str | None:
    for needle in needles:
        if not needle:
            continue
        if " " in needle:
            if needle in haystack:
                return needle
            continue
        if re.search(rf"\b{re.escape(needle)}\b", haystack):
            return needle
    return None


@dataclass
class UserCatalog:
    aliases: dict[str, str] = field(default_factory=dict)
    exclude_contains: list[str] = field(default_factory=list)
    include_contains: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> UserCatalog:
        path = path or USER_CATALOG_PATH
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        aliases = { _norm(k): str(v).strip() for k, v in (data.get("aliases") or {}).items() if str(v).strip() }
        return cls(
            aliases=aliases,
            exclude_contains=[_norm(x) for x in data.get("exclude_contains") or [] if str(x).strip()],
            include_contains=[_norm(x) for x in data.get("include_contains") or [] if str(x).strip()],
        )

    def save(self, path: Path | None = None) -> None:
        path = path or USER_CATALOG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "aliases": self.aliases,
            "exclude_contains": self.exclude_contains,
            "include_contains": self.include_contains,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def remember_alias(self, raw_item: str, food: str, path: Path | None = None) -> None:
        key = _norm(raw_item)
        food = food.strip()
        if not key or not food:
            return
        if self.aliases.get(key) == food:
            return
        self.aliases[key] = food
        self.save(path)


class Catalog:
    def __init__(self, user: UserCatalog | None = None) -> None:
        self.user = user or UserCatalog()
        self._food_phrases: list[tuple[str, str]] = []  # (normalized phrase, canonical)
        self._food_skeletons: dict[str, str] = {}
        self._build_indexes()

    def _build_indexes(self) -> None:
        for canonical, extras in FOOD_ALIASES.items():
            phrases = {canonical.lower(), *extras}
            phrases.update(canonical.lower() + "s" for _ in [0] if not canonical.lower().endswith("s"))
            for phrase in phrases:
                norm = _norm(phrase)
                if not norm:
                    continue
                self._food_phrases.append((norm, canonical))
                for tok in norm.split():
                    sk = _skeleton(tok)
                    if len(sk) >= 3 and sk not in self._food_skeletons:
                        self._food_skeletons[sk] = canonical
        self._food_phrases.sort(key=lambda pair: len(pair[0]), reverse=True)

    def merchant_kind(self, merchant: str | None) -> str:
        name = _norm(merchant or "")
        if _contains_any(name, GROCERY_HINTS):
            return "grocery"
        if _contains_any(name, RESTAURANT_HINTS):
            return "restaurant"
        return "unknown"

    def classify(self, raw_item: str) -> tuple[str, str, bool]:
        """Return (canonical_food, category, include)."""
        norm = _norm(raw_item)
        if not norm:
            return "", "other", False

        if _contains_any(norm, tuple(self.user.include_contains)):
            food = self.canonical_food(raw_item) or raw_item.strip()
            return food, "food", True
        if _contains_any(norm, tuple(self.user.exclude_contains)):
            return self.canonical_food(raw_item) or raw_item.strip(), "other", False

        food = self.canonical_food(raw_item)
        excluded_category = None
        for category, needles in EXCLUDE_CATEGORIES.items():
            if _contains_any(norm, needles):
                excluded_category = category
                break

        if food and excluded_category == "alcohol" and food in {"Vinegar", "Sauce", "Juice"}:
            return food, "food", True
        if food and not excluded_category:
            return food, "food", True
        if food and excluded_category:
            # A known food word plus an exclude word: keep the food (review can uncheck).
            return food, "food", True
        if excluded_category:
            return raw_item.strip(), excluded_category, False
        # Unknown merchandise: include and let the review step uncheck it.
        return raw_item.strip(), "unknown", True

    def canonical_food(self, raw_item: str) -> str:
        norm = _norm(raw_item)
        if not norm:
            return ""
        if norm in self.user.aliases:
            return self.user.aliases[norm]
        # User aliases may match a shorter key inside the line.
        for key, food in sorted(self.user.aliases.items(), key=lambda kv: len(kv[0]), reverse=True):
            if key and key in norm:
                return food
        for phrase, canonical in self._food_phrases:
            if phrase == norm or f" {phrase} " in f" {norm} ":
                return canonical
        meaningful = [tok for tok in _tokens(raw_item) if tok not in NOISE_TOKENS and not tok.isdigit()]
        for tok in meaningful:
            sk = _skeleton(tok)
            if sk in self._food_skeletons and len(sk) >= 3:
                return self._food_skeletons[sk]
        # Last pass: any token equal to a food word.
        for tok in meaningful:
            for phrase, canonical in self._food_phrases:
                if phrase == tok:
                    return canonical
        return ""

    def infer_taxable(self, raw_item: str, category: str, merchant_kind: str, flagged: bool | None) -> bool:
        if flagged is not None:
            return flagged
        norm = _norm(raw_item)
        if category in {"alcohol", "household", "appliance", "clothing", "pharmacy", "pet", "other"}:
            return True
        if _contains_any(norm, TAXABLE_FOOD_HINTS) or category == "soda":
            return True
        if merchant_kind == "restaurant":
            return True
        if merchant_kind == "grocery":
            return False
        # Unknown store: tax unknown food only if it looks prepared/restaurant-y.
        return bool(_contains_any(norm, TAXABLE_FOOD_HINTS + RESTAURANT_HINTS))


def default_catalog() -> Catalog:
    return Catalog(UserCatalog.load())
