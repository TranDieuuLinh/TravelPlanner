"""
Tool 3: Festival Discovery - Festival/holiday discovery.

Discovers festivals and holidays in Vietnam with filtering by month.
Uses a static in-memory dataset (no database required).

Vietnamese festivals are tied to:
- Solar calendar (dl) - e.g., 30/4, 1/5, 2/9
- Lunar calendar (al) - e.g., Tết Nguyên Đán, Giỗ Tổ Hùng Vương
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.modules.plans.planner.research_tools_schema import (
    Festival,
    FestivalDiscoveryInput,
    FestivalDiscoveryOutput,
)


# ============================================================================
# Festival Data (Static In-Memory)
# ============================================================================

# Scale levels
SCALE_NATIONAL = "quoc-gia"
SCALE_REGIONAL = "vung"
SCALE_LOCAL = "dia-phuong"

# All festivals are defined here - no database required
FESTIVALS_DATA: list[Festival] = [
    # === QUÝ 1 (Jan-Mar) ===
    Festival(
        name="Tết Nguyên Đán",
        date="29-30-1 (âm lịch)",
        region_keys=["vn"],
        region_names=["Toàn quốc"],
        scale=SCALE_NATIONAL,
        activities=["đi lễ", "thăm relatives", "bắn pháo hoa", "múa lân", "trò chơi dân gian"],
        description="Tết cổ truyền lớn nhất Việt Nam, đánh dấu năm mới theo âm lịch",
    ),
    Festival(
        name="Lễ hội Đền Hùng",
        date="10/3 (âm lịch)",
        region_keys=["vn,phu-tho", "vn,ha-noi"],
        region_names=["Phú Thọ", "Hà Nội"],
        scale=SCALE_NATIONAL,
        activities=["dâng hương", "lễ giỗ", "hội Lim", "trò chơi dân gian"],
        description="Giỗ Tổ Hùng Vương - ngày tưởng nhớ các Vua Hùng",
    ),
    Festival(
        name="Hội xuân Yên Tử",
        date="mùng 1-16/1 (âm lịch)",
        region_keys=["vn,quang-ninh"],
        region_names=["Quảng Ninh"],
        scale=SCALE_REGIONAL,
        activities=["lên núi", "cầu nguyện", "lễ chùa", "du xuân"],
        description="Lễ hội xuân tại đỉnh Yên Tử, trung tâm Phật giáo Trúc Lâm",
    ),
    Festival(
        name="Lễ hội hoa Anh Đào",
        date="tháng 1-2 (dương lịch)",
        region_keys=["vn,sa-pa", "vn,da-lat"],
        region_names=["Sapa", "Đà Lạt"],
        scale=SCALE_REGIONAL,
        activities=["ngắm hoa", "chụp ảnh", "dạo phố", "trải nghiệm văn hóa"],
        description="Mùa hoa anh đào nở rộ tại các vùng núi cao",
    ),
    Festival(
        name="Lễ hội đua thuyền truyền thống",
        date="mùng 3-5/1 (âm lịch)",
        region_keys=["vn,thua-thien-hue", "vn,hue"],
        region_names=["Thừa Thiên Huế", "Huế"],
        scale=SCALE_REGIONAL,
        activities=["đua thuyền", "bơi thuyền", "lễ hội đường", "trình diễn văn nghệ"],
        description="Lễ hội đua thuyền truyền thống trên sông Hương",
    ),

    # === QUÝ 2 (Apr-Jun) ===
    Festival(
        name="Giỗ Tổ Hùng Vương",
        date="10/3 (âm lịch)",
        region_keys=["vn"],
        region_names=["Toàn quốc"],
        scale=SCALE_NATIONAL,
        activities=["dâng hương", "lễ giỗ", "trò chơi dân gian", "hội Lim"],
        description="Ngày Quốc giỗ - tưởng nhớ công lao tổ tiên dựng nước",
    ),
    Festival(
        name="Lễ 30/4",
        date="30/4",
        region_keys=["vn"],
        region_names=["Toàn quốc"],
        scale=SCALE_NATIONAL,
        activities=["diễu hành", "bắn pháo hoa", "lễ kỷ niệm", "du lịch"],
        description="Ngày Giải phóng miền Nam, thống nhất đất nước",
    ),
    Festival(
        name="Lễ 1/5",
        date="1/5",
        region_keys=["vn"],
        region_names=["Toàn quốc"],
        scale=SCALE_NATIONAL,
        activities=["mít tinh", "diễu hành", "nghỉ lễ", "du lịch"],
        description="Ngày Quốc tế Lao động",
    ),
    Festival(
        name="Lễ hội Bạch Mã",
        date="15/2-15/3 (âm lịch)",
        region_keys=["vn,thua-thien-hue", "vn,hue"],
        region_names=["Thừa Thiên Huế", "Huế"],
        scale=SCALE_REGIONAL,
        activities=["lễ tế", "diễu procession", "trình diễn văn nghệ", "du xuân"],
        description="Lễ hội truyền thống lớn nhất Huế, tôn vinh Thần Fua",
    ),
    Festival(
        name="Lễ hội đền Trần",
        date="14-16/1 (âm lịch)",
        region_keys=["vn,nam-dinh", "vn,thai-binh"],
        region_names=["Nam Định", "Thái Bình"],
        scale=SCALE_NATIONAL,
        activities=["lễ cầu phúc", "trình diễn nhạc lễ", "phật giáo", "trò chơi"],
        description="Lễ hội đền Trần tại Nam Định - tưởng nhớ các vị tướng nhà Trần",
    ),

    # === QUÝ 3 (Jul-Sep) ===
    Festival(
        name="Lễ Vu Lan báo hiếu",
        date="15/7 (âm lịch)",
        region_keys=["vn"],
        region_names=["Toàn quốc"],
        scale=SCALE_NATIONAL,
        activities=["thắp nến", "cúng Phật", "báo hiếu cha mẹ", "lễ chùa"],
        description="Ngày báo hiếu công ơn cha mẹ, tưởng nhớ người đã khuất",
    ),
    Festival(
        name="Lễ 2/9",
        date="2/9",
        region_keys=["vn"],
        region_names=["Toàn quốc"],
        scale=SCALE_NATIONAL,
        activities=["lễ kỷ niệm", "diễu hành", "bắn pháo hoa", "du lịch"],
        description="Ngày Quốc khánh - kỷ niệm Ngày Tuyên ngôn Độc lập",
    ),
    Festival(
        name="Lễ hội Nghinh Ông",
        date="tháng 7-8 (dương lịch)",
        region_keys=["vn,phan-thiet", "vn,binh-thuan"],
        region_names=["Phan Thiết", "Bình Thuận"],
        scale=SCALE_REGIONAL,
        activities=["đón cá voi", "lễ tế cá Voi", "parade", "bắn pháo hoa"],
        description="Lễ hội độc đáo của ngư dân Phan Thiết, tôn vinh cá Voi",
    ),
    Festival(
        name="Lễ Ok Om Bok",
        date="15/10 (âm lịch)",
        region_keys=["vn,soc-trang", "vn,can-tho"],
        region_names=["Sóc Trăng", "Cần Thơ"],
        scale=SCALE_REGIONAL,
        activities=["cúng trăng", "đua thuyền", "múa dâng", "lễ hội đường"],
        description="Lễ hội của người Khmer, cúng Trăng thu hoạch lúa",
    ),

    # === QUÝ 4 (Oct-Dec) ===
    Festival(
        name="Lễ hội chọi trâu",
        date="mùng 9-10/8 (âm lịch)",
        region_keys=["vn,nam-dinh", "vn,dien-bien"],
        region_names=["Nam Định", "Điện Biên"],
        scale=SCALE_REGIONAL,
        activities=["chọi trâu", "lễ tế", "trình diễn văn nghệ", "du xuân"],
        description="Lễ hội chọi trâu truyền thống, tôn vinh trâu bò",
    ),
    Festival(
        name="Lễ hội khao hỏa tử đạo",
        date="27/7",
        region_keys=["vn"],
        region_names=["Toàn quốc"],
        scale=SCALE_NATIONAL,
        activities=["dâng hoa", "lễ tưởng niệm", "thắp nến", "tri ân"],
        description="Ngày Thương binh Liệt sĩ - tưởng nhớ các anh hùng liệt sĩ",
    ),
    Festival(
        name="Lễ hội đêm Trung thu",
        date="15/8 (âm lịch)",
        region_keys=["vn"],
        region_names=["Toàn quốc"],
        scale=SCALE_NATIONAL,
        activities=["rước đèn", "múa lân", "phá cỗ", "trẻ em vui chơi"],
        description="Tết Trung thu - ngày tết thiếu nhi với đèn lồng, bánh dẻo",
    ),
    Festival(
        name="Lễ hội Gò Đống Đổ",
        date="20/11-25/11 (dương lịch)",
        region_keys=["vn,hcm-city", "vn,tp-ho-chi-minh"],
        region_names=["TP. Hồ Chí Minh", "Sài Gòn"],
        scale=SCALE_NATIONAL,
        activities=["lễ tế", "hội chợ", "trình diễn văn nghệ", "du lịch"],
        description="Lễ hội lớn nhất Sài Gòn, tưởng nhớ công lao dựng nước",
    ),
    Festival(
        name="Noel / Giáng sinh",
        date="25/12",
        region_keys=["vn"],
        region_names=["Toàn quốc"],
        scale=SCALE_NATIONAL,
        activities=["trang trí cây thông", "gửi thiệp", "lễ chào đón", "du lịch"],
        description="Lễ hội Kitô giáo, được tổ chức rộng rãi tại các thành phố lớn",
    ),
]


# ============================================================================
# Month Mapping
# ============================================================================

# Lunar months to Gregorian month ranges (approximate)
# Lunar calendar varies each year, so we use typical ranges
LUNAR_MONTH_APPROX: dict[int, list[int]] = {
    1: [1, 2],   # Tháng 1 âm ~ Jan-Feb
    2: [2, 3],   # Tháng 2 âm ~ Feb-Mar
    3: [3, 4],   # Tháng 3 âm ~ Mar-Apr
    4: [4, 5],   # Tháng 4 âm ~ Apr-May
    5: [5, 6],   # Tháng 5 âm ~ May-Jun
    6: [6, 7],   # Tháng 6 âm ~ Jun-Jul
    7: [7, 8],   # Tháng 7 âm ~ Jul-Aug
    8: [8, 9],   # Tháng 8 âm ~ Aug-Sep
    9: [9, 10],  # Tháng 9 âm ~ Sep-Oct
    10: [10, 11], # Tháng 10 âm ~ Oct-Nov
    11: [11, 12], # Tháng 11 âm ~ Nov-Dec
    12: [12, 1],  # Tháng 12 âm ~ Dec-Jan
}

# Solar date festivals
SOLAR_FESTIVALS: dict[str, list[str]] = {
    "1": ["Lễ 1/5", "Noel / Giáng sinh"],  # January
    "2": [],  # February
    "3": [],  # March
    "4": ["Lễ 30/4"],  # April
    "5": ["Lễ 1/5"],  # May
    "6": [],  # June
    "7": ["Lễ hội Nghinh Ông", "Lễ khao hỏa tử đạo"],  # July
    "8": ["Lễ hội Nghinh Ông"],  # August
    "9": ["Lễ 2/9"],  # September
    "10": [],  # October
    "11": ["Lễ hội Gò Đống Đổ"],  # November
    "12": ["Noel / Giáng sinh"],  # December
}


# ============================================================================
# Helper Functions
# ============================================================================

def _parse_month_filter(month_str: str | None) -> list[int] | None:
    """
    Parse month filter string to list of month numbers.
    
    Examples:
        "tháng 4" -> [4]
        "tháng 4/2026" -> [4]
        "Q1" -> [1, 2, 3]
        None -> None (all months)
    """
    if month_str is None:
        return None

    month_str = month_str.strip().lower()

    # Quarter filter
    quarter_match = re.match(r"^q([1-4])$", month_str)
    if quarter_match:
        q = int(quarter_match.group(1))
        return [(q - 1) * 3 + i for i in range(3)]

    # Month with year
    month_year_match = re.match(r"^tháng\s*(\d+)(?:/\d+)?$", month_str)
    if month_year_match:
        return [int(month_year_match.group(1))]

    # Just month
    just_month_match = re.match(r"^tháng\s*(\d+)$", month_str)
    if just_month_match:
        return [int(just_month_match.group(1))]

    # Lunar month
    lunar_match = re.match(r"^tháng\s*(\d+)\s*\(?âm\s*lịch\)?$", month_str)
    if lunar_match:
        lunar_month = int(lunar_match.group(1))
        return LUNAR_MONTH_APPROX.get(lunar_month, [])

    return None


def _festival_matches_month(festival: Festival, target_months: list[int] | None) -> bool:
    """Check if a festival matches the target month(s)."""
    if target_months is None:
        return True

    # Check lunar months
    lunar_month_match = re.search(r"(\d+)/(\d+)\s*\(?âm\s*lịch\)?", festival.date)
    if lunar_month_match:
        lunar_month = int(lunar_month_match.group(1))
        approx_gregorian_months = LUNAR_MONTH_APPROX.get(lunar_month, [])
        if any(m in target_months for m in approx_gregorian_months):
            return True

    # Check solar dates (day/month)
    solar_match = re.search(r"(\d{1,2})/(\d{1,2})(?!\s*\(?âm)", festival.date)
    if solar_match:
        solar_month = int(solar_match.group(2))
        if solar_month in target_months:
            return True

    # Check month ranges (e.g., "tháng 1-2")
    range_match = re.search(r"tháng\s*(\d+)-(\d+)", festival.date)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        for m in target_months:
            if start <= m <= end:
                return True

    # Check name-based
    festival_lower = festival.name.lower()
    for month in target_months:
        if month == 1 and "tết" in festival_lower:
            return True
        if month == 4 and "giỗ tổ" in festival_lower or "đền hùng" in festival_lower:
            return True

    return False


def _festival_matches_region(festival: Festival, region_key: str | None) -> bool:
    if not region_key or festival.scale == SCALE_NATIONAL:
        return True
    return any(
        candidate == region_key
        or candidate.startswith(f"{region_key},")
        or region_key.startswith(f"{candidate},")
        for candidate in festival.region_keys
    )


# ============================================================================
# Main Calculation Logic
# ============================================================================

def calculate_festival_discovery(
    input_data: FestivalDiscoveryInput,
) -> FestivalDiscoveryOutput:
    """
    Calculate festival discovery results.

    Args:
        input_data: Festival discovery input with optional month filter

    Returns:
        FestivalDiscoveryOutput with festivals list and by-month index
    """
    target_months = _parse_month_filter(input_data.month)

    # Filter festivals
    festivals = [
        f for f in FESTIVALS_DATA
        if _festival_matches_month(f, target_months)
        and _festival_matches_region(f, input_data.region_key)
    ]

    # Build by-month index
    by_month: dict[str, list[str]] = {}
    for festival in FESTIVALS_DATA:
        if not _festival_matches_region(festival, input_data.region_key):
            continue
        # Extract month from date
        months = set()
        
        # Lunar month
        lunar_match = re.search(r"(\d+)/(\d+)\s*\(?âm\s*lịch\)?", festival.date)
        if lunar_match:
            lunar_month = int(lunar_match.group(1))
            for gm in LUNAR_MONTH_APPROX.get(lunar_month, []):
                months.add(gm)

        # Solar month
        solar_match = re.search(r"(\d{1,2})/(\d{1,2})(?!\s*\(?âm)", festival.date)
        if solar_match:
            months.add(int(solar_match.group(2)))

        for month in months:
            month_key = f"tháng {month}"
            if month_key not in by_month:
                by_month[month_key] = []
            by_month[month_key].append(festival.name)

    # Sort festivals by name
    festivals.sort(key=lambda f: f.name)

    return FestivalDiscoveryOutput(
        festivals=festivals,
        by_month=by_month,
    )


# ============================================================================
# Tool Implementation
# ============================================================================

class FestivalDiscoveryTool:
    """
    Tool implementation for festival_discovery.
    Uses static in-memory data - no database or repository needed.
    """

    def execute(self, input_data: FestivalDiscoveryInput) -> FestivalDiscoveryOutput:
        """Execute the festival discovery tool."""
        return calculate_festival_discovery(input_data)
