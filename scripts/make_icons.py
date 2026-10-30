"""Draws the app icon, a 3D gold peso coin on a green tile, at every size needed.

Run from the repository root: python scripts/make_icons.py (requires Pillow)
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SCALE = 4
SIZE = 1024 * SCALE


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def vertical_gradient(size, top, bottom):
    strip = Image.new("RGB", (1, 256))
    for y in range(256):
        strip.putpixel((0, y), lerp(top, bottom, y / 255))
    return strip.resize((size, size), Image.BICUBIC)


def s(value):
    return round(value * SCALE)


def ellipse_mask(box):
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).ellipse([s(v) for v in box], fill=255)
    return mask


def peso_mask(cx, cy, height):
    """A bold peso sign built from shapes, so it needs no particular font."""
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(mask)
    stroke = height * 0.16
    left, top = cx - height * 0.3, cy - height / 2
    bowl_h, bowl_w = height * 0.68, height * 0.74
    draw.rounded_rectangle([s(left), s(top), s(left + bowl_w), s(top + bowl_h)], radius=s(bowl_h / 2), fill=255)
    draw.rectangle([s(left), s(top), s(left + bowl_w * .5), s(top + bowl_h)], fill=255)
    hole_r = (bowl_h - 2 * stroke) / 2
    draw.rounded_rectangle(
        [s(left + stroke), s(top + stroke), s(left + bowl_w - stroke), s(top + bowl_h - stroke)],
        radius=s(hole_r), fill=0,
    )
    draw.rectangle([s(left + stroke), s(top + stroke), s(left + bowl_w * .5), s(top + bowl_h - stroke)], fill=0)
    draw.rectangle([s(left), s(top), s(left + stroke), s(top + height)], fill=255)
    bar = height * 0.075
    for y in (top + height * 0.2, top + height * 0.37):
        draw.rectangle([s(cx - height * 0.48), s(y), s(cx + height * 0.54), s(y + bar)], fill=255)
    return mask


def coin(canvas, cx, cy, rx, ry, depth):
    # Soft shadow on the surface below.
    shadow = ellipse_mask((cx - rx * .96, cy + depth + ry * .62, cx + rx * .96, cy + depth + ry * 1.2))
    shadow = shadow.filter(ImageFilter.GaussianBlur(s(26))).point(lambda v: v * 0.55)
    canvas.paste((6, 30, 16), (0, 0), shadow)

    # Rim: stacked ellipses give the coin its thickness.
    for offset in range(depth, 0, -1):
        tint = lerp((121, 72, 8), (214, 148, 32), 1 - offset / depth)
        box = (cx - rx, cy - ry + offset, cx + rx, cy + ry + offset)
        canvas.paste(tint, (0, 0), ellipse_mask(box))

    face = vertical_gradient(SIZE, (255, 231, 150), (232, 158, 36))
    canvas.paste(face, (0, 0), ellipse_mask((cx - rx, cy - ry, cx + rx, cy + ry)))

    inner = (cx - rx * .82, cy - ry * .82, cx + rx * .82, cy + ry * .82)
    well = vertical_gradient(SIZE, (226, 150, 30), (252, 209, 104))
    canvas.paste(well, (0, 0), ellipse_mask(inner))

    glyph = peso_mask(cx, cy + 4, ry * 1.04)
    edge = ImageChops.offset(glyph, 0, s(9))
    canvas.paste((122, 72, 6), (0, 0), edge)
    canvas.paste(vertical_gradient(SIZE, (255, 248, 214), (255, 222, 132)), (0, 0), glyph)

    # A curved glint across the top of the face.
    glint = ellipse_mask((cx - rx * .78, cy - ry * .93, cx + rx * .62, cy + ry * .1))
    cut = ellipse_mask((cx - rx * .9, cy - ry * .62, cx + rx * .9, cy + ry * 1.1))
    glint = ImageChops.subtract(glint, cut).filter(ImageFilter.GaussianBlur(s(10))).point(lambda v: v * 0.6)
    canvas.paste((255, 255, 255), (0, 0), glint)


def tile():
    base = vertical_gradient(SIZE, (37, 148, 86), (9, 52, 29))
    glow = ellipse_mask((90, -240, 950, 560)).filter(ImageFilter.GaussianBlur(s(90))).point(lambda v: v * 0.5)
    base.paste((94, 214, 142), (0, 0), glow)
    return base


def build():
    full = tile()
    coin(full, 512, 480, 318, 292, 62)

    foreground = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    layer = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    coin(layer, 512, 480, 250, 230, 48)
    mask = Image.new("L", (SIZE, SIZE), 0)
    for offset in range(49):
        mask = ImageChops.lighter(mask, ellipse_mask((262, 250 + offset, 762, 710 + offset)))
    foreground.paste(layer, (0, 0), mask)
    return full, foreground


def rounded(image, radius):
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, image.width - 1, image.height - 1], radius=radius, fill=255)
    result = image.convert("RGBA")
    result.putalpha(mask)
    return result


def main():
    root = Path(__file__).resolve().parent.parent
    full, foreground = build()
    assets = root / "mobile" / "assets"
    public = root / "web" / "public"
    assets.mkdir(exist_ok=True)
    public.mkdir(exist_ok=True)
    full.resize((1024, 1024), Image.LANCZOS).save(assets / "icon.png")
    foreground.resize((1024, 1024), Image.LANCZOS).save(assets / "icon_foreground.png")
    site = rounded(full, SIZE // 5)
    for name, size in {"favicon.png": 64, "logo.png": 128, "apple-touch-icon.png": 180, "icon-192.png": 192, "icon-512.png": 512}.items():
        site.resize((size, size), Image.LANCZOS).save(public / name)


if __name__ == "__main__":
    main()
