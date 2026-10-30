"""DTI Suggested Retail Prices, read from the official e-Presyo bulletin PDF.

The bulletin is a multi-column poster. Rows come from its table cells because plain
text extraction interleaves the columns, which would pair prices with the wrong products.
"""
import io
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from urllib.parse import quote

import pdfplumber

BUCKET = "https://dtiwebfiles.s3.ap-southeast-1.amazonaws.com"
LISTING_URL = f"{BUCKET}/?list-type=2&prefix=e-Presyo/SRP"
PDF_PREFIX = "e-Presyo/SRP Basic Necessities and Prime Commodities/"
PRICE = re.compile(r"(?<![\w.])\d{1,4}\.\d{2}(?![\w.])")
MIN_ROWS = 120
GROUPS = {"BASIC NECESSITIES": "Basic Necessities", "PRIME COMMODITIES": "Prime Commodities"}


def latest_bulletin_url(listing_xml: bytes) -> str:
    """Newest uploaded bulletin, skipping DTI's working copies."""
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    entries = [
        (entry.findtext("s3:LastModified", "", ns), entry.findtext("s3:Key", "", ns))
        for entry in ET.fromstring(listing_xml).findall("s3:Contents", ns)
    ]
    usable = [
        (modified, key) for modified, key in entries
        if key.startswith(PDF_PREFIX) and key.lower().endswith(".pdf")
        and not re.search(r"backup|bakcup", key, re.I)
    ]
    if not usable:
        raise ValueError("no SRP bulletin found in the DTI listing")
    return f"{BUCKET}/{quote(max(usable)[1])}"


def _clean(cell: str | None) -> str:
    return " ".join((cell or "").split())


def _category(heading: str) -> str:
    return heading.title().replace("3-In-1", "3-in-1").replace(" – ", " - ").replace("Doy ", "Doy ")


def parse_bulletin(pdf_bytes: bytes) -> dict:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        tables = [table.extract() for table in page.find_tables()]

    found = re.search(r"effective\s+(\d{1,2} \w+ \d{4})", text)
    if not found:
        raise ValueError("bulletin has no effective date")
    effective: date = datetime.strptime(found.group(1), "%d %B %Y").date()

    rows, group, category = [], None, None
    for table in tables:
        for offset in range(0, len(table[0]), 3):  # name, unit, SRP repeat across the page
            for record in table:
                name, unit, price = (_clean(c) for c in record[offset:offset + 3])
                if not name and not price:
                    continue
                if name.upper() in GROUPS:
                    group = GROUPS[name.upper()]
                elif not price:
                    category = _category(name)
                elif PRICE.fullmatch(price):
                    rows.append({
                        "group": group, "category": category, "commodity": name,
                        "specification": unit, "unit": "pack",
                        "price_centavos": round(float(price) * 100),
                    })
                else:
                    raise ValueError(f"unreadable SRP cell: {price!r}")

    expected = len(PRICE.findall(text))
    if len(rows) < MIN_ROWS or len(rows) != expected:
        raise ValueError(f"read {len(rows)} SRP rows but the page shows {expected} prices")
    return {"report_date": effective, "rows": rows}
