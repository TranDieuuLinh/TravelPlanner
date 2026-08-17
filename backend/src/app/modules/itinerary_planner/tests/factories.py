from typing import Any


def candidate(
    place_id: str,
    *,
    priority: str = "special_experience",
    opening_hours: Any = None,
    duration_minutes: int = 60,
    relationships: list[str] | None = None,
    image_urls: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "placeId": place_id,
        "name": place_id.replace("_", " ").title(),
        "coordinates": {"latitude": 21.0287, "longitude": 105.8522},
        "address": "Hanoi",
        "priority": priority,
        "notes": None,
        "tags": [" Local Experience ", "local-experience", "CULTURE"],
        "imageUrls": image_urls or [],
        "rating": 4.7,
        "reviewCount": 100,
        "durationMinutes": duration_minutes,
        "openingHours": opening_hours,
        "preferredTimeWindows": [],
        "price": {"cost": 0, "currency": "vnd"},
        "relationships": relationships or [],
    }


def food(
    place_id: str = "all_day_food",
    *,
    supported_meals: list[str] | None = None,
    opening_hours: Any = None,
    venue_type: str = "restaurant",
) -> dict[str, Any]:
    value = candidate(
        place_id,
        priority="special_near",
        opening_hours=opening_hours,
    )
    value["supportedMeals"] = supported_meals or [
        "breakfast",
        "lunch",
        "dinner",
    ]
    value["venueType"] = venue_type
    return value


def payload(
    *,
    days: int = 1,
    places: list[dict[str, Any]] | None = None,
    foods: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "trip": {
            "destination": "Hanoi",
            "days": days,
            "startDate": "2026-08-20",
            "timezone": "Asia/Ho_Chi_Minh",
            "people": 2,
            "budget": {"amount": 5_000_000, "currency": "VND"},
            "preferences": ["Culture", "local experience"],
        },
        "places": places or [],
        "food": foods if foods is not None else [food()],
        "upstreamWarnings": [],
    }
