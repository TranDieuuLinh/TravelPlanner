from fastapi import APIRouter

from app.integrations.llm.factory import get_llm_client

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("/planner-preview")
async def planner_preview(destination: str, days: int = 3, budget: str = "medium") -> dict[str, str]:
    client = get_llm_client()
    prompt = f"Destination: {destination}. Days: {days}. Budget: {budget}."
    draft = await client.generate_profile_plan(prompt)
    return {"draft": draft}
