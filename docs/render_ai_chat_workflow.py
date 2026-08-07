from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "ai-chat-workflow.png"
FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

WIDTH = 2200
HEIGHT = 1680

BG = "#F4F7F5"
INK = "#142323"
MUTED = "#61706D"
LINE = "#C9D5D1"
WHITE = "#FFFFFF"
AI = "#6D56C9"
AI_SOFT = "#EEEAFE"
CODE = "#167C68"
CODE_SOFT = "#E3F3EE"
DATA = "#C67924"
DATA_SOFT = "#FFF1DD"
UI = "#285E9C"
UI_SOFT = "#E8F1FC"
WARN = "#A94B38"
WARN_SOFT = "#FFF0EC"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
draw = ImageDraw.Draw(canvas)


def rounded_box(
    xy: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str,
    radius: int = 24,
    width: int = 3,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def text_block(
    xy: tuple[int, int, int, int],
    title: str,
    body: str = "",
    *,
    title_color: str = INK,
    body_color: str = MUTED,
    align: str = "center",
    title_size: int = 29,
    body_size: int = 22,
) -> None:
    x1, y1, x2, y2 = xy
    title_font = font(title_size, bold=True)
    body_font = font(body_size)
    max_chars = max(18, int((x2 - x1) / (body_size * 0.56)))
    title_lines = wrap(title, max_chars)
    body_lines = wrap(body, max_chars) if body else []
    line_gap = 8
    total_height = (
        len(title_lines) * (title_size + 3)
        + len(body_lines) * (body_size + 4)
        + (14 if body_lines else 0)
        + max(0, len(title_lines) + len(body_lines) - 2) * line_gap
    )
    y = y1 + max(18, (y2 - y1 - total_height) // 2)
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x = x1 + 24 if align == "left" else x1 + (x2 - x1 - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=title_font, fill=title_color)
        y += title_size + line_gap
    if body_lines:
        y += 6
    for line in body_lines:
        bbox = draw.textbbox((0, 0), line, font=body_font)
        x = x1 + 24 if align == "left" else x1 + (x2 - x1 - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=body_font, fill=body_color)
        y += body_size + 6


def arrow(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str = MUTED,
    width: int = 5,
) -> None:
    draw.line((start, end), fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 > x1 else -1
        points = [(x2, y2), (x2 - direction * 18, y2 - 11), (x2 - direction * 18, y2 + 11)]
    else:
        direction = 1 if y2 > y1 else -1
        points = [(x2, y2), (x2 - 11, y2 - direction * 18), (x2 + 11, y2 - direction * 18)]
    draw.polygon(points, fill=color)


def connector(points: list[tuple[int, int]], *, color: str = MUTED, width: int = 4) -> None:
    draw.line(points, fill=color, width=width, joint="curve")
    arrow(points[-2], points[-1], color=color, width=width)


def pill(x: int, y: int, label: str, fill: str, color: str) -> int:
    pill_font = font(20, bold=True)
    bbox = draw.textbbox((0, 0), label, font=pill_font)
    pill_width = bbox[2] - bbox[0] + 34
    draw.rounded_rectangle((x, y, x + pill_width, y + 42), radius=21, fill=fill)
    draw.text((x + 17, y + 9), label, font=pill_font, fill=color)
    return x + pill_width


# Header
draw.text((90, 60), "TravelPlanner — Current AI Chat Workflow", font=font(52, bold=True), fill=INK)
draw.text(
    (92, 126),
    "One UI send creates a new intake, then a deterministic travel plan.",
    font=font(27),
    fill=MUTED,
)

x = 90
x = pill(x, 180, "UI", UI_SOFT, UI) + 14
x = pill(x, 180, "Gemini AI", AI_SOFT, AI) + 14
x = pill(x, 180, "Deterministic code", CODE_SOFT, CODE) + 14
pill(x, 180, "Persistence / external data", DATA_SOFT, DATA)

# User input
input_box = (580, 250, 1620, 360)
rounded_box(input_box, fill=WHITE, outline=UI)
text_block(
    input_box,
    "User sends one message",
    "Natural-language prompt  •  pasted URL  •  screenshots/images",
    title_color=UI,
)

# Stage 1 label
draw.text((90, 414), "1  EXPLORE INTAKE", font=font(24, bold=True), fill=AI)
draw.line((90, 452, 2110, 452), fill=LINE, width=3)

route_box = (640, 480, 1560, 570)
rounded_box(route_box, fill=UI_SOFT, outline=UI)
text_block(route_box, "POST /api/plans/explore/full/intake", "Multipart form data")
arrow((1100, 360), (1100, 478), color=UI)

prompt_box = (90, 625, 600, 770)
url_box = (670, 625, 1180, 770)
image_box = (1250, 625, 1760, 770)
auth_box = (1820, 625, 2110, 770)
rounded_box(prompt_box, fill=CODE_SOFT, outline=CODE)
rounded_box(url_box, fill=AI_SOFT, outline=AI)
rounded_box(image_box, fill=AI_SOFT, outline=AI)
rounded_box(auth_box, fill=DATA_SOFT, outline=DATA)
text_block(prompt_box, "Prompt parsing", "Extract URLs; infer destination and explicit number of days")
text_block(url_box, "URL / reel extraction", "Metadata + temporary media; audio STT and frame vision run in parallel")
text_block(image_box, "Image OCR", "Gemini reads travel text, places, prices, dates and captions")
text_block(auth_box, "Optional user", "Load long-term travel preferences", title_size=26, body_size=20)

connector([(1100, 570), (1100, 595), (345, 595), (345, 623)], color=UI)
connector([(1100, 570), (1100, 623)], color=UI)
connector([(1100, 570), (1100, 595), (1505, 595), (1505, 623)], color=UI)
connector([(1100, 570), (1100, 595), (1965, 595), (1965, 623)], color=UI)

gemini_box = (510, 825, 1690, 955)
rounded_box(gemini_box, fill=AI_SOFT, outline=AI, width=5)
text_block(
    gemini_box,
    "Gemini Explorer formatter",
    "Produces schema-validated JSON: intent, tripSpec, assumptions, missingInfoQuestions, preferenceSnapshot and placeCandidates",
    title_color=AI,
    title_size=32,
)
connector([(345, 770), (345, 800), (850, 800), (850, 823)], color=CODE)
connector([(925, 770), (925, 823)], color=AI)
connector([(1505, 770), (1505, 800), (1350, 800), (1350, 823)], color=AI)
connector([(1965, 770), (1965, 800), (1590, 800), (1590, 823)], color=DATA)

process_box = (220, 1010, 1160, 1135)
db_box = (1240, 1010, 1980, 1135)
rounded_box(process_box, fill=CODE_SOFT, outline=CODE)
rounded_box(db_box, fill=DATA_SOFT, outline=DATA)
text_block(
    process_box,
    "Aggregate → infer coverage → preferences → resolve",
    "Deduplicate candidates while preserving provenance; the places catalog then Google Maps Playwright resolve identity and coordinates",
    title_color=CODE,
)
text_block(
    db_box,
    "PostgreSQL: user_must_place",
    "Persist candidates and resolution under intakeId + userId",
    title_color=DATA,
)
connector([(1100, 955), (1100, 982), (690, 982), (690, 1008)], color=AI)
arrow((1160, 1072), (1238, 1072), color=DATA)

# Stage 2
draw.text((90, 1190), "2  BUILD MAIN PLAN", font=font(24, bold=True), fill=CODE)
draw.line((90, 1228, 2110, 1228), fill=LINE, width=3)

plan_route = (90, 1260, 530, 1385)
load_box = (585, 1260, 955, 1385)
planner_box = (1010, 1260, 1375, 1385)
finder_box = (1430, 1260, 1775, 1385)
check_box = (1830, 1260, 2110, 1385)
rounded_box(plan_route, fill=UI_SOFT, outline=UI)
rounded_box(load_box, fill=DATA_SOFT, outline=DATA)
rounded_box(planner_box, fill=CODE_SOFT, outline=CODE)
rounded_box(finder_box, fill=CODE_SOFT, outline=CODE)
rounded_box(check_box, fill=CODE_SOFT, outline=CODE)
text_block(plan_route, "POST /plans/main/from-explorer", "Explorer context + intakeId + userId", title_size=25, body_size=19)
text_block(load_box, "Load source places", "Reload schedulable candidates", title_size=25, body_size=19)
text_block(planner_box, "Planner", "Rule-based MacroPlan and day briefs", title_color=CODE, title_size=27, body_size=19)
text_block(finder_box, "Finder", "Rule-based places, times, breaks and route estimates", title_color=CODE, title_size=27, body_size=19)
text_block(check_box, "OverallChecker", "Empty days, duplicates and warnings", title_color=CODE, title_size=23, body_size=18)
arrow((530, 1322), (583, 1322), color=UI)
arrow((955, 1322), (1008, 1322), color=DATA)
arrow((1375, 1322), (1428, 1322), color=CODE)
arrow((1775, 1322), (1828, 1322), color=CODE)

# Output and limitation band
output_box = (90, 1445, 1190, 1585)
limit_box = (1250, 1445, 2110, 1585)
rounded_box(output_box, fill=UI_SOFT, outline=UI)
rounded_box(limit_box, fill=WARN_SOFT, outline=WARN)
text_block(
    output_box,
    "UI result",
    "Explorer details • source provenance • itinerary • estimated routes • map",
    title_color=UI,
)
text_block(
    limit_box,
    "Not a multi-turn conversation",
    "Messages stay in React state. Previous turns are not sent. No conversation ID, plan-edit context, SSE or token streaming.",
    title_color=WARN,
)
connector([(1970, 1385), (1970, 1415), (640, 1415), (640, 1443)], color=CODE)

draw.text(
    (90, 1625),
    "AI is used for understanding and extraction. Planner, Finder and validation are deterministic Python services. Generated plans are stored in process memory.",
    font=font(23),
    fill=MUTED,
)

canvas.save(OUTPUT, format="PNG", optimize=True)
print(OUTPUT)
