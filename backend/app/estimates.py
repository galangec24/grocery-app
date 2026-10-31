"""Rough guide prices, so a product with no evidence yet still shows a useful figure.

These are hand-set ballparks for a kind of product, scaled to its size. They are not
store prices. They are always labelled, always shown as a range, and give way to any
real price. They never reach store rankings, mall pages or proof checks.
"""
import re

from . import comparison as cmp

LABEL = "Rough guide, not a store price"
SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|mg|ml|cl|l|oz)\b", re.I)
UNITS = {"kg": 1000, "g": 1, "mg": 0.001, "l": 1000, "cl": 10, "ml": 1, "oz": 28}
BROAD = re.compile(r"beauty & fragrance", re.I)
SPREAD = 0.25
SCALE_POWER = 0.85  # Bigger packs cost less per gram.
LIMITS = (0.15, 8)

# (words to look for, reference size in g or ml, or None if size doesn't change the price, pesos)
# Order matters: the first match wins, so specific kinds come before general ones.
GUIDES = [
    (r"dog food|puppy|dog meal", 1500, 300), (r"cat food|kitten", 1200, 280), (r"pet milk|pet food|pouch dog|pouch cat", 130, 50),
    (r"cat litter|litter", None, 280), (r"dog shampoo|pet shampoo", 250, 180),
    (r"refrigerator|freezer", None, 18000), (r"washing machine", None, 12000), (r"microwave", None, 5000),
    (r"air fryer", None, 4500), (r"pressure cooker", None, 2800), (r"induction", None, 2200), (r"blender", None, 2000),
    (r"rice cooker", None, 1500), (r"electric fan|stand fan", None, 1400), (r"steam iron|flat iron", None, 1200),
    (r"kettle", None, 1000), (r"frying pan|cooking pot|\bpot\b|\bwok\b", None, 900), (r"baking dish", None, 600),
    (r"spoon|fork|cutlery", None, 350), (r"kitchen knife|\bknife\b", None, 350), (r"dinner plate|\bplate\b|\bbowl\b", None, 300),
    (r"food storage|food container|lunch box", None, 250), (r"water bottle|tumbler", None, 350),
    (r"ballpen|\bpen\b", None, 10), (r"pencil", None, 80), (r"notebook", None, 40), (r"marker", None, 40), (r"\bglue\b", 130, 60),
    (r"eau de (toilette|parfum)|perfume|parfum|fragrance", 75, 350), (r"cologne", 100, 120),
    (r"body spray|body mist|\bmist\b", 150, 200), (r"deodorant|roll.?on|antiperspirant", 40, 110),
    (r"conditioner.*(fabric|laundry)|fabric conditioner|fabcon", 1000, 170), (r"shampoo|conditioner|hair", 180, 150),
    (r"toothpaste|tooth paste", 150, 130), (r"mouthwash", 250, 150), (r"toothbrush", None, 70),
    (r"body wash|shower gel", 400, 220), (r"bar soap|\bsoap\b", 135, 55),
    (r"sunscreen|sunblock|spf", 50, 350), (r"serum|essence|toner", 30, 450), (r"lotion|moisturi[sz]er|\bcream\b.*(face|skin|hand|body)|face cream", 200, 220),
    (r"lipstick|lip tint|mascara|foundation|concealer|eyeliner|blush", None, 350), (r"nail polish", None, 90),
    (r"diaper|\bpants\b", None, 600), (r"baby powder", 200, 120), (r"infant|formula|enfagrow|cerelac", 1500, 1300),
    (r"detergent|laundry", 1000, 130), (r"dishwashing|dish liquid", 500, 90), (r"bleach", 1000, 70), (r"candle", None, 30),
    (r"tissue|toilet paper", None, 90), (r"insecticide|mosquito", 300, 180),
    (r"brandy|brandys|\bgin\b|\brum\b|whisky|whiskey|vodka|tequila|liqueur|\bwine\b", 750, 280), (r"\bbeer\b", 330, 60),
    (r"energy drink", 250, 60), (r"softdrink|soft drink|\bsoda\b|\bcola\b|coca.?cola|pepsi|sprite", 1500, 80),
    (r"\bjuice\b|nectar", 1000, 110), (r"mineral water|drinking water|\bwater\b", 500, 20), (r"\btea\b", 500, 40),
    (r"coffee|nescafe|kopiko", 50, 90), (r"milo|chocolate malt", 300, 130),
    (r"sardine|mackerel", 155, 26), (r"\btuna\b", 180, 60), (r"corned", 210, 70), (r"luncheon|meat loaf", 340, 190),
    (r"pancit|instant noodle|ramen|\bnoodle|\bcup noodles\b", 60, 18), (r"spaghetti|macaroni|\bpasta\b", 900, 100),
    (r"\brice\b", 1000, 55), (r"\bflour\b", 1000, 60), (r"\bsugar\b", 1000, 80), (r"\bsalt\b", 1000, 40),
    (r"evaporad|evap\b|condensad|condensed", 370, 50), (r"\bmilk\b", 1000, 115), (r"ice cream", 1500, 280),
    (r"\bcheese\b", 165, 75), (r"butter|margarine", 225, 130), (r"mayonnaise|sandwich spread", 220, 70),
    (r"ketchup", 320, 40), (r"cooking oil|\boil\b", 1000, 130), (r"\bsauce\b|vinegar|\bsoy\b", 250, 45), (r"seasoning", 8, 6),
    (r"cereal|oats|granola", 500, 180), (r"\bbread\b|loaf", 450, 70),
    (r"chocolate|\bcandy\b|biscuit|cookie|cracker|wafer", 100, 60),
    (r"\bchip|crisps|snack|piatos|\bnova\b|cornick|chicharon|nachos", 60, 35),
]
# Used when nothing more specific fits, so every catalog product has a figure.
DEPARTMENTS = [
    (r"beauty|fragrance|cosmetic|personal care|hygiene", 200), (r"pet", 200), (r"household|appliance|kitchen", 200),
    (r"school|office", 50), (r"", 80),
]
GUIDES = [(re.compile(words, re.I), base, price) for words, base, price in GUIDES]
DEPARTMENTS = [(re.compile(words, re.I), price) for words, price in DEPARTMENTS]


def _amount(text: str) -> float | None:
    found = SIZE.search(text)
    return float(found.group(1)) * UNITS[found.group(2).lower()] if found else None


def _nice(value: float) -> int:
    step = 1 if value < 50 else 5 if value < 500 else 50 if value < 5000 else 500
    return max(1, round(value / step) * step)


def _scaled(price: float, base: float | None, amount: float | None) -> float:
    if base is None or not amount:
        return price
    low, high = LIMITS
    return price * max(low, min(high, (amount / base) ** SCALE_POWER))


def guide(name: str, category: str = "", keywords: str = "") -> dict | None:
    """The ballpark for a product. Without a category, only a clear match counts."""
    amount = _amount(name)
    # The site-wide "Beauty & Fragrance" label says nothing about what a product is.
    for text in (name, BROAD.sub(" ", f"{category} {keywords}")):
        for words, base, price in GUIDES:
            if words.search(text):
                return _result(_scaled(price, base, amount))
    if not category:
        return None
    return _result(next(price for words, price in DEPARTMENTS if words.search(f"{category} {keywords}")))


def _result(value: float) -> dict:
    return {
        "price": cmp.money(_nice(value) * 100), "low": cmp.money(_nice(value * (1 - SPREAD)) * 100),
        "high": cmp.money(_nice(value * (1 + SPREAD)) * 100), "kind": "guide", "label": LABEL, "date": None,
    }
