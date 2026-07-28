from fastapi import APIRouter

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("/categories")
def categories() -> list[str]:
    return ["budget", "medium", "high", "food", "nature", "family", "creator-picks"]
