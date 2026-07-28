from app.shared.contracts.plan_marketplace import (
    PlanCopyResult,
    PlanDaySummary,
    PlanMarketplaceGateway,
    PlanPreview,
    PlanPublishInfo,
)


class FakePlanMarketplaceGateway:
    def get_publish_info(self, plan_id: str, actor_id: int) -> PlanPublishInfo:
        return PlanPublishInfo(
            planId=plan_id,
            planVersionId="plan_version_03",
            ownerId=actor_id,
            title="Đà Nẵng và Hội An",
            destination="Đà Nẵng",
            days=4,
            status="locked",
            checkStatus="valid",
        )

    def get_preview(self, plan_version_id: str) -> PlanPreview:
        return PlanPreview(
            planVersionId=plan_version_id,
            title="Đà Nẵng và Hội An",
            destination="Đà Nẵng",
            days=4,
            highlights=["Sơn Trà", "Hội An"],
            daySummaries=[PlanDaySummary(day=1, theme="Biển và thành phố")],
        )

    def clone_for_buyer(
        self,
        plan_version_id: str,
        buyer_id: int,
        source_listing_version_id: str,
    ) -> PlanCopyResult:
        return PlanCopyResult(
            planId=f"buyer_plan_{buyer_id}",
            planVersionId="buyer_plan_version_01",
            sourcePlanVersionId=plan_version_id,
            sourceListingVersionId=source_listing_version_id,
        )


def test_fake_gateway_matches_shared_contract() -> None:
    gateway: PlanMarketplaceGateway = FakePlanMarketplaceGateway()

    publish_info = gateway.get_publish_info("plan_01", 12)
    preview = gateway.get_preview(publish_info.plan_version_id)
    copy = gateway.clone_for_buyer(publish_info.plan_version_id, 18, "listing_version_07")

    assert publish_info.model_dump(by_alias=True)["checkStatus"] == "valid"
    assert preview.model_dump(by_alias=True)["daySummaries"][0]["day"] == 1
    assert copy.source_plan_version_id == "plan_version_03"
