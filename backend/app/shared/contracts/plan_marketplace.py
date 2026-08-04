from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class PlanPublishInfo(BaseModel):
    plan_id: str = Field(alias="planId")
    plan_version_id: str = Field(alias="planVersionId")
    owner_id: int = Field(alias="ownerId")
    title: str
    destination: str
    days: int
    status: str
    check_status: str = Field(alias="checkStatus")

    model_config = ConfigDict(populate_by_name=True)


class PlanDaySummary(BaseModel):
    day: int
    theme: str


class PlanPreview(BaseModel):
    plan_version_id: str = Field(alias="planVersionId")
    title: str
    destination: str
    days: int
    highlights: list[str]
    day_summaries: list[PlanDaySummary] = Field(alias="daySummaries")

    model_config = ConfigDict(populate_by_name=True)


class PlanCopyResult(BaseModel):
    plan_id: str = Field(alias="planId")
    plan_version_id: str = Field(alias="planVersionId")
    source_plan_version_id: str = Field(alias="sourcePlanVersionId")
    source_listing_version_id: str = Field(alias="sourceListingVersionId")

    model_config = ConfigDict(populate_by_name=True)


class PlanMarketplaceGateway(Protocol):
    def get_publish_info(self, plan_id: str, actor_id: int) -> PlanPublishInfo: ...

    def get_preview(self, plan_version_id: str) -> PlanPreview: ...

    def clone_for_buyer(
        self,
        plan_version_id: str,
        buyer_id: int,
        source_listing_version_id: str,
    ) -> PlanCopyResult: ...
