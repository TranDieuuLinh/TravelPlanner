from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.auth.adapters.in_memory import InMemoryUserRepository
from app.modules.auth.service import AuthService


class FakeKnowledgeGraphService:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.last_limits: dict[str, int] = {}
        self.entity_data = {
            "id": "restaurant_example",
            "canonical_name": "Example Restaurant",
            "entity_type": "Restaurant",
            "status": "active",
            "review_count": None,
            "created_at": now,
            "updated_at": now,
            "aliases": [],
            "alias_total": 0,
            "alias_has_more": False,
            "properties": [],
            "property_total": 0,
            "property_has_more": False,
            "relationships": [],
            "relationship_total": 0,
            "relationship_has_more": False,
        }

    async def entity(self, _entity_id: str, **limits):
        self.last_limits = limits
        return self.entity_data

    async def entity_filter_options(self) -> dict[str, list[str]]:
        return {
            "entity_types": ["City", "Restaurant"],
            "statuses": ["active", "draft"],
            "property_keys": ["description", "time_window"],
            "relationship_types": ["located_in", "special_experience"],
        }

    async def entity_preview(self, _name: str) -> dict:
        return {
            "id": "restaurant_example",
            "name": "Example Restaurant",
            "entity_type": "Restaurant",
            "description": "A sample place.",
            "image_url": "https://example.test/image.jpg",
            "details": {"address": "Hanoi"},
        }

    async def entity_preview_by_id(self, entity_id: str) -> dict:
        return {
            "id": entity_id,
            "name": "Example Restaurant",
            "entity_type": "Restaurant",
            "description": "A sample place.",
            "image_url": "https://example.test/image.jpg",
            "details": {"address": "Hanoi"},
        }


def admin_client() -> tuple[TestClient, FakeKnowledgeGraphService]:
    app = create_app()
    app.state.auth_service = AuthService(
        InMemoryUserRepository(),
        bootstrap_users=(
            [("admin@travelplanner.local", "TravelPlanner Admin", "Password123!", "admin")]
        ),
    )
    service = FakeKnowledgeGraphService()
    app.state.knowledge_graph_service = service
    return TestClient(app), service


def login(http: TestClient) -> None:
    response = http.post(
        "/auth/login",
        json={"email": "admin@travelplanner.local", "password": "Password123!"},
    )
    assert response.status_code == 200


def test_entity_detail_accepts_zero_child_limits() -> None:
    http, service = admin_client()
    with http:
        login(http)
        response = http.get(
            "/admin/knowledge-graph/entities/restaurant_example"
            "?alias_limit=0&property_limit=0&relationship_limit=0"
        )

    assert response.status_code == 200
    assert service.last_limits == {
        "alias_offset": 0,
        "alias_limit": 0,
        "property_offset": 0,
        "property_limit": 0,
        "relationship_offset": 0,
        "relationship_limit": 0,
    }


def test_entity_filter_options_are_read_from_service() -> None:
    http, _ = admin_client()
    with http:
        login(http)
        response = http.get("/admin/knowledge-graph/entities/filters")

    assert response.status_code == 200
    assert response.json() == {
        "entityTypes": ["City", "Restaurant"],
        "statuses": ["active", "draft"],
        "propertyKeys": ["description", "time_window"],
        "relationshipTypes": ["located_in", "special_experience"],
    }


def test_authenticated_user_can_read_entity_preview() -> None:
    http, _ = admin_client()
    with http:
        login(http)
        response = http.get("/v1/knowledge-graph/entity-preview?name=Example%20Restaurant")

    assert response.status_code == 200
    assert response.json()["imageUrl"] == "https://example.test/image.jpg"


def test_authenticated_user_can_read_entity_preview_by_id() -> None:
    http, _ = admin_client()
    with http:
        login(http)
        response = http.get("/v1/knowledge-graph/entities/restaurant_example/preview")

    assert response.status_code == 200
    assert response.json()["id"] == "restaurant_example"
