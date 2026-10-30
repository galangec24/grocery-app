"""Department of Agriculture Daily Price Index for the National Capital Region.

Prices are prevailing retail prices: the average seen in the DA's covered wet markets,
not a suggested or supermarket price.
"""
import io
import re
from datetime import date, datetime

import pdfplumber

LISTING_URL = "https://www.da.gov.ph/price-monitoring/"
LINK = re.compile(r"https://www\.da\.gov\.ph/wp-content/uploads/[\w/.-]+\.pdf", re.I)
TITLE_DATE = re.compile(r"\(\w+,\s*([A-Z][a-z]+ \d{1,2}, \d{4})\)")
PRICE = re.compile(r"\d{1,5}\.\d{2}|n/a", re.I)
MIN_PRICED_ROWS = 100


def daily_report_urls(listing_html: str) -> list[str]:
    """Daily reports, newest first as the DA lists them."""
    urls = dict.fromkeys(m.group(0) for m in LINK.finditer(listing_html))
    return [
        u for u in urls
        if re.search(r"Daily-Price-Index|DPI", u, re.I) and not re.search(r"Weekly|Cigarette", u, re.I)
    ]


def _unit(commodity: str) -> str:
    name = commodity.lower()
    if name.startswith("chicken egg"):
        return "piece"
    if name.startswith("cooking oil"):
        return "bottle"  # Sized by bottle: 350 ml lists at about 40% of 1 L.
    return "kg"


def _clean(cell: str | None) -> str:
    return " ".join((cell or "").split())


def parse_report(pdf_bytes: bytes) -> dict:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        first_page = pdf.pages[0].extract_text() or ""
        tables = [table.extract() for page in pdf.pages for table in page.find_tables()]

    title = TITLE_DATE.search(first_page)
    if not title:
        raise ValueError("report has no date")
    report_date: date = datetime.strptime(title.group(1), "%B %d, %Y").date()

    rows, category = [], None
    for table in tables:
        for record in table:
            cells = [_clean(c) for c in record]
            if len(cells) < 3 or cells[0] == "COMMODITY" or not cells[0]:
                continue
            commodity, specification, price = cells[0], cells[1], cells[-1]
            if not price:
                category = commodity.title()
            elif PRICE.fullmatch(price):
                if category.endswith("Commercial Rice"):
                    origin = category.split()[0].title()
                    label = commodity if "rice" in commodity.lower() else f"{commodity} Rice"
                    commodity = f"{label}, {origin}"
                rows.append({
                    "group": category, "category": category, "commodity": commodity,
                    "specification": specification, "unit": _unit(commodity),
                    "price_centavos": None if price.lower() == "n/a" else round(float(price) * 100),
                })

    priced = sum(r["price_centavos"] is not None for r in rows)
    if priced < MIN_PRICED_ROWS or any(not r["category"] for r in rows):
        raise ValueError(f"report parsed poorly: {priced} priced rows of {len(rows)}")
    return {"report_date": report_date, "rows": rows}
