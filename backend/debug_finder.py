"""Debug script: chạy Finder với payload mô phỏng user paste 2 ngày.

Mục tiêu: xác nhận skeleton thực sự được build, hiểu vì sao dinner break
không tìm được, và vì sao các block activity khác bị drop.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Đảm bảo relative import hoạt động
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from app.modules.plans.domain.entities import (
    DayBrief,
    MacroPlan,
    TravelIntent,
    UserStatus,
)
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.finder.place_tool import FinderPlace


# ---------------------------------------------------------------------------
# Fake place tool — trả về place theo ID
# ---------------------------------------------------------------------------


class FakeFinderPlaceTool:
    def __init__(self, places: dict[str, FinderPlace]):
        self.places = places
        self.search_queries: list[list[str]] = []

    def get(self, place_id: str) -> FinderPlace | None:
        return self.places.get(place_id)

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[FinderPlace]:
        self.search_queries.append({
            "region": region_key,
            "tags": list(target_tags),
            "excluded": set(excluded_place_ids),
            "limit": limit,
        })
        # Trả về các place còn lại (trừ excluded) trong region
        candidates = [
            p for p in self.places.values()
            if p.place_id not in excluded_place_ids
            and (p.region_key == region_key or p.region_key.startswith(region_key + ","))
        ]
        return candidates[:limit]


def _place(place_id: str, name: str, place_type: str, region_key: str = "vn,ha-noi,hoan-kiem", tags: list[str] | None = None) -> FinderPlace:
    return FinderPlace(
        placeId=place_id,
        name=name,
        placeType=place_type,
        regionKey=region_key,
        tags=tags or [],
        latitude=21.03,
        longitude=105.85,
        typicalDurationMinutes=60,
        dataConfidence="high",
    )


# ---------------------------------------------------------------------------
# Case 1: User paste 2 ngày với source_time_hint (giống case thực của bạn)
# ---------------------------------------------------------------------------


def case_source_itinerary_sparse():
    """Day 1: 09:00-09:45 (Nộm bò khô) + 12:15-13:15 (Phương Anh)
    Day 2: 12:00-13:00 (Tây Quán) + 14:30-16:30 (Vân Art Gallery)
    """
    places = {
        "nom-bo-kho": _place("nom-bo-kho", "Nộm Bò Khô Long Vi Dung", "restaurant"),
        "phuong-anh": _place("phuong-anh", "Nhà hàng quà vặt Phương Anh", "restaurant"),
        "tay-quan": _place("tay-quan", "Tây Quán - Nướng Lẩu", "restaurant"),
        "van-art": _place("van-art", "Vân Art Gallery", "art_gallery"),
    }
    tool = FakeFinderPlaceTool(places)
    finder = FinderService(tool)

    intent = TravelIntent(
        destination="Hà Nội",
        days=2,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["culture", "food"],
    )
    user_status = UserStatus()

    macro_plan = MacroPlan(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            DayBrief(
                day=1,
                theme="Di sản văn hóa và ẩm thực phố cổ",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=["nom-bo-kho", "phuong-anh"],
            ),
            DayBrief(
                day=2,
                theme="Nhịp sống hiện đại và thư giãn bên hồ",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=["tay-quan", "van-art"],
            ),
        ],
    )

    selected = [
        SelectedPlaceContext(
            placeId="nom-bo-kho",
            name="Nộm Bò Khô Long Vi Dung",
            mustVisit=True,
            sourceRefs=["https://youtube.com/watch?v=abc"],
            sourceOrder=1,
            sourceTimeHint="09:00",
            sourceDurationMinutes=45,
            tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="phuong-anh",
            name="Nhà hàng quà vặt Phương Anh",
            mustVisit=True,
            sourceRefs=["https://youtube.com/watch?v=abc"],
            sourceOrder=2,
            sourceTimeHint="12:15",
            sourceDurationMinutes=60,
            tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="tay-quan",
            name="Tây Quán - Nướng Lẩu",
            mustVisit=True,
            sourceRefs=["https://youtube.com/watch?v=abc"],
            sourceOrder=1,
            sourceDay=2,
            sourceTimeHint="12:00",
            sourceDurationMinutes=60,
            tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="van-art",
            name="Vân Art Gallery",
            mustVisit=True,
            sourceRefs=["https://youtube.com/watch?v=abc"],
            sourceOrder=2,
            sourceDay=2,
            sourceTimeHint="14:30",
            sourceDurationMinutes=120,
            tags=["culture"],
        ),
    ]

    result = finder.fill_main_plan(macro_plan, intent, selected, user_status=user_status)

    print("=" * 80)
    print("CASE 1: Source itinerary (giống case thực bạn paste)")
    print("=" * 80)
    print(f"Strategies: {[d.strategy for d in result.days]}")
    print(f"Warnings: {result.warnings}")
    print(f"Unscheduled: {[p.name for p in result.unscheduled_places]}")
    print(f"Final plan status warnings: {result.final_plan_status.warnings}")
    print(f"Rejections: {result.final_plan_status.rejected_candidate_ids}")
    print(f"Search queries: {tool.search_queries}")
    print()
    for day in result.days:
        print(f"--- Day {day.day} ({day.theme}) | strategy={day.strategy}")
        for item in day.items:
            print(f"  [{item.time_window:>13s}] {item.role:<25s} | {item.name} ({item.source})")
        print()
    print()


# ---------------------------------------------------------------------------
# Case 2: Cùng 4 selected places nhưng KHÔNG có source_order (no source itinerary)
# Để xem code mới có chạy không
# ---------------------------------------------------------------------------


def case_no_source_itinerary():
    """Cùng 4 place nhưng không có source_order → vào nhánh anchor_day / scattered_day"""
    places = {
        "nom-bo-kho": _place("nom-bo-kho", "Nộm Bò Khô Long Vi Dung", "restaurant"),
        "phuong-anh": _place("phuong-anh", "Nhà hàng quà vặt Phương Anh", "restaurant"),
        "tay-quan": _place("tay-quan", "Tây Quán - Nướng Lẩu", "restaurant"),
        "van-art": _place("van-art", "Vân Art Gallery", "art_gallery"),
    }
    tool = FakeFinderPlaceTool(places)
    finder = FinderService(tool)

    intent = TravelIntent(
        destination="Hà Nội",
        days=2,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["culture", "food"],
    )
    user_status = UserStatus()

    macro_plan = MacroPlan(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            DayBrief(
                day=1,
                theme="Di sản văn hóa và ẩm thực phố cổ",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=["nom-bo-kho", "phuong-anh"],
            ),
            DayBrief(
                day=2,
                theme="Nhịp sống hiện đại và thư giãn bên hồ",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=["tay-quan", "van-art"],
            ),
        ],
    )

    selected = [
        SelectedPlaceContext(
            placeId="nom-bo-kho", name="Nộm Bò Khô Long Vi Dung", mustVisit=True, tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="phuong-anh", name="Nhà hàng quà vặt Phương Anh", mustVisit=True, tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="tay-quan", name="Tây Quán - Nướng Lẩu", mustVisit=True, tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="van-art", name="Vân Art Gallery", mustVisit=True, tags=["culture"],
        ),
    ]

    result = finder.fill_main_plan(macro_plan, intent, selected, user_status=user_status)

    print("=" * 80)
    print("CASE 2: KHÔNG có source_order (vào code mới anchor_day)")
    print("=" * 80)
    print(f"Strategies: {[d.strategy for d in result.days]}")
    print(f"Warnings: {result.warnings}")
    print(f"Unscheduled: {[p.name for p in result.unscheduled_places]}")
    print()
    for day in result.days:
        print(f"--- Day {day.day} ({day.theme}) | strategy={day.strategy}")
        for item in day.items:
            print(f"  [{item.time_window:>13s}] {item.role:<25s} | {item.name} ({item.source})")
        print()
    print()


# ---------------------------------------------------------------------------
# Case 3: Selected toàn cafe/shop (test code mới chọn scattered)
# ---------------------------------------------------------------------------


def case_scattered_day():
    places = {
        "cafe-1": _place("cafe-1", "Cafe A", "cafe"),
        "cafe-2": _place("cafe-2", "Cafe B", "coffee_shop"),
        "tiem-banh": _place("tiem-banh", "Tiệm bánh X", "tiem_banh"),
        "cho": _place("cho", "Chợ đêm", "cho"),
    }
    tool = FakeFinderPlaceTool(places)
    finder = FinderService(tool)

    intent = TravelIntent(
        destination="Hà Nội",
        days=1,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["food"],
    )
    user_status = UserStatus()

    macro_plan = MacroPlan(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            DayBrief(
                day=1,
                theme="Street food & cafe",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["food"],
                allocatedSelectedPlaceRefs=["cafe-1", "cafe-2", "tiem-banh", "cho"],
            ),
        ],
    )

    selected = [
        SelectedPlaceContext(placeId="cafe-1", name="Cafe A", mustVisit=True, tags=["cafe"]),
        SelectedPlaceContext(placeId="cafe-2", name="Cafe B", mustVisit=True, tags=["cafe"]),
        SelectedPlaceContext(placeId="tiem-banh", name="Tiệm bánh X", mustVisit=True, tags=["bakery"]),
        SelectedPlaceContext(placeId="cho", name="Chợ đêm", mustVisit=True, tags=["market"]),
    ]

    result = finder.fill_main_plan(macro_plan, intent, selected, user_status=user_status)

    print("=" * 80)
    print("CASE 3: 4 place cafe/bakery/cho (test scattered_day)")
    print("=" * 80)
    print(f"Strategies: {[d.strategy for d in result.days]}")
    print(f"Warnings: {result.warnings}")
    print(f"Unscheduled: {[p.name for p in result.unscheduled_places]}")
    print()
    for day in result.days:
        print(f"--- Day {day.day} ({day.theme}) | strategy={day.strategy}")
        for item in day.items:
            print(f"  [{item.time_window:>13s}] {item.role:<25s} | {item.name} ({item.source})")
        print()


if __name__ == "__main__":
    case_source_itinerary_sparse()
    case_no_source_itinerary()
    case_scattered_day()
