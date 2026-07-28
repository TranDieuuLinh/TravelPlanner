from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.marketplace.dependencies import get_marketplace_repository, get_plan_gateway
from app.modules.marketplace.repository import MarketplaceRepository
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.modules.payments.momo_adapter import MoMoAdapter
from app.shared.contracts.plan_marketplace import PlanMarketplaceGateway

_momo_adapter_instance = MoMoAdapter()


def get_momo_adapter() -> MoMoAdapter:
    return _momo_adapter_instance


def get_order_repository(db: Annotated[Session, Depends(get_db)]) -> OrderRepository:
    return OrderRepository(db)


def get_order_service(
    db: Annotated[Session, Depends(get_db)],
    repo: Annotated[OrderRepository, Depends(get_order_repository)],
    marketplace_repo: Annotated[MarketplaceRepository, Depends(get_marketplace_repository)],
    momo_adapter: Annotated[MoMoAdapter, Depends(get_momo_adapter)],
    plan_gateway: Annotated[PlanMarketplaceGateway, Depends(get_plan_gateway)],
) -> OrderService:
    return OrderService(db, repo, marketplace_repo, momo_adapter, plan_gateway)
