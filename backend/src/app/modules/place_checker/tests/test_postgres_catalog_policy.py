from app.modules.place_checker.adapters.postgres_catalog import PostgresPlaceCatalog
from app.shared.tools.search_places import PlaceProviderCandidate


def _candidate(identity: str, experience: str) -> PlaceProviderCandidate:
    return PlaceProviderCandidate(
        provider="knowledge_graph",
        entityId=identity,
        name=identity,
        canonicalType="travel_place",
        tags=["travel place", f"experience:{experience}"],
    )


def test_generic_travel_pool_caps_repeated_experience_groups() -> None:
    candidates = [
        _candidate("camp-1", "Cắm trại"),
        _candidate("camp-2", "Cắm trại"),
        _candidate("camp-3", "Cắm trại"),
        _candidate("museum", "Tham quan địa danh"),
        _candidate("temple", "Tham quan văn hóa và tín ngưỡng"),
    ]

    selected = PostgresPlaceCatalog._cap_tourism_experience_groups(candidates)

    assert [candidate.entity_id for candidate in selected] == [
        "camp-1",
        "camp-2",
        "museum",
        "temple",
    ]


def test_generic_travel_pool_rejects_non_tourism_service_tags() -> None:
    assert PostgresPlaceCatalog._has_tourism_experience(
        ["experience:Tham quan địa danh"]
    )
    assert not PostgresPlaceCatalog._has_tourism_experience(
        ["experience:Thư giãn và chăm sóc sức khỏe"]
    )
