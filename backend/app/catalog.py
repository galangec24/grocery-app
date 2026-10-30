"""Popular Philippine grocery products, so any brand can be found and added to a list.

This catalog holds names and sizes only, never prices. Government lists cover a limited
set of goods, and an invented price would be worse than none. Shoppers enter the shelf
price themselves until a retailer connects its data.
"""
import re

from . import comparison as cmp

_PRODUCTS = {
    "Junk Food": {
        "aliases": "chips snacks chichirya",
        "items": [
            ("Jack 'n Jill", "Piatos Cheese", "85g"), ("Jack 'n Jill", "Piatos Sour Cream & Onion", "85g"),
            ("Jack 'n Jill", "Piatos Roadhouse Barbecue", "85g"), ("Jack 'n Jill", "Nova Country Cheddar", "78g"),
            ("Jack 'n Jill", "Nova Homestyle BBQ", "78g"), ("Jack 'n Jill", "Chippy Barbecue", "110g"),
            ("Jack 'n Jill", "Chippy Chili & Cheese", "110g"), ("Jack 'n Jill", "Mr. Chips Nacho Cheese", "100g"),
            ("Jack 'n Jill", "V-Cut Barbecue", "60g"), ("Jack 'n Jill", "Roller Coaster Cheddar", "85g"),
            ("Jack 'n Jill", "Taquitos Chili", "85g"), ("Oishi", "Prawn Crackers", "60g"),
            ("Oishi", "Pillows Chocolate", "150g"), ("Oishi", "Pillows Ube", "150g"),
            ("Oishi", "Marty's Cracklin' Vegetarian Chicharon", "90g"), ("Oishi", "Ridges Cheddar", "85g"),
            ("Oishi", "Kirei Yummy Flakes", "65g"), ("Oishi", "Crispy Patata", "60g"),
            ("Leslie's", "Clover Chips Cheese", "85g"), ("Leslie's", "Clover Chips Barbecue", "85g"),
            ("Leslie's", "Cheezy Corn Crunch", "70g"), ("Leslie's", "Chiz Curls", "55g"),
            ("Regent", "Cheese Ring", "60g"), ("Regent", "Tortillos Barbecue", "100g"),
            ("Pringles", "Sour Cream & Onion", "110g"), ("Lay's", "Classic", "65g"), ("Doritos", "Nacho Cheese", "60g"),
            ("Nagaraya", "Cracker Nuts Original", "160g"), ("Boy Bawang", "Cornick Garlic", "100g"),
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


def _build() -> list[dict]:
    items = []
    for category, group in _PRODUCTS.items():
        for brand, product, size in group["items"]:
            name = f"{brand} {product}"
            items.append({
                "id": f"catalog:{re.sub(r'[^a-z0-9]+', '-', f'{name} {size}'.lower()).strip('-')}",
                "name": name, "brand": brand, "category": category, "size": size,
                "keywords": f"{name} {size} {category} {group['aliases']}".lower(),
            })
    return items


CATALOG = _build()


def custom_items(db) -> list[dict]:
    """Products administrators added, shaped like the built-in catalog."""
    return [
        {"id": d["_id"], "name": d["name"], "brand": d["brand"], "category": d["category"], "size": d["size"],
         "keywords": f'{d["name"]} {d["size"]} {d["category"]}'.lower()}
        for d in db.catalog_items.find().sort("name", 1)
    ]


def full(db) -> list[dict]:
    return CATALOG + custom_items(db)


def search(query: str, items: list[dict] | None = None) -> list[dict]:
    tokens = cmp.tokenize(query)
    return [item for item in (items or CATALOG) if tokens and cmp.matches(tokens, item["keywords"])]
