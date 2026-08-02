from app.modules.places.model import Place
from app.modules.plans.discovery.schema import DestinationDiscoveryRequest
from app.modules.plans.discovery.service import DestinationDiscoveryService
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class FakeDestinationRepository:
    def __init__(self, places: list[Place]) -> None:
        self.places = places

    def list_active_for_destination_discovery(
        self,
        *,
        limit: int = 50_000,
    ) -> list[Place]:
        return self.places[:limit]


def _place(
    place_id: str,
    *,
    city: str,
    region_key: str,
    place_type: str,
    tags: list[str],
    price_level: str,
) -> Place:
    return Place(
        id=place_id,
        name=f"{city} {place_type} {place_id}",
        city=city,
        country="Việt Nam",
        country_code="VN",
        place_type=place_type,
        region_key=region_key,
        status="active",
        data_confidence="high",
        metadata_json={
            "placeGroup": "food_drink" if place_type == "restaurant" else "attraction",
            "tags": tags,
            "priceLevel": price_level,
        },
    )


def test_destination_discovery_ranks_budget_interest_and_exposes_graph_coverage() -> None:
    places = [
        *[
            _place(
                f"hn-{index}",
                city="Hà Nội",
                region_key="vn,ha-noi,hoan-kiem",
                place_type="restaurant",
                tags=["food", "local_food"],
                price_level="$",
            )
            for index in range(8)
        ],
        *[
            _place(
                f"dn-{index}",
                city="Đà Nẵng",
                region_key="vn,da-nang,hai-chau",
                place_type="attraction",
                tags=["culture"],
                price_level="$$$$",
            )
            for index in range(8)
        ],
    ]
    service = DestinationDiscoveryService(FakeDestinationRepository(places))

    result = service.discover(
        DestinationDiscoveryRequest.model_validate(
            {
                "days": 3,
                "budget": {
                    "targetAmount": 3_000_000,
                    "currency": "VND",
                    "level": "low",
                },
                "interests": ["ẩm thực"],
            }
        )
    )

    assert result.proposals[0].region_key == "vn,ha-noi"
    assert result.proposals[0].matched_interests == ["ẩm thực"]
    assert result.proposals[0].budget_fit == "fits"
    assert result.proposals[0].knowledge_graph_available is True
    assert any("nơi xuất phát" in assumption for assumption in result.assumptions)


def test_destination_discovery_does_not_claim_transport_or_lodging_costs() -> None:
    places = [
        _place(
            f"hn-{index}",
            city="Hà Nội",
            region_key="vn,ha-noi",
            place_type="restaurant",
            tags=["food"],
            price_level="$",
        )
        for index in range(5)
    ]
    service = DestinationDiscoveryService(FakeDestinationRepository(places))

    result = service.discover(
        DestinationDiscoveryRequest.model_validate(
            {
                "days": 2,
                "budget": {"targetAmount": 2_000_000, "currency": "VND"},
                "budgetIncludesTransport": True,
                "budgetIncludesAccommodation": True,
            }
        )
    )

    assert len(result.warnings) == 2
    assert "activity" in result.assumptions[0]


def test_destination_discovery_api_uses_camel_case_contract(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            _place(
                f"api-hn-{index}",
                city="Hà Nội",
                region_key="vn,ha-noi,hoan-kiem",
                place_type="restaurant",
                tags=["food"],
                price_level="$",
            )
            for index in range(5)
        ]
    )
    db_session.commit()

    response = client.post(
        "/api/plans/destinations/discover",
        json={
            "days": 2,
            "budget": {"targetAmount": 2_000_000, "currency": "VND"},
            "interests": ["food"],
            "limit": 3,
        },
    )

    assert response.status_code == 200
    proposal = response.json()["proposals"][0]
    assert proposal["regionKey"] == "vn,ha-noi"
    assert proposal["estimatedCatalogActivityCost"] == 600_000
    assert proposal["knowledgeGraphAvailable"] is True
