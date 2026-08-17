from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.auth.public import require_current_user
from app.modules.knowledge_graph.router import get_service, public_router


class PreviewService:
    async def entity_preview_by_id(self, entity_id: str) -> dict:
        return {
            "id": entity_id,
            "name": "Exact node",
            "entity_type": "Place",
            "description": "Resolved by ID.",
            "image_url": None,
            "details": {},
        }


def test_public_preview_resolves_the_encoded_entity_id_without_name_lookup() -> None:
    app = FastAPI()
    app.include_router(public_router)
    app.dependency_overrides[require_current_user] = lambda: object()
    app.dependency_overrides[get_service] = lambda: PreviewService()

    with TestClient(app) as http:
        response = http.get("/v1/knowledge-graph/entities/node%2Ftwo/preview")

    assert response.status_code == 200
    assert response.json()["id"] == "node/two"
