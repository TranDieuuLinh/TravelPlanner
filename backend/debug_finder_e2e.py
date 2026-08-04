"""E2E debug: chạy Finder thực với data giả lập giống case user.

Mục tiêu:
  1. Xác nhận bbox filter có thực sự drop place ngoài bbox không
  2. Chạy case FND-002 (URL reels) — tương đương input của bạn
  3. Quan sát skeleton/strategy và các warning

Không cần Docker — chỉ dùng in-memory repository.
"""
# tại thằng Lợi
from __future__ import annotations

import sys
from pathlib import Path

backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from app.modules.plans.domain.entities import (
    PlaceSelectionDay,
    PlaceSelectionBlueprint,
    TravelIntent,
    UserStatus,
)
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.place_selector.service import PlaceSelectorService
from app.modules.plans.place_selector.place_tool import RepositoryPlaceSelectionTool
from app.modules.places.model import Place


# ---------------------------------------------------------------------------
# In-memory repo
# ---------------------------------------------------------------------------


class InMemoryFinderRepo:
    def __init__(self, places: list[Place]) -> None:
        self._by_id = {p.id: p for p in places if p.id}
        self._by_region: dict[str, list[Place]] = {}
        for place in places:
            for region in self._enumerate_regions(place.region_key):
                self._by_region.setdefault(region, []).append(place)

    @staticmethod
    def _enumerate_regions(region_key: str) -> list[str]:
        parts = region_key.split(",")
        out = []
        for length in range(len(parts), 0, -1):
            out.append(",".join(parts[:length]))
        return out

    def get(self, place_id: str) -> Place | None:
        return self._by_id.get(place_id)

    def list_for_finder(self, region_key: str, *, limit: int = 10000) -> list[Place]:
        return list(self._by_region.get(region_key, []))[:limit]


class LoggingTool(RepositoryPlaceSelectionTool):
    """Wrap tool to record search calls + their bbox filtering outcome."""

    def __init__(self, repo):
        super().__init__(repo)
        self.calls: list[dict] = []

    def search(self, *, region_key, target_tags, excluded_place_ids, limit, bbox_filter=None):
        # Snapshot candidates pre-filter
        raw = self.repository.list_for_finder(region_key, limit=limit)
        self.calls.append({
            "region": region_key,
            "tags": list(target_tags),
            "excluded": set(excluded_place_ids),
            "bbox": bbox_filter,
            "candidate_count": len(raw),
            "candidate_ids": [p.id for p in raw],
        })
        return super().search(
            region_key=region_key,
            target_tags=target_tags,
            excluded_place_ids=excluded_place_ids,
            limit=limit,
            bbox_filter=bbox_filter,
        )


def _place(
    place_id: str,
    name: str,
    *,
    place_type: str = "restaurant",
    region_key: str = "vn,ha-noi,hoan-kiem",
    tags: list[str] | None = None,
    lat: float = 21.03,
    lon: float = 105.85,
    duration: int = 60,
    intensity: str | None = "light",
    opening_hours: list[dict] | None = None,
    rating: float = 4.5,
) -> Place:
    place = Place(
        id=place_id,
        name=name,
        place_type=place_type,
        region_key=region_key,
        data_confidence="high",
        typical_duration_minutes=duration,
    )
    place.latitude = lat
    place.longitude = lon
    place.metadata_json = {}
    place.opening_hours = opening_hours or [
        {"openTime": "07:00", "closeTime": "22:00"}
    ]
    place.rating = rating
    place.weather_sensitivity = "low"
    place.price_level = "mid_range"
    place.tags = tags or []
    return place


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_day(day) -> None:
    print(f"  --- Day {day.day} ({day.theme}) | strategy={day.strategy}")
    for item in day.items:
        print(
            f"    [{item.time_window:>13s}] {item.role:<22s} | "
            f"{item.name!r:<40s} (source={item.source})"
        )


def _run_case(
    case_name: str,
    macro_plan: PlaceSelectionBlueprint,
    selected_places: list[SelectedPlaceContext],
    places: list[Place],
    intent: TravelIntent,
    *,
    allow_finder_suggestions: bool = True,
) -> None:
    print("=" * 80)
    print(f"CASE: {case_name}")
    print("=" * 80)

    repo = InMemoryFinderRepo(places)
    tool = LoggingTool(repo)
    finder = PlaceSelectorService(tool)
    user_status = UserStatus()

    result = finder.fill_main_plan(
        macro_plan,
        intent,
        selected_places,
        user_status=user_status,
        allow_finder_suggestions=allow_finder_suggestions,
    )

    print(f"  Strategies: {[d.strategy for d in result.days]}")
    print(f"  Warnings: {result.warnings}")
    print(f"  Unscheduled: {[(p.name, p.reason_code) for p in result.unscheduled_places]}")
    print(f"  Search calls: {len(tool.calls)}")
    for i, c in enumerate(tool.calls, 1):
        print(
            f"    [{i}] region={c['region']!r} tags={c['tags']} "
            f"excluded={c['excluded']} bbox={c['bbox']} "
            f"raw_count={c['candidate_count']} ids={c['candidate_ids']}"
        )
    print()
    for day in result.days:
        _print_day(day)
    print()


# ---------------------------------------------------------------------------
# CASE A: FND-002 — URL reels giống input của bạn
#   - 3 selected place với sourceOrder=1,2,3
#   - allowFinderSuggestions=false
# ---------------------------------------------------------------------------


def case_fnd_002():
    places = [
        _place(
            "p_hn_bun_thang", "Bún Thang Cầu Gỗ",
            place_type="restaurant", lat=21.034, lon=105.852,
            duration=75, tags=["food", "local_cuisine"],
        ),
        _place(
            "p_hn_hoang_thanh", "Hoàng Thành Thăng Long",
            place_type="museum", lat=21.035, lon=105.842,
            duration=150, intensity="moderate",
            tags=["culture", "history"],
        ),
        _place(
            "p_hn_cho_dem", "Chợ Đêm Phố Cổ Hà Nội",
            place_type="market", lat=21.030, lon=105.850,
            duration=120, tags=["market", "food"],
        ),
    ]
    macro_plan = PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            PlaceSelectionDay(
                day=1,
                theme="Source itinerary",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=[
                    "p_hn_bun_thang",
                    "p_hn_hoang_thanh",
                    "p_hn_cho_dem",
                ],
            ),
        ],
    )
    selected = [
        SelectedPlaceContext(
            placeId="p_hn_bun_thang", name="Bún Thang Cầu Gỗ",
            mustVisit=True, sourceOrder=1, sourceDay=1,
            sourceTimeHint="11:30", sourceDurationMinutes=75,
            tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="p_hn_hoang_thanh", name="Hoàng Thành Thăng Long",
            mustVisit=True, sourceOrder=2, sourceDay=1,
            sourceTimeHint="14:00", sourceDurationMinutes=150,
            tags=["culture"],
        ),
        SelectedPlaceContext(
            placeId="p_hn_cho_dem", name="Chợ Đêm Phố Cổ Hà Nội",
            mustVisit=True, sourceOrder=3, sourceDay=1,
            sourceTimeHint="19:00", sourceDurationMinutes=120,
            tags=["market"],
        ),
    ]
    intent = TravelIntent(
        destination="Hà Nội", days=1, budget=BudgetLevel.medium,
        travelStyle="local", pace=TravelPace.balanced,
        interests=["culture", "food"],
    )
    _run_case(
        "FND-002 — URL reels 3 điểm (giống input của bạn)",
        macro_plan, selected, places, intent,
        allow_finder_suggestions=False,
    )


# ---------------------------------------------------------------------------
# CASE B: User's actual problem — 2 ngày, mỗi ngày 2 place với source_time_hint
# ---------------------------------------------------------------------------


def case_user_problem():
    # Places chính từ input của bạn (4 place, region hơi khác nhau)
    places = [
        # Day 1
        _place(
            "p_nom_bo_kho", "Nộm Bò Khô Long Vi Dung",
            place_type="restaurant",
            region_key="vn,ha-noi,hoan-kiem,hang-bai",
            lat=21.029, lon=105.853, duration=45,
            tags=["food"],
        ),
        _place(
            "p_phuong_anh", "Nhà hàng quà vặt Phương Anh",
            place_type="restaurant",
            region_key="vn,ha-noi,hoan-kiem,hang-bac",
            lat=21.030, lon=105.850, duration=60,
            tags=["food"],
        ),
        # Day 2
        _place(
            "p_tay_quan", "Tây Quán - Nướng Lẩu - Ngã tư Văn Cao",
            place_type="restaurant",
            region_key="vn,ha-noi,ba-dinh,ngoc-ha",
            lat=21.040, lon=105.812, duration=60,
            tags=["food"],
        ),
        _place(
            "p_van_art", "Vân Art Gallery",
            place_type="art_gallery",
            region_key="vn,ha-noi,hai-ba-trung",
            lat=21.012, lon=105.860, duration=120,
            tags=["culture", "art"],
        ),
    ]
    macro_plan = PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            PlaceSelectionDay(
                day=1,
                theme="Di sản văn hóa và ẩm thực phố cổ",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=["p_nom_bo_kho", "p_phuong_anh"],
            ),
            PlaceSelectionDay(
                day=2,
                theme="Nhịp sống hiện đại và thư giãn bên hồ",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=["p_tay_quan", "p_van_art"],
            ),
        ],
    )
    selected = [
        SelectedPlaceContext(
            placeId="p_nom_bo_kho", name="Nộm Bò Khô Long Vi Dung",
            mustVisit=True, sourceOrder=1, sourceDay=1,
            sourceTimeHint="09:00", sourceDurationMinutes=45,
            tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="p_phuong_anh", name="Nhà hàng quà vặt Phương Anh",
            mustVisit=True, sourceOrder=2, sourceDay=1,
            sourceTimeHint="12:15", sourceDurationMinutes=60,
            tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="p_tay_quan", name="Tây Quán - Nướng Lẩu",
            mustVisit=True, sourceOrder=1, sourceDay=2,
            sourceTimeHint="12:00", sourceDurationMinutes=60,
            tags=["food"],
        ),
        SelectedPlaceContext(
            placeId="p_van_art", name="Vân Art Gallery",
            mustVisit=True, sourceOrder=2, sourceDay=2,
            sourceTimeHint="14:30", sourceDurationMinutes=120,
            tags=["culture"],
        ),
    ]
    intent = TravelIntent(
        destination="Hà Nội", days=2, budget=BudgetLevel.medium,
        travelStyle="local", pace=TravelPace.balanced,
        interests=["culture", "food"],
    )
    _run_case(
        "USER PROBLEM — 2 ngày, mỗi ngày 2 place + source_time_hint",
        macro_plan, selected, places, intent,
        allow_finder_suggestions=True,
    )


# ---------------------------------------------------------------------------
# CASE C: Test bbox filter có hoạt động không
#   - 2 selected ở Hoàn Kiếm
#   - 1 catalog suggestion ở Long Biên (xa bbox)
# ---------------------------------------------------------------------------


def case_bbox_filter():
    places = [
        _place(
            "p_in_hk", "Selected trong Hoàn Kiếm",
            place_type="museum", lat=21.030, lon=105.850,
            region_key="vn,ha-noi,hoan-kiem",
            tags=["culture"],
        ),
        # Catalog suggestion xa (Long Biên)
        _place(
            "p_in_lb", "Catalog ở Long Biên (xa bbox)",
            place_type="museum", lat=21.040, lon=105.880,
            region_key="vn,ha-noi,long-bien",
            tags=["culture"],
        ),
        _place(
            "p_in_hk_2", "Catalog trong Hoàn Kiếm",
            place_type="museum", lat=21.035, lon=105.855,
            region_key="vn,ha-noi,hoan-kiem",
            tags=["culture"],
        ),
    ]
    macro_plan = PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            PlaceSelectionDay(
                day=1, theme="BBox test",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture"],
                allocatedSelectedPlaceRefs=["p_in_hk"],
            ),
        ],
    )
    selected = [
        SelectedPlaceContext(
            placeId="p_in_hk", name="Selected trong Hoàn Kiếm",
            mustVisit=True, tags=["culture"],
        ),
    ]
    intent = TravelIntent(
        destination="Hà Nội", days=1, budget=BudgetLevel.medium,
        travelStyle="local", pace=TravelPace.balanced,
        interests=["culture"],
    )
    _run_case(
        "BBOX — selected HK, catalog có HK + xa (Long Biên)",
        macro_plan, selected, places, intent,
        allow_finder_suggestions=True,
    )


if __name__ == "__main__":
    case_fnd_002()
    case_user_problem()
    case_bbox_filter()