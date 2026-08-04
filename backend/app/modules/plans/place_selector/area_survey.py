"""Area Survey Tool - Khảo sát khu vực để điều chỉnh skeleton planning."""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.plans.place_selector.place_tool import (
        SelectablePlace,
        PlaceSelectionTool,
    )


from app.modules.plans.trip_theme_planner.opening_hours_parser import (  # noqa: E402
    extract_time_intervals,
    is_24_hours,
)


@dataclass(frozen=True)
class AreaProfile:
    """Profile khảo sát khu vực - dùng để điều chỉnh skeleton planning."""

    region_key: str
    place_count: int

    # Phân bố loại hình (category → count)
    distribution: dict[str, int]

    # Khoảng cách & mật độ
    avg_distance_km: float
    bbox: tuple[float, float, float, float] | None  # (min_lat, min_lon, max_lat, max_lon)
    estimated_walkability: str  # "high" | "medium" | "low"

    # Giờ hoạt động
    typical_hours: str  # "morning_focused" | "evening_focused" | "all_day"
    open_late_ratio: float  # % places mở > 21:00

    # Chất lượng
    avg_rating: float
    highly_rated_count: int  # places rating >= 4.5
    total_reviews: int

    # Chi phí
    dominant_price_level: str  # "budget" | "mid_range" | "premium"
    price_distribution: dict[str, int]

    # Đa dạng
    category_entropy: float  # Shannon entropy
    unique_categories: int
    has_food_scene: bool
    has_nature: bool
    has_culture: bool

    # Ước lượng thời gian (Core metric cho skeleton)
    avg_duration_per_place_minutes: float
    recommended_stops_per_day: int  # Số stops khuyến nghị/ngày

    # Insights
    insights: tuple[str, ...]


@dataclass(frozen=True)
class AreaSurveyResult:
    region_key: str
    profile: AreaProfile
    top_places_by_rating: tuple[SelectablePlace, ...]
    top_places_by_reviews: tuple[SelectablePlace, ...]
    survey_method: str = "catalog"


class AreaSurveyService:
    """Service khảo sát khu vực dựa trên places trong catalog."""

    # Ngưỡng cho các quyết định
    HIGHLY_RATED_THRESHOLD = 4.5
    WALKABILITY_HIGH_KM = 0.5  # avg distance < 0.5km = walkable
    WALKABILITY_MEDIUM_KM = 1.0  # avg distance < 1km = medium

    # Ngưỡng stops per day theo mật độ
    STOPS_SPARSE = 3
    STOPS_MEDIUM = 4
    STOPS_DENSE = 5

    # Số lượng top places giữ lại khi xếp hạng
    TOP_PLACES_LIMIT = 10

    def __init__(
        self,
        place_tool: PlaceSelectionTool,
        *,
        max_survey_places: int = 500,
    ) -> None:
        self.place_tool = place_tool
        self.max_survey_places = max_survey_places

    def survey(self, region_key: str) -> AreaSurveyResult:
        """Khảo sát khu vực và trả về AreaProfile."""
        # Load places từ catalog
        places = self.place_tool.search(
            region_key=region_key,
            target_tags=[],  # Lấy tất cả categories
            excluded_place_ids=set(),
            limit=self.max_survey_places,
        )

        if not places:
            return self._empty_result(region_key)

        profile = self._compute_profile(region_key, places)

        # Filter: chỉ giữ place có id (giữ nguyên hiện trạng)
        rankable = tuple(p for p in places if p.place_id is not None)

        # Place thiếu rating rơi về cuối list (top đầu chỉ chứa place có rating thật).
        def rating_sort_key(p: SelectablePlace) -> tuple:
            rating = self._get_rating(p)
            rating_rank = -rating if rating is not None else float("inf")
            review_rank = -self._get_review_count(p)
            return (rating_rank, review_rank, p.name.casefold())

        # Sort theo review_count, rating làm tie-breaker.
        # Place thiếu rating được xếp SAU place có rating (ưu tiên thông tin thật).
        def review_sort_key(p: SelectablePlace) -> tuple:
            review_rank = -self._get_review_count(p)
            rating = self._get_rating(p)
            rating_rank = -rating if rating is not None else float("inf")
            return (review_rank, rating_rank, p.name.casefold())

        top_places_by_rating = tuple(
            sorted(rankable, key=rating_sort_key)[: self.TOP_PLACES_LIMIT]
        )
        top_places_by_reviews = tuple(
            sorted(rankable, key=review_sort_key)[: self.TOP_PLACES_LIMIT]
        )

        return AreaSurveyResult(
            region_key=region_key,
            profile=profile,
            top_places_by_rating=top_places_by_rating,
            top_places_by_reviews=top_places_by_reviews,
            survey_method="catalog",
        )

    def _compute_profile(
        self,
        region_key: str,
        places: list[SelectablePlace],
    ) -> AreaProfile:
        """Compute AreaProfile từ list of SelectablePlace."""
        place_count = len(places)

        # 1. Distribution - phân bố theo category
        distribution = self._compute_distribution(places)

        # 2. Geographic metrics
        coords = [
            (p.latitude, p.longitude)
            for p in places
            if p.latitude is not None and p.longitude is not None
        ]
        avg_distance_km = self._compute_avg_distance(coords)
        bbox = self._compute_bbox(coords)
        estimated_walkability = self._compute_walkability(avg_distance_km)

        # 3. Hours metrics
        open_late_ratio = self._compute_open_late_ratio(places)
        typical_hours = self._compute_typical_hours(places, open_late_ratio)

        # 4. Quality metrics
        ratings = [self._get_rating(p) for p in places if self._get_rating(p) is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
        highly_rated_count = sum(1 for r in ratings if r >= self.HIGHLY_RATED_THRESHOLD)
        total_reviews = sum(self._get_review_count(p) for p in places)

        # 5. Price metrics
        price_distribution = self._compute_price_distribution(places)
        dominant_price_level = self._compute_dominant_price(price_distribution)

        # 6. Diversity metrics
        category_entropy = self._compute_entropy(distribution)
        unique_categories = len(distribution)
        has_food_scene = "food_drink" in distribution and distribution["food_drink"] >= 3
        has_nature = "nature" in distribution and distribution["nature"] >= 2
        has_culture = "attraction" in distribution and distribution["attraction"] >= 2

        # 7. Time estimates
        durations = [
            p.typical_duration_minutes
            for p in places
            if p.typical_duration_minutes is not None
        ]
        avg_duration_per_place_minutes = (
            sum(durations) / len(durations) if durations else 60.0
        )
        recommended_stops_per_day = self._compute_stops_per_day(
            avg_distance_km,
            estimated_walkability,
            place_count,
        )

        # 8. Generate insights
        insights = self._generate_insights(
            distribution=distribution,
            avg_rating=avg_rating,
            highly_rated_count=highly_rated_count,
            avg_distance_km=avg_distance_km,
            estimated_walkability=estimated_walkability,
            typical_hours=typical_hours,
            has_food_scene=has_food_scene,
            has_nature=has_nature,
            has_culture=has_culture,
            recommended_stops_per_day=recommended_stops_per_day,
        )

        return AreaProfile(
            region_key=region_key,
            place_count=place_count,
            distribution=distribution,
            avg_distance_km=round(avg_distance_km, 2),
            bbox=bbox,
            estimated_walkability=estimated_walkability,
            typical_hours=typical_hours,
            open_late_ratio=round(open_late_ratio, 2),
            avg_rating=round(avg_rating, 2),
            highly_rated_count=highly_rated_count,
            total_reviews=total_reviews,
            dominant_price_level=dominant_price_level,
            price_distribution=price_distribution,
            category_entropy=round(category_entropy, 3),
            unique_categories=unique_categories,
            has_food_scene=has_food_scene,
            has_nature=has_nature,
            has_culture=has_culture,
            avg_duration_per_place_minutes=round(avg_duration_per_place_minutes, 0),
            recommended_stops_per_day=recommended_stops_per_day,
            insights=insights,
        )

    def _compute_distribution(self, places: list[SelectablePlace]) -> dict[str, int]:
        """Phân bố places theo semantic category."""
        from app.modules.plans.place_selector.place_tool import place_category

        distribution: dict[str, int] = {}
        for place in places:
            category = place_category(place)
            if category is None:
                category = "other"
            distribution[category] = distribution.get(category, 0) + 1
        return distribution

    def _compute_avg_distance(self, coords: list[tuple[float, float]]) -> float:
        """Tính khoảng cách trung bình giữa các điểm (km)."""
        if len(coords) < 2:
            return 0.0

        total_distance = 0.0
        count = 0

        # Use a stable evenly-spaced sample to keep area profiles reproducible.
        sample_size = min(50, len(coords))
        if sample_size == len(coords):
            sampled = coords
        else:
            indexes = [
                round(index * (len(coords) - 1) / (sample_size - 1))
                for index in range(sample_size)
            ]
            sampled = [coords[index] for index in indexes]
        for i in range(len(sampled)):
            for j in range(i + 1, len(sampled)):
                total_distance += self._haversine_km(sampled[i], sampled[j])
                count += 1

        return total_distance / count if count > 0 else 0.0

    def _haversine_km(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> float:
        """Tính khoảng cách Haversine giữa 2 tọa độ (km)."""
        lat1, lon1 = map(radians, origin)
        lat2, lon2 = map(radians, destination)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        return 6371 * 2 * asin(sqrt(a))

    def _compute_bbox(
        self,
        coords: list[tuple[float, float]],
    ) -> tuple[float, float, float, float] | None:
        """Tính bounding box từ list tọa độ."""
        if not coords:
            return None

        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]

        return (
            min(lats),
            min(lons),
            max(lats),
            max(lons),
        )

    def _compute_walkability(self, avg_distance_km: float) -> str:
        """Ước lượng mức độ walkable dựa trên avg distance."""
        if avg_distance_km <= self.WALKABILITY_HIGH_KM:
            return "high"
        elif avg_distance_km <= self.WALKABILITY_MEDIUM_KM:
            return "medium"
        else:
            return "low"

    def _compute_open_late_ratio(self, places: list[SelectablePlace]) -> float:
        """Tính tỷ lệ places mở sau 21:00."""
        late_opening_count = 0
        has_hours_count = 0

        for place in places:
            if not place.opening_hours:
                continue
            has_hours_count += 1

            intervals = extract_time_intervals(place.opening_hours)
            if not intervals:
                continue
            if is_24_hours(place.opening_hours):
                late_opening_count += 1
                continue
            if any(self._is_late_evening(end) for _, end in intervals):
                late_opening_count += 1

        return (
            late_opening_count / has_hours_count
            if has_hours_count > 0 else 0.5
        )

    def _is_late_evening(self, end_minutes: int) -> bool:
        """Check if a closing minute-of-day is at or after 21:00."""

        normalised = end_minutes if end_minutes <= 24 * 60 else end_minutes - 24 * 60
        return normalised >= 21 * 60

    def _compute_typical_hours(
        self,
        places: list[SelectablePlace],
        open_late_ratio: float,
    ) -> str:
        """Xác định khu vực tập trung vào khung giờ nào."""
        early_open_count = 0
        has_hours_count = 0

        for place in places:
            if not place.opening_hours:
                continue
            has_hours_count += 1
            intervals = extract_time_intervals(place.opening_hours)
            if not intervals:
                continue
            if is_24_hours(place.opening_hours):
                early_open_count += 1
                continue
            if any(self._is_early_morning(start) for start, _ in intervals):
                early_open_count += 1

        early_open_ratio = (
            early_open_count / has_hours_count
            if has_hours_count > 0 else 0.5
        )

        # Decision logic
        if early_open_ratio > 0.4:
            return "morning_focused"
        elif open_late_ratio > 0.4:
            return "evening_focused"
        else:
            return "all_day"

    def _is_early_morning(self, start_minutes: int) -> bool:
        """Check if an opening minute-of-day is at or before 08:00."""

        return 0 <= start_minutes <= 8 * 60

    def _get_rating(self, place: SelectablePlace) -> float | None:
        """Return the place rating from the dedicated field if available."""

        if place.rating is not None:
            return float(place.rating)
        return None

    def _get_review_count(self, place: SelectablePlace) -> int:
        """Return the place review count from the dedicated field."""

        return int(place.review_count or 0)

    def _compute_price_distribution(self, places: list[SelectablePlace]) -> dict[str, int]:
        """Phân bố theo mức giá."""
        distribution: dict[str, int] = {"free": 0, "budget": 0, "mid_range": 0, "premium": 0}

        for place in places:
            price = (place.price_level or "mid_range").casefold()
            if price in {"free", "budget", "mid_range", "premium"}:
                distribution[price] += 1
            elif price in {"$", "low", "cheap"}:
                distribution["budget"] += 1
            elif price in {"$$", "moderate", "medium"}:
                distribution["mid_range"] += 1
            elif price in {"$$$", "$$$$", "high", "expensive", "luxury"}:
                distribution["premium"] += 1

        return distribution

    def _compute_dominant_price(self, price_distribution: dict[str, int]) -> str:
        """Xác định mức giá chiếm ưu thế."""
        if not price_distribution:
            return "unknown"

        return max(price_distribution.items(), key=lambda x: x[1])[0]

    def _compute_entropy(self, distribution: dict[str, int]) -> float:
        """Tính Shannon entropy của phân bố categories."""
        if not distribution:
            return 0.0

        total = sum(distribution.values())
        if total == 0:
            return 0.0

        entropy = 0.0
        for count in distribution.values():
            if count > 0:
                p = count / total
                entropy -= p * (p ** 0.5 if p < 0.0001 else __import__("math").log2(p))

        return entropy

    def _compute_stops_per_day(
        self,
        avg_distance_km: float,
        estimated_walkability: str,
        place_count: int,
    ) -> int:
        """Tính số stops khuyến nghị per day."""
        # Base stops theo mật độ
        if place_count < 10:
            base_stops = self.STOPS_SPARSE
        elif place_count < 50:
            base_stops = self.STOPS_MEDIUM
        else:
            base_stops = self.STOPS_DENSE

        # Điều chỉnh theo walkability
        if estimated_walkability == "high":
            return base_stops  # Giữ nguyên - walkable
        elif estimated_walkability == "medium":
            return max(2, base_stops - 1)  # Giảm 1 vì cần transport
        else:
            return max(2, base_stops - 2)  # Giảm 2 vì sparse + transport

    def _generate_insights(
        self,
        distribution: dict[str, int],
        avg_rating: float,
        highly_rated_count: int,
        avg_distance_km: float,
        estimated_walkability: str,
        typical_hours: str,
        has_food_scene: bool,
        has_nature: bool,
        has_culture: bool,
        recommended_stops_per_day: int,
    ) -> tuple[str, ...]:
        """Generate human-readable insights về khu vực."""
        insights: list[str] = []

        # Về mật độ
        if estimated_walkability == "high":
            insights.append("Khu vực có mật độ cao, thích hợp đi bộ giữa các điểm.")
        elif estimated_walkability == "medium":
            insights.append("Khu vực phân tán vừa phải, cần dự kiến thời gian di chuyển.")
        else:
            insights.append("Khu vực rộng, nên sử dụng phương tiện di chuyển giữa các điểm.")

        # Về thời gian
        if typical_hours == "morning_focused":
            insights.append("Khu vực tập trung hoạt động buổi sáng, nên khởi hành sớm.")
        elif typical_hours == "evening_focused":
            insights.append("Khu vực sôi động về đêm, phù hợp cho kế hoạch buổi chiều/tối.")
        else:
            insights.append("Khu vực hoạt động cả ngày, linh hoạt về thời gian.")

        # Về chất lượng
        if highly_rated_count >= 5:
            insights.append(f"Có {highly_rated_count} địa điểm được đánh giá cao (≥4.5 sao).")
        elif avg_rating < 3.5:
            insights.append("Cần kiểm chứng thêm về chất lượng các địa điểm tại đây.")

        # Về ẩm thực
        if has_food_scene:
            food_count = distribution.get("food_drink", 0)
            insights.append(f"Có {food_count} địa điểm ẩm thực, thuận tiện cho việc ăn uống.")

        # Về thiên nhiên
        if has_nature:
            insights.append("Khu vực có các địa điểm thiên nhiên, phù hợp cho outdoor activities.")

        # Về văn hóa
        if has_culture:
            insights.append("Nhiều địa điểm văn hóa, di tích lịch sử.")

        # Về số stops
        insights.append(
            f"Khuyến nghị khoảng {recommended_stops_per_day} điểm dừng/ngày cho khu vực này."
        )

        return tuple(insights)

    def _empty_result(self, region_key: str) -> AreaSurveyResult:
        """Trả về empty result khi không có places."""
        return AreaSurveyResult(
            region_key=region_key,
            profile=AreaProfile(
                region_key=region_key,
                place_count=0,
                distribution={},
                avg_distance_km=0.0,
                bbox=None,
                estimated_walkability="unknown",
                typical_hours="all_day",
                open_late_ratio=0.0,
                avg_rating=0.0,
                highly_rated_count=0,
                total_reviews=0,
                dominant_price_level="unknown",
                price_distribution={},
                category_entropy=0.0,
                unique_categories=0,
                has_food_scene=False,
                has_nature=False,
                has_culture=False,
                avg_duration_per_place_minutes=60.0,
                recommended_stops_per_day=3,
                insights=("Chưa có dữ liệu địa điểm cho khu vực này.",),
            ),
            top_places_by_rating=(),
            top_places_by_reviews=(),
            survey_method="empty",
        )
