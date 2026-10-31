"""The product catalog, stored in the database.

Most products arrive from the open product databases (see sources/open_data.py).
Administrators can add more, for example when a mall partners with the app. The list
below only seeds popular local items that those databases may be missing. The catalog
holds names and sizes. A product with no real price yet shows a labelled rough guide.
"""
import re

from . import comparison as cmp
from . import estimates, search

_PRODUCTS = {
    "Junk Food": {
        "aliases": "chips snacks chichirya",
        "items": [
            ("Jack 'n Jill", "Piatos Cheese", "40g/85g"), ("Jack 'n Jill", "Piatos Sour Cream & Onion", "40g/85g"),
            ("Jack 'n Jill", "Piatos Roadhouse Barbecue", "40g/85g"), ("Jack 'n Jill", "Nova Country Cheddar", "40g/78g"),
            ("Jack 'n Jill", "Nova Homestyle BBQ", "40g/78g"), ("Jack 'n Jill", "Chippy Barbecue", "27g/110g"),
            ("Jack 'n Jill", "Chippy Chili & Cheese", "27g/110g"), ("Jack 'n Jill", "Mr. Chips Nacho Cheese", "25g/100g"),
            ("Jack 'n Jill", "V-Cut Barbecue", "25g/60g"), ("Jack 'n Jill", "Roller Coaster Cheddar", "30g/85g"),
            ("Jack 'n Jill", "Taquitos Chili", "25g/85g"), ("Oishi", "Prawn Crackers", "25g/60g"),
            ("Oishi", "Pillows Chocolate", "38g/150g"), ("Oishi", "Pillows Ube", "38g/150g"),
            ("Oishi", "Marty's Cracklin' Vegetarian Chicharon", "27g/90g"), ("Oishi", "Ridges Cheddar", "25g/85g"),
            ("Oishi", "Kirei Yummy Flakes", "24g/65g"), ("Oishi", "Crispy Patata", "22g/60g"),
            ("Leslie's", "Clover Chips Cheese", "30g/85g"), ("Leslie's", "Clover Chips Barbecue", "30g/85g"),
            ("Leslie's", "Cheezy Corn Crunch", "30g/70g"), ("Leslie's", "Chiz Curls", "28g/55g"),
            ("Regent", "Cheese Ring", "30g/60g"), ("Regent", "Tortillos Barbecue", "30g/100g"),
            ("Pringles", "Sour Cream & Onion", "42g/110g"), ("Lay's", "Classic", "25g/65g"), ("Doritos", "Nacho Cheese", "30g/60g"),
            ("Nagaraya", "Cracker Nuts Original", "40g/160g"), ("Boy Bawang", "Cornick Garlic", "30g/100g"),
        ],
    },
    "Canned Sardines": {
        "aliases": "canned fish",
        "items": [
            ("Mega", "Sardines in Tomato Sauce", "155g"), ("Mega", "Sardines in Tomato Sauce with Chili", "155g"),
            ("Mega", "Sardines Easy Open Can", "155g"), ("Mega", "Mackerel in Tomato Sauce", "155g"),
            ("Ligo", "Sardines in Tomato Sauce", "155g"), ("Ligo", "Sardines Chili", "155g"),
            ("Master", "Sardines in Tomato Sauce", "155g"), ("Hakone", "Sardines in Tomato Sauce", "155g"),
        ],
    },
    "Canned Goods": {
        "aliases": "tuna meat",
        "items": [
            ("Century", "Tuna Flakes in Oil", "180g"), ("Century", "Tuna Flakes Hot & Spicy", "180g"),
            ("Century", "Tuna Hot & Spicy", "155g"), ("San Marino", "Corned Tuna", "180g"),
            ("Purefoods", "Corned Beef", "210g"), ("Libby's", "Corned Beef", "340g"),
            ("Spam", "Classic Luncheon Meat", "340g"), ("Ma Ling", "Luncheon Meat", "340g"),
        ],
    },
    "Noodles & Pasta": {
        "aliases": "instant noodles pancit",
        "items": [
            ("Lucky Me!", "Pancit Canton Original", "60g"), ("Lucky Me!", "Pancit Canton Chilimansi", "60g"),
            ("Lucky Me!", "Pancit Canton Extra Hot", "60g"), ("Lucky Me!", "Supreme La Paz Batchoy", "70g"),
            ("Nissin", "Cup Noodles Seafood", "60g"), ("Nissin", "Yakisoba Spicy", "60g"),
            ("Payless", "Xtra Big Pancit Canton", "130g"), ("Royal", "Spaghetti", "1kg"),
            ("Fiesta", "Spaghetti", "900g"),
        ],
    },
    "Beverages": {
        "aliases": "drinks softdrinks juice coffee",
        "items": [
            ("Coca-Cola", "Regular", "1.5L"), ("Coca-Cola", "Zero Sugar", "1.5L"), ("Pepsi", "Regular", "1.5L"),
            ("Royal", "Tru-Orange", "1.5L"), ("Sprite", "Regular", "1.5L"), ("Mountain Dew", "Regular", "1.5L"),
            ("C2", "Green Tea Apple", "500ml"), ("Zesto", "Orange", "200ml"), ("Tang", "Orange", "25g"),
            ("Milo", "Chocolate Malt Drink", "300g"), ("Nescafe", "Classic", "50g"), ("Kopiko", "Brown Coffee", "27.5g"),
            ("Red Bull", "Energy Drink", "250ml"), ("Cobra", "Energy Drink", "350ml"), ("Gatorade", "Blue Bolt", "500ml"),
        ],
    },
    "Dairy & Breakfast": {
        "aliases": "milk cereal",
        "items": [
            ("Alaska", "Evaporada", "370ml"), ("Alaska", "Condensada", "300ml"), ("Carnation", "Evap", "370ml"),
            ("Nestle", "Fresh Milk", "1L"), ("Selecta", "Ice Cream Vanilla", "1.5L"), ("Eden", "Cheese", "165g"),
            ("Magnolia", "Butter", "225g"), ("Lady's Choice", "Sandwich Spread", "220ml"),
            ("Nestle", "Koko Krunch", "330g"), ("Quaker", "Instant Oats", "800g"),
        ],
    },
    "Condiments": {
        "aliases": "sauce seasoning",
        "items": [
            ("UFC", "Banana Ketchup", "320g"), ("Del Monte", "Tomato Sauce", "250g"), ("Del Monte", "Spaghetti Sauce", "1kg"),
            ("Mang Tomas", "All Purpose Sauce", "325g"), ("Knorr", "Liquid Seasoning", "250ml"),
            ("Magic Sarap", "Seasoning Mix", "8g"), ("Maggi", "Savor", "130ml"), ("Lady's Choice", "Mayonnaise", "220ml"),
        ],
    },
    "Kitchenware & Utensils": {
        "aliases": "utensils kitchen cookware plates spoon fork pot pan",
        "items": [
            ("Tramontina", "Stainless Spoon and Fork Set", "12 pcs"), ("Tefal", "Non-Stick Frying Pan", "24 cm"),
            ("Tefal", "Non-Stick Cooking Pot", "20 cm"), ("Zebra", "Stainless Cooking Pot", "22 cm"),
            ("Lock & Lock", "Food Storage Container", "1L"), ("Corelle", "Dinner Plate", "26 cm"),
            ("Pyrex", "Glass Baking Dish", "2L"), ("Tupperware", "Water Bottle", "1L"),
            ("Masflex", "Pressure Cooker", "6L"), ("Oxo", "Kitchen Knife", "20 cm"),
        ],
    },
    "Appliances": {
        "aliases": "electronics home appliance",
        "items": [
            ("Hanabishi", "Electric Stand Fan", "16 inch"), ("Asahi", "Electric Fan", "16 inch"),
            ("Kyowa", "Rice Cooker", "1.8L"), ("Imarflex", "Induction Cooker", "1 unit"),
            ("Panasonic", "Steam Iron", "1 unit"), ("Oster", "Blender", "1.25L"),
            ("Samsung", "Microwave Oven", "23L"), ("American Home", "Electric Kettle", "1.7L"),
            ("Condura", "Inverter Refrigerator", "7 cu ft"), ("Philips", "Air Fryer", "4.1L"),
        ],
    },
    "Pet Supplies": {
        "aliases": "pets animal dog cat puppy kitten feeds",
        "items": [
            ("Pedigree", "Adult Beef Dog Food", "1.5kg"), ("Pedigree", "Puppy Chicken Dog Food", "1.3kg"),
            ("Pedigree", "Beef Pouch Dog Food", "130g"), ("Vitality", "Value Meal Dog Food", "3kg"),
            ("Royal Canin", "Medium Adult Dog Food", "4kg"), ("Whiskas", "Ocean Fish Cat Food", "1.2kg"),
            ("Whiskas", "Tuna Cat Food Pouch", "85g"), ("Friskies", "Seafood Sensations Cat Food", "1.1kg"),
            ("Royal Canin", "Indoor Cat Food", "2kg"), ("Cosi", "Pet Milk", "200ml"),
            ("Bioline", "Dog Shampoo", "250ml"), ("Pet Republic", "Cat Litter", "10L"),
        ],
    },
    "Perfume & Fragrance": {
        "aliases": "cologne scent deodorant body spray",
        "items": [
            ("Bench", "Daily Scent Eau de Toilette", "75ml"), ("Bench", "Atlantis Body Spray", "150ml"),
            ("Penshoppe", "Eau de Toilette", "75ml"), ("Axe", "Dark Temptation Body Spray", "150ml"),
            ("Dove", "Roll-On Deodorant", "40ml"), ("Rexona", "Roll-On Deodorant", "40ml"),
            ("Johnson's", "Baby Cologne", "100ml"), ("Enchanteur", "Charming Body Mist", "75ml"),
            ("Avon", "Far Away Eau de Parfum", "50ml"),
        ],
    },
    "Baby Needs": {
        "aliases": "diapers infant formula",
        "items": [
            ("Pampers", "Baby Dry Diapers Medium", "40 pcs"), ("Huggies", "Dry Pants Medium", "32 pcs"),
            ("EQ", "Dry Diapers Medium", "40 pcs"), ("Cerelac", "Rice and Soy Infant Cereal", "120g"),
            ("Enfagrow", "A+ Powdered Milk", "1.5kg"), ("Johnson's", "Baby Powder", "200g"),
        ],
    },
    "School & Office": {
        "aliases": "supplies stationery",
        "items": [
            ("Panda", "Ballpen Black", "1 pc"), ("Mongol", "Pencil No. 2", "12 pcs"), ("Veco", "Spiral Notebook", "80 leaves"),
            ("Pilot", "Permanent Marker", "1 pc"), ("Elmer's", "Glue All", "130g"),
        ],
    },
    "Personal Care & Household": {
        "aliases": "soap shampoo toiletries",
        "items": [
            ("Palmolive", "Shampoo", "180ml"), ("Sunsilk", "Shampoo", "180ml"), ("Colgate", "Toothpaste", "150g"),
            ("Safeguard", "Bar Soap", "135g"), ("Ariel", "Detergent Powder", "1kg"), ("Tide", "Detergent Powder", "1kg"),
            ("Downy", "Fabric Conditioner", "1L"), ("Joy", "Dishwashing Liquid", "500ml"), ("Zonrox", "Bleach", "1L"),
        ],
    },
}


VARIANTS = {2: ["Small", "Large"], 3: ["Small", "Medium", "Large"]}


def _build() -> list[dict]:
    items = []
    for category, group in _PRODUCTS.items():
        for brand, product, sizes in group["items"]:
            options = sizes.split("/")
            for index, size in enumerate(options):
                name = f"{brand} {product}"
                variant = VARIANTS[len(options)][index] if len(options) > 1 else ""
                items.append({
                    "id": f"catalog:{re.sub(r'[^a-z0-9]+', '-', f'{name} {size}'.lower()).strip('-')}",
                    "name": name, "brand": brand, "category": category, "size": size, "variant": variant,
                    "keywords": f"{name} {size} {variant} {category} {group['aliases']}".lower(),
                })
    return items


STARTER = _build()


def seed(db) -> None:
    """Adds starter items once. Anything an administrator removed stays removed."""
    if db.catalog_items.find_one({"source": "starter"}):
        return
    for item in STARTER:
        db.catalog_items.replace_one(
            {"_id": item["id"]},
            {"_id": item["id"], **{k: v for k, v in item.items() if k != "id"}, "source": "starter", "status": "active"},
            upsert=True,
        )


def _public(doc: dict) -> dict:
    return {
        "id": doc["_id"], "name": doc["name"], "brand": doc["brand"], "category": doc["category"],
        "size": doc["size"], "variant": doc.get("variant", ""), "barcode": doc.get("barcode"),
        "image_url": doc.get("image_url"), "source": doc.get("source"), "keywords": doc["keywords"],
        "auto_price": doc.get("auto_price") or estimates.guide(f'{doc["name"]} {doc["size"]}', doc["category"], doc["keywords"]),
    }


def find(db, query: str, limit: int = 50, offset: int = 0) -> list[dict]:
    criteria = search.catalog_criteria(search.expand(db, query))
    rows = db.catalog_items.find(criteria).sort("name", 1).skip(offset).limit(limit)
    return [_public(doc) for doc in rows]


def closest(db, query: str) -> list[dict]:
    """The single best match, judged by the product's name rather than the alphabet."""
    groups = search.expand(db, query)
    rows = find(db, query, 80)
    return sorted(rows, key=lambda item: -search.score(groups, f'{item["name"]} {item["size"]}'))[:1]


def count(db, query: str) -> int:
    return db.catalog_items.count_documents(search.catalog_criteria(search.expand(db, query)))


def custom_items(db) -> list[dict]:
    """Products administrators added."""
    return [_public(d) for d in db.catalog_items.find({"source": "admin", "status": "active"}).sort("name", 1)]
