from decimal import Decimal

from app.modules.places.model import Place
from app.modules.plans.dto.agent_contracts import PlannerResearchDraft
from app.modules.plans.trip_theme_planner.research_tool import (
    RepositoryPlannerResearchTool,
)


def test_research_tool_verifies_local_capabilities_and_nearby_regions() -> None:
    repository = FakeResearchRepository(
        [
            _place(
                "vung-tau-beach",
                "Bãi Sau",
                "beach",
                "vn,ba-ria-vung-tau,vung-tau",
                10.34,
                107.09,
                ["beach"],
            ),
            _place(
                "vung-tau-mountain",
                "Núi Lớn",
                "attraction",
                "vn,ba-ria-vung-tau,vung-tau",
                10.35,
                107.07,
                ["mountain", "hiking"],
            ),
            _place(
                "vung-tau-seafood",
                "Hải sản địa phương",
                "restaurant",
                "vn,ba-ria-vung-tau,vung-tau",
                10.34,
                107.08,
                ["seafood"],
            ),
            _place(
                "phan-thiet-camping",
                "Khu cắm trại ven biển",
                "campsite",
                "vn,binh-thuan,phan-thiet",
                10.93,
                108.10,
                ["camping", "beach"],
            ),
        ]
    )
    tool = RepositoryPlannerResearchTool(repository)
    draft = PlannerResearchDraft.model_validate(
        {
            "journeyStyle": "road_trip",
            "varietyStrategy": "Biển, hải sản và vận động ngoài trời.",
            "themeQueries": [
                {
                    "theme": "Ngày biển",
                    "capabilities": ["beach", "seafood", "hiking"],
                    "rationale": "Kiểm chứng các theme khác nhau.",
                }
            ],
            "expandBeyondRoot": True,
            "nearbyCapabilities": ["camping", "beach"],
            "maxDistanceKm": 200,
        }
    )

    result = tool.verify(
        draft,
        root_region_key="vn,ba-ria-vung-tau,vung-tau",
    )

    evidence = {
        item.capability: item for item in result.capability_evidence
    }
    assert evidence["beach"].supported is True
    assert evidence["seafood"].supported is True
    assert evidence["hiking"].supported is True
    assert evidence["hiking"].sample_places[0]["name"] == "Núi Lớn"
    assert result.nearby_regions[0].region_key == "vn,binh-thuan,phan-thiet"
    assert set(result.nearby_regions[0].matching_capabilities) == {
        "beach",
        "camping",
    }


def test_research_tool_does_not_claim_unsupported_capability() -> None:
    repository = FakeResearchRepository(
        [
            _place(
                "vung-tau-beach",
                "Bãi Sau",
                "beach",
                "vn,ba-ria-vung-tau,vung-tau",
                10.34,
                107.09,
                ["beach"],
            )
        ]
    )
    tool = RepositoryPlannerResearchTool(repository)
    draft = PlannerResearchDraft.model_validate(
        {
            "journeyStyle": "local_base",
            "varietyStrategy": "Kiểm tra khả năng leo núi.",
            "themeQueries": [
                {
                    "theme": "Leo núi",
                    "capabilities": ["hiking"],
                    "rationale": "Không được bịa capability.",
                }
            ],
        }
    )

    result = tool.verify(
        draft,
        root_region_key="vn,ba-ria-vung-tau,vung-tau",
    )

    assert result.capability_evidence[0].supported is False
    assert result.capability_evidence[0].active_place_count == 0
    assert "hiking" in result.warnings[0]


class FakeResearchRepository:
    def __init__(self, places: list[Place]) -> None:
        self.places = places

    def list_active_for_planner_research(
        self,
        region_key: str | None = None,
        *,
        limit: int = 5000,
    ) -> list[Place]:
        return [
            place
            for place in self.places
            if place.status == "active"
            and (
                region_key is None
                or place.region_key == region_key
                or place.region_key.startswith(f"{region_key},")
            )
        ][:limit]


def _place(
    place_id: str,
    name: str,
    place_type: str,
    region_key: str,
    latitude: float,
    longitude: float,
    tags: list[str],
) -> Place:
    return Place(
        id=place_id,
        name=name,
        place_type=place_type,
        region_key=region_key,
        status="active",
        latitude=Decimal(str(latitude)),
        longitude=Decimal(str(longitude)),
        data_confidence="high",
        opening_hours=[],
        metadata_json={"tags": tags},
    )
