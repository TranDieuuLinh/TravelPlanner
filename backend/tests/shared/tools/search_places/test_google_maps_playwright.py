from datetime import UTC, datetime

from app.modules.knowledge_graph.adapters.draft_places import PostgresDraftPlaceStore
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import PlaceProviderCandidate
from app.shared.tools.search_places.adapters import GoogleMapsPlaywrightSearch


def test_google_maps_url_identity_and_coordinates_are_stable() -> None:
    url = (
        "https://www.google.com/maps/place/Test/@21.028511,105.804817,17z/"
        "data=!4m6!3m5!1s0x3135:0xabc!8m2!3d21.028511!4d105.804817"
    )

    coordinates = GoogleMapsPlaywrightSearch.coordinates_from_url(url)

    assert coordinates == Coordinates(latitude=21.028511, longitude=105.804817)
    assert GoogleMapsPlaywrightSearch.provider_id_from_url(url) == (
        GoogleMapsPlaywrightSearch.provider_id_from_url(url)
    )
    assert len(GoogleMapsPlaywrightSearch.provider_id_from_url(url)) == 32


def test_coordinates_can_fall_back_to_google_data_tokens() -> None:
    coordinates = GoogleMapsPlaywrightSearch.coordinates_from_url(
        "https://maps.google.com/data=!3d21.028511!4d105.804817"
    )

    assert coordinates == Coordinates(latitude=21.028511, longitude=105.804817)


def test_coordinates_prefer_direction_destination_over_viewport() -> None:
    coordinates = GoogleMapsPlaywrightSearch.coordinates_from_url(
        "https://google.com/maps/dir//@21.02,105.80,17z/"
        "data=!1d105.8521484!2d21.0286669"
    )

    assert coordinates == Coordinates(latitude=21.0286669, longitude=105.8521484)


def test_google_category_is_normalized_without_creating_graph_relationships() -> None:
    normalize = GoogleMapsPlaywrightSearch._canonical_type

    assert normalize("Nhà hàng Việt Nam", None) == "restaurant"
    assert normalize("Coffee shop", None) == "drink_dessert"
    assert normalize("Museum", "attraction") == "travel_place"


def test_draft_store_maps_google_fields_to_property_rows() -> None:
    candidate = PlaceProviderCandidate(
        provider="google_maps_playwright",
        providerId="google-123",
        name="Museum",
        address="Hà Nội",
        coordinates=Coordinates(latitude=21.02, longitude=105.84),
        admIds=["adm1_vn_ha_noi"],
        admNames=["Hà Nội"],
        canonicalType="travel_place",
        rating=4.7,
        reviewCount=1200,
        tags=["Museum"],
        fetchedAt=datetime.now(UTC),
        verificationStatus="not_verified",
        sourceUrl="https://www.google.com/maps/place/example",
        providerMetadata={
            "phone": "0123456789",
            "website": "https://example.com",
            "weekly_opening_hours": "Thứ Hai, 08:00–17:00",
        },
    )

    properties = PostgresDraftPlaceStore._properties(candidate)

    assert properties["google_place_id"] == "google-123"
    assert properties["url_google_map"] == candidate.source_url
    assert properties["review_count"] == "1200"
    assert properties["phone"] == "0123456789"
    assert "weekly_opening_hours" in properties["meta_json"]
