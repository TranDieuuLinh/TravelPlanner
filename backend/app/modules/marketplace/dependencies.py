from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import ACCESS_COOKIE, get_current_user
from app.modules.auth.security import ACCESS_TOKEN_TYPE, decode_token, token_user_id
from app.modules.marketplace.gateways.fake_plan_gateway import FakePlanMarketplaceGateway
from app.modules.marketplace.repository import MarketplaceRepository
from app.modules.marketplace.service import MarketplaceService
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.contracts.plan_marketplace import PlanMarketplaceGateway

_plan_gateway_instance = FakePlanMarketplaceGateway()


def get_plan_gateway() -> PlanMarketplaceGateway:
    return _plan_gateway_instance


def get_marketplace_repository(db: Annotated[Session, Depends(get_db)]) -> MarketplaceRepository:
    return MarketplaceRepository(db)


def get_marketplace_service(
    db: Annotated[Session, Depends(get_db)],
    repo: Annotated[MarketplaceRepository, Depends(get_marketplace_repository)],
    gateway: Annotated[PlanMarketplaceGateway, Depends(get_plan_gateway)],
) -> MarketplaceService:
    return MarketplaceService(db, repo, gateway)


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    try:
        payload = decode_token(token, ACCESS_TOKEN_TYPE)
        user = UserRepository(db).get_by_id(token_user_id(payload))
        if user and user.status == "active":
            return user
    except Exception:
        pass
    return None
