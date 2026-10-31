"""Search that understands what shoppers mean.

Words are expanded with Tagalog and everyday synonyms, spelling slips are corrected
against the words we actually stock, and results are ranked by how well they fit. This
is matching on meaning by rules, not a language model, so it needs no paid service.
"""
import difflib
import re
import time
from statistics import median

from pymongo.database import Database

from . import comparison as cmp

SYNONYMS = {
    "bigas": ["rice"], "kanin": ["rice"], "itlog": ["egg"], "gatas": ["milk"], "tinapay": ["bread", "pandesal"],
    "kape": ["coffee"], "asukal": ["sugar"], "asin": ["salt"], "mantika": ["cooking oil", "oil"], "suka": ["vinegar"],
    "toyo": ["soy sauce"], "patis": ["fish sauce", "patis"], "manok": ["chicken"], "baboy": ["pork"], "baka": ["beef"],
    "isda": ["fish", "bangus", "tilapia"], "bangus": ["milkfish", "bangus"], "gulay": ["vegetable"], "prutas": ["fruit"],
    "sibuyas": ["onion"], "bawang": ["garlic"], "kamatis": ["tomato"], "luya": ["ginger"], "saging": ["banana"],
    "mangga": ["mango"], "sabon": ["soap"], "tubig": ["water"], "tsitsirya": ["snack", "chips"], "chichirya": ["snack", "chips"],
    "sitsirya": ["snack", "chips"], "aso": ["dog"], "pusa": ["cat"], "pabango": ["perfume", "cologne"], "lampin": ["diaper"],
    "softdrinks": ["soda", "cola"], "softdrink": ["soda", "cola"], "softdrink's": ["soda"], "noodles": ["noodle", "pancit", "mami"],
    "pasta": ["spaghetti", "macaroni"], "chips": ["chip", "crisps", "snack"], "snacks": ["snack", "chips"],
    "sardines": ["sardine", "sardinas"], "sardinas": ["sardine"], "cologne": ["perfume"], "perfume": ["cologne", "fragrance"],
    "diapers": ["diaper"], "appliance": ["electronics"], "detergent": ["laundry", "soap"],
}
PRODUCT_TYPES = [
    "corned beef", "meat loaf", "beef loaf", "luncheon meat", "soy sauce", "instant noodles", "sardines", "noodles", "mami",
    "coffee", "condensed milk", "evaporated milk", "powdered milk", "milk", "vinegar", "patis", "water", "soap",
    "detergent", "salt", "bread", "candle",
]
VOCABULARY_TTL_SECONDS = 600
SIZE = re.compile(r"\d+(?:\.\d+)?\s?(?:kg|g|ml|l)\b", re.I)
_vocabulary: tuple[float, list[str]] = (0, [])


def reset_vocabulary() -> None:
    global _vocabulary
    _vocabulary = (0, [])


def vocabulary(db: Database) -> list[str]:
    global _vocabulary
    loaded, words = _vocabulary
    if time.monotonic() - loaded < VOCABULARY_TTL_SECONDS and words:
        return words
    found: set[str] = set(SYNONYMS)
    for doc in db.catalog_items.find({"status": "active"}, {"name": 1}).limit(15000):
        found.update(w for w in cmp.tokenize(doc["name"]) if len(w) >= 4 and w.isalpha())
    for doc in db.market_prices.find({}, {"commodity": 1}).limit(3000):
        found.update(w for w in cmp.tokenize(doc["commodity"]) if len(w) >= 4 and w.isalpha())
    _vocabulary = (time.monotonic(), sorted(found))
    return _vocabulary[1]


def expand(db: Database, query: str) -> list[list[str]]:
    """One list of acceptable alternatives for each word the shopper typed."""
    words = vocabulary(db)
    known = set(words)
    groups = []
    for token in cmp.tokenize(query):
        options = [token]
        if token not in known and len(token) >= 4 and token.isalpha():
            options += difflib.get_close_matches(token, words, n=2, cutoff=0.78)
        for word in list(options):
            options += SYNONYMS.get(word, [])
        groups.append(list(dict.fromkeys(options)))
    return groups


def _hit(option: str, text: str) -> bool:
    return option in text or (option.endswith("s") and option[:-1] in text)


def fits(groups: list[list[str]], text: str) -> bool:
    return all(any(_hit(option, text) for option in group) for group in groups)


def score(groups: list[list[str]], name: str) -> int:
    """Higher is better: words in the name beat words only in the category."""
    name = name.lower()
    words = set(cmp.tokenize(name))
    points = 0
    for group in groups:
        if any(o in words or f"{o}s" in words or o.rstrip("s") in words for o in group):
            points += 3  # A whole word, so "egg" outranks "eggplant".
        elif any(_hit(o, name) for o in group):
            points += 2
    if groups and any(name.startswith(o) for o in groups[0]):
        points += 1
    return points


def catalog_criteria(groups: list[list[str]]) -> dict:
    clauses: list[dict] = [{"status": "active"}]
    for group in groups:
        words = [re.escape(o[:-1] if o.endswith("s") and len(o) > 3 else o) for o in group]
        clauses.append({"keywords": {"$regex": "|".join(words)}})
    return {"$and": clauses}


def estimate(rows: list[dict], query: str, name: str = "") -> dict | None:
    """The typical official price of the same kind of product, ideally the same size."""
    text = f"{query} {name}".lower()
    kind = next((k for k in PRODUCT_TYPES if k in text or k.rstrip("s") in text), None)
    if kind is None:
        return None
    similar = [
        r for r in rows
        if r["kind"] == "srp" and (kind in f'{r["commodity"]} {r["category"]}'.lower() or kind.rstrip("s") in f'{r["commodity"]} {r["category"]}'.lower())
    ]
    size = SIZE.search(text)
    wanted = size.group(0).replace(" ", "").lower() if size else None
    same_size = [r for r in similar if wanted and r["specification"].replace(" ", "").lower() == wanted]
    pool = same_size or (similar if wanted is None else [])
    if len(pool) < 2:
        return None
    return {"price": round(median(r["price"] for r in pool), 2), "kind": kind, "count": len(pool)}
