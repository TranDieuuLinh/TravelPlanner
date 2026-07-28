from fastapi import APIRouter

from app.modules.marketplace.admin_router import admin_router
from app.modules.marketplace.creator_router import creator_router
from app.modules.marketplace.public_router import public_router

router = APIRouter()

router.include_router(creator_router)
router.include_router(public_router)
router.include_router(admin_router)


@router.get("/marketplace/categories", tags=["marketplace"])
def categories() -> list[str]:
    return ["budget", "medium", "high", "food", "nature", "family", "creator-picks"]
