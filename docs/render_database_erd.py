from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).resolve().parent / "database-erd.png"
W, H = 2200, 1500
BG = "#f8f4ea"
INK = "#1f2d3a"
MUTED = "#66717c"
CARD = "#fffdf8"
LINE = "#52616b"
IMPLEMENTED = "#2f7d5b"
PLANNED = "#6b5a90"
LINK = "#b76830"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


TITLE = load_font(46, True)
SUBTITLE = load_font(24)
TABLE = load_font(24, True)
FIELD = load_font(17)
SMALL = load_font(16)
TINY = load_font(14)


TABLES = {
    "users": {
        "box": (80, 185, 395, 385),
        "color": IMPLEMENTED,
        "status": "implemented",
        "fields": ["id PK", "email unique", "full_name", "role", "travel_preferences"],
    },
    "places": {
        "box": (500, 185, 815, 385),
        "color": PLANNED,
        "status": "planned",
        "fields": ["id PK", "name", "place_type", "address", "lat/lng", "metadata"],
    },
    "trips": {
        "box": (80, 520, 395, 750),
        "color": PLANNED,
        "status": "planned",
        "fields": ["id PK", "owner_id FK", "destination", "start/end_date", "budget", "party_size", "status"],
    },
    "itinerary_items": {
        "box": (505, 520, 820, 750),
        "color": LINK,
        "status": "link",
        "fields": ["id PK", "trip_id FK", "place_id FK", "day_number", "start/end_time", "sort_order", "cost"],
    },
    "trip_members": {
        "box": (80, 850, 395, 1025),
        "color": LINK,
        "status": "link",
        "fields": ["trip_id FK", "user_id FK", "role", "joined_at"],
    },
    "marketplace_plans": {
        "box": (1330, 185, 1665, 425),
        "color": PLANNED,
        "status": "planned",
        "fields": ["id PK", "creator_id FK", "title", "destination", "duration_days", "price", "status", "version"],
    },
    "marketplace_plan_items": {
        "box": (1330, 520, 1665, 735),
        "color": LINK,
        "status": "link",
        "fields": ["id PK", "marketplace_plan_id FK", "place_id FK", "day_number", "start/end_time", "sort_order"],
    },
    "orders": {
        "box": (80, 1160, 395, 1380),
        "color": PLANNED,
        "status": "planned",
        "fields": ["id PK", "buyer_id FK", "total_amount", "currency", "status", "created_at"],
    },
    "order_items": {
        "box": (505, 1160, 820, 1380),
        "color": LINK,
        "status": "link",
        "fields": ["id PK", "order_id FK", "marketplace_plan_id FK", "unit_amount", "quantity"],
    },
    "payments": {
        "box": (930, 1160, 1245, 1380),
        "color": PLANNED,
        "status": "planned",
        "fields": ["id PK", "order_id FK", "provider", "method", "transaction_id", "status"],
    },
    "reviews": {
        "box": (1770, 850, 2105, 1065),
        "color": PLANNED,
        "status": "planned",
        "fields": ["id PK", "user_id FK", "marketplace_plan_id FK", "order_id FK", "rating", "creator_reply"],
    },
    "favorites": {
        "box": (1810, 520, 2125, 695),
        "color": LINK,
        "status": "link",
        "fields": ["user_id FK", "marketplace_plan_id FK", "created_at"],
    },
    "achievements": {
        "box": (930, 850, 1245, 1045),
        "color": PLANNED,
        "status": "planned",
        "fields": ["id PK", "code unique", "name", "description", "criteria"],
    },
    "user_achievements": {
        "box": (505, 850, 820, 1045),
        "color": LINK,
        "status": "link",
        "fields": ["user_id FK", "achievement_id FK", "progress", "achieved_at"],
    },
}


RELATIONS = [
    ("users", "trips", "owner"),
    ("users", "trip_members", ""),
    ("trips", "trip_members", ""),
    ("trips", "itinerary_items", ""),
    ("places", "itinerary_items", ""),
    ("marketplace_plans", "marketplace_plan_items", ""),
    ("places", "marketplace_plan_items", ""),
    ("orders", "order_items", ""),
    ("orders", "payments", ""),
    ("achievements", "user_achievements", ""),
]


SIDE_RELATIONS = [
    "users.creator_id -> marketplace_plans",
    "users.buyer_id -> orders",
    "users.user_id -> reviews, favorites, user_achievements",
    "marketplace_plans -> order_items, reviews, favorites",
]


def center(name: str) -> tuple[int, int]:
    x1, y1, x2, y2 = TABLES[name]["box"]
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def edge_point(name: str, target: str) -> tuple[int, int]:
    x1, y1, x2, y2 = TABLES[name]["box"]
    cx, cy = center(name)
    tx, ty = center(target)
    dx, dy = tx - cx, ty - cy
    if abs(dx) > abs(dy):
        return (x2 if dx > 0 else x1, cy)
    return (cx, y2 if dy > 0 else y1)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str, width: int = 2, radius: int = 18) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, font: ImageFont.ImageFont, fill: str = INK) -> None:
    draw.text(xy, value, font=font, fill=fill)


def draw_relation(draw: ImageDraw.ImageDraw, source: str, target: str, label: str) -> None:
    start = edge_point(source, target)
    end = edge_point(target, source)
    draw.line((start, end), fill=LINE, width=3)
    ex, ey = end
    sx, sy = start
    dx, dy = ex - sx, ey - sy
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    size = 13
    draw.polygon(
        [
            (ex, ey),
            (int(ex - ux * size + px * 7), int(ey - uy * size + py * 7)),
            (int(ex - ux * size - px * 7), int(ey - uy * size - py * 7)),
        ],
        fill=LINE,
    )
    if label:
        lx = (sx + ex) // 2
        ly = (sy + ey) // 2
        bbox = draw.textbbox((lx, ly), label, font=TINY)
        rounded(draw, (bbox[0] - 6, bbox[1] - 4, bbox[2] + 6, bbox[3] + 4), "#fffaf1", "#ddcfbf", 1, 8)
        draw_text(draw, (lx, ly), label, TINY, MUTED)


def draw_table(draw: ImageDraw.ImageDraw, name: str, data: dict[str, object]) -> None:
    box = data["box"]
    color = data["color"]
    rounded(draw, box, CARD, color, 3, 18)
    x1, y1, x2, _ = box
    draw.rounded_rectangle((x1, y1, x2, y1 + 48), radius=16, fill=color)
    draw.rectangle((x1, y1 + 24, x2, y1 + 48), fill=color)
    draw_text(draw, (x1 + 18, y1 + 13), name, TABLE, "#ffffff")
    y = y1 + 65
    for field in data["fields"]:
        for line in wrap(field, width=29):
            draw_text(draw, (x1 + 20, y), line, FIELD, INK)
            y += 24


def draw_note_panel(draw: ImageDraw.ImageDraw) -> None:
    box = (1330, 1160, 2125, 1380)
    rounded(draw, box, "#fffaf1", "#d8c8b7", 2, 18)
    draw_text(draw, (1360, 1190), "FK relations shown by fields", TABLE, INK)
    y = 1235
    for item in SIDE_RELATIONS:
        draw.ellipse((1362, y + 8, 1372, y + 18), fill=LINE)
        draw_text(draw, (1388, y), item, FIELD, MUTED)
        y += 36


def capsule(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, color: str) -> None:
    bbox = draw.textbbox((0, 0), label, font=SMALL)
    w = bbox[2] - bbox[0] + 44
    rounded(draw, (x, y, x + w, y + 42), color, color, 1, 21)
    draw_text(draw, (x + 22, y + 12), label, SMALL, "#ffffff")


def main() -> None:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw_text(draw, (80, 55), "VSF Travel Database ERD", TITLE)
    draw_text(draw, (82, 112), "Implemented users table plus planned core/link tables for trips, marketplace, orders, payments, reviews, and achievements.", SUBTITLE, MUTED)
    capsule(draw, 1620, 60, "Implemented", IMPLEMENTED)
    capsule(draw, 1790, 60, "Planned core", PLANNED)
    capsule(draw, 1975, 60, "Link table", LINK)

    for source, target, label in RELATIONS:
        draw_relation(draw, source, target, label)

    for name, data in TABLES.items():
        draw_table(draw, name, data)

    draw_note_panel(draw)

    draw_text(draw, (80, 1440), "Generated from docs/13-database-schema.md and current backend models. Only users is migrated today; the rest are target schema tables.", SMALL, MUTED)
    image.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
