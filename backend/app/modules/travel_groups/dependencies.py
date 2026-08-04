from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.travel_groups.repository import TravelGroupRepository
from app.modules.travel_groups.service import TravelGroupService


def get_travel_group_service(
    db: Annotated[Session, Depends(get_db)],
) -> TravelGroupService:
    return TravelGroupService(db, TravelGroupRepository(db))
