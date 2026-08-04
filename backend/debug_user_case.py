"""E2E debug case: "Hà Nội cuối tuần, ưu tiên món địa phương và văn hóa"

Đây là case user chỉ gửi raw text, không attach place nào.
Hệ thống phải:
  1. Parse intent → destination="Hà Nội", duration="weekend" (2 ngày), pace=balanced
  2. Tìm PlaceSelectionBlueprint
  3. Finder tự fill từ catalog (allow_finder_suggestions=True)
"""

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
    def __init__(self, repo):
        super().__init__(repo)
        self.calls: list[dict] = []
        self.all_search_results: list[list[str]] = []

    def search(self, *, region_key, target_tags, excluded_place_ids, limit, bbox_filter=None):
        raw = self.repository.list_for_finder(region_key, limit=limit)
        result = super().search(
            region_key=region_key,
            target_tags=target_tags,
            excluded_place_ids=excluded_place_ids,
            limit=limit,
            bbox_filter=bbox_filter,
        )
        self.calls.append({
            "region": region_key,
            "tags": list(target_tags),
            "excluded": set(excluded_place_ids),
            "bbox": bbox_filter,
            "candidate_count": len(raw),
            "candidate_ids": [p.id for p in raw],
            "result_ids": [p.place_id for p in result],
            "result_names": [p.name for p in result],
        })
        self.all_search_results.append([p.name for p in result])
        return result


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
    rating: float = 4.5,
) -> Place:
    place = Place(
        id=place_id, name=name, place_type=place_type,
        region_key=region_key, data_confidence="high",
        typical_duration_minutes=duration,
    )
    place.latitude = lat
    place.longitude = lon
    place.metadata_json = {}
    place.opening_hours = [{"openTime": "07:00", "closeTime": "22:00"}]
    place.rating = rating
    place.weather_sensitivity = "low"
    place.price_level = "mid_range"
    place.tags = tags or []
    return place


# ---------------------------------------------------------------------------
# Catalog mô phỏng Hà Nội: ~25 place trải khắp
# ---------------------------------------------------------------------------


def build_catalog() -> list[Place]:
    places = []
    # Hoàn Kiếm (bán kính trung tâm)
    places += [
        _place("p_hn_hm1", "Bún Chả Đắc Kim", place_type="restaurant",
               tags=["food", "local_cuisine"], lat=21.034, lon=105.851, duration=75, rating=4.7),
        _place("p_hn_hm2", "Phở Thìn Bờ Hồ", place_type="restaurant",
               tags=["food", "local_cuisine"], lat=21.024, lon=105.852, duration=45, rating=4.5),
        _place("p_hn_hm3", "Bún Thang Cầu Gỗ", place_type="restaurant",
               tags=["food", "local_cuisine"], lat=21.034, lon=105.852, duration=75, rating=4.6),
        _place("p_hn_hm4", "Cà phê Giảng", place_type="cafe",
               tags=["food", "coffee"], lat=21.027, lon=105.850, duration=45, rating=4.4),
        _place("p_hn_hm5", "Bánh Mì 25", place_type="restaurant",
               tags=["food"], lat=21.034, lon=105.853, duration=30, rating=4.5),

        _place("p_hn_hc1", "Văn Miếu Quốc Tử Giám", place_type="museum",
               tags=["culture", "history"], lat=21.027, lon=105.835, duration=120, rating=4.8),
        _place("p_hn_hc2", "Hoàng Thành Thăng Long", place_type="museum",
               tags=["culture", "history"], lat=21.035, lon=105.842, duration=150, rating=4.7),
        _place("p_hn_hc3", "Đền Quán Thánh", place_type="temple",
               tags=["culture", "spiritual"], lat=21.043, lon=105.847, duration=60, rating=4.5),
        _place("p_hn_hc4", "Chùa Trấn Quốc", place_type="temple",
               tags=["culture", "spiritual"], lat=21.046, lon=105.840, duration=60, rating=4.6),
        _place("p_hn_hc5", "Bảo tàng Phụ nữ Việt Nam", place_type="museum",
               tags=["culture"], lat=21.024, lon=105.844, duration=90, rating=4.4),
        _place("p_hn_hc6", "Hồ Hoàn Kiếm & Đền Ngọc Sơn", place_type="attraction",
               tags=["culture"], lat=21.029, lon=105.852, duration=120, rating=4.7),

        _place("p_hn_hs1", "Khách sạn Hanoi Pearl", place_type="hotel",
               tags=["accommodation"], lat=21.030, lon=105.850, duration=0, rating=4.3),
    ]
    # Ba Đình
    places += [
        _place("p_hn_bd1", "Bảo tàng Hồ Chí Minh", place_type="museum",
               region_key="vn,ha-noi,ba-dinh,ngoc-ha",
               tags=["culture", "history"], lat=21.037, lon=105.834, duration=120, rating=4.7),
        _place("p_hn_bd2", "Lăng Chủ tịch Hồ Chí Minh", place_type="monument",
               region_key="vn,ha-noi,ba-dinh,ngoc-ha",
               tags=["culture", "history"], lat=21.036, lon=105.834, duration=60, rating=4.6),
        _place("p_hn_bd3", "Chợ Đồng Xuân", place_type="market",
               region_key="vn,ha-noi,ba-dinh,ba-dinh",
               tags=["market", "shopping"], lat=21.038, lon=105.849, duration=90, rating=4.2),
        # Thêm nhà hàng Ba Đình (local_cuisine) — bị thiếu
        _place("p_hn_bd4", "Bún Riêu Cô Bách", place_type="restaurant",
               region_key="vn,ha-noi,ba-dinh,ba-dinh",
               tags=["food", "local_cuisine"], lat=21.038, lon=105.842, duration=60, rating=4.5),
        _place("p_hn_bd5", "Phở Bát Đàn - chi nhánh Liễu Giai", place_type="restaurant",
               region_key="vn,ha-noi,ba-dinh,ngoc-ha",
               tags=["food", "local_cuisine"], lat=21.034, lon=105.832, duration=45, rating=4.6),
    ]
    # Tây Hồ (xa, ~5km)
    places += [
        _place("p_hn_th1", "Chùa Trấn Quốc Tây Hồ", place_type="temple",
               region_key="vn,ha-noi,tay-ho",
               tags=["culture"], lat=21.046, lon=105.840, duration=60, rating=4.7),
        _place("p_hn_th2", "Phủ Tây Hồ", place_type="attraction",
               region_key="vn,ha-noi,tay-ho",
               tags=["culture"], lat=21.055, lon=105.825, duration=60, rating=4.5),
    ]
    # Long Biên (xa, ~5km)
    places += [
        _place("p_hn_lb1", "Cầu Long Biên", place_type="monument",
               region_key="vn,ha-noi,long-bien",
               tags=["culture", "history"], lat=21.045, lon=105.862, duration=45, rating=4.6),
    ]
    return places


def run(raw_request: str) -> None:
    print("=" * 80)
    print(f"RAW REQUEST: {raw_request!r}")
    print("=" * 80)

    places = build_catalog()
    repo = InMemoryFinderRepo(places)
    tool = LoggingTool(repo)
    finder = PlaceSelectorService(tool)
    user_status = UserStatus()

    # Intent do Explorer sẽ sinh: destination="Hà Nội", days=2, pace=balanced,
    # interests=["food", "culture"], weekend=True
    intent = TravelIntent(
        destination="Hà Nội",
        days=2,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["food", "culture"],
    )

    # PlaceSelectionBlueprint đơn giản (Planner sẽ sinh tự, nhưng để test Finder tôi hard-code)
    macro_plan = PlaceSelectionBlueprint(
        title="Hà Nội cuối tuần",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            PlaceSelectionDay(
                day=1, theme="Khám phá ẩm thực phố cổ",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["food"],
            ),
            PlaceSelectionDay(
                day=2, theme="Văn hóa lịch sử Ba Đình",
                targetArea="Ba Đình",
                targetRegionKey="vn,ha-noi,ba-dinh",
                focusTags=["culture"],
            ),
        ],
    )

    result = finder.fill_main_plan(
        macro_plan, intent, selected_places=[],
        user_status=user_status, allow_finder_suggestions=True,
    )

    # Bbox lookup
    print("\n=== BBox for each region ===")
    for rk in ["vn,ha-noi,hoan-kiem", "vn,ha-noi,ba-dinh"]:
        profile = finder._get_area_profile(rk)
        print(f"  {rk}: bbox={profile.bbox if profile else None}")

    print(f"\nStrategies: {[d.strategy for d in result.days]}")
    print(f"Warnings ({len(result.warnings)}):")
    for w in result.warnings:
        print(f"  - {w}")
    print(f"Unscheduled ({len(result.unscheduled_places)}):")
    for p in result.unscheduled_places:
        print(f"  - {p.name} ({p.reason_code})")

    print(f"\nSearch calls: {len(tool.calls)}")
    for i, c in enumerate(tool.calls, 1):
        bbox_str = f"bbox={c['bbox']}" if c["bbox"] else "bbox=NONE"
        print(
            f"  [{i}] region={c['region']!r} tags={c['tags']}\n"
            f"       raw={c['candidate_count']} {c['candidate_ids']}\n"
            f"       out={c['result_names']}"
        )

    print("\nFinal days:")
    for day in result.days:
        print(f"\n  Day {day.day}: {day.theme} (strategy={day.strategy})")
        for item in day.items:
            print(
                f"    [{item.time_window:>13s}] {item.role:<22s} | "
                f"{item.name!r:<45s} (source={item.source})"
            )


if __name__ == "__main__":
    run("Hà Nội cuối tuần, ưu tiên món địa phương và văn hóa")