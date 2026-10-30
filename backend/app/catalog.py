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


def search(query: str) -> list[dict]:
    tokens = cmp.tokenize(query)
    return [item for item in CATALOG if tokens and cmp.matches(tokens, item["keywords"])]
