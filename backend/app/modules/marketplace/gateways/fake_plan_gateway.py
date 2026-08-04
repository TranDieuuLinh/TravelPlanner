from app.shared.contracts.plan_marketplace import (
    PlanCopyResult,
    PlanDaySummary,
    PlanMarketplaceGateway,
    PlanPreview,
    PlanPublishInfo,
)
from app.shared.errors import AppError


class FakePlanMarketplaceGateway(PlanMarketplaceGateway):
    def __init__(self) -> None:
        pass

    def get_publish_info(self, plan_id: str, actor_id: int) -> PlanPublishInfo:
        if plan_id == "plan_demo_valid":
            return PlanPublishInfo(
                planId="plan_demo_valid",
                planVersionId="plan_version_demo_valid_v1",
                ownerId=actor_id,
                title="Đà Nẵng & Hội An 4 ngày 3 đêm",
                destination="Đà Nẵng - Hội An",
                days=4,
                status="locked",
                checkStatus="valid",
            )
        elif plan_id == "plan_demo_draft":
            return PlanPublishInfo(
                planId="plan_demo_draft",
                planVersionId="plan_version_demo_draft_v1",
                ownerId=actor_id,
                title="Phú Quốc nghỉ dưỡng 3 ngày",
                destination="Phú Quốc",
                days=3,
                status="draft",
                checkStatus="valid",
            )
        elif plan_id == "plan_demo_invalid":
            return PlanPublishInfo(
                planId="plan_demo_invalid",
                planVersionId="plan_version_demo_invalid_v1",
                ownerId=actor_id,
                title="Sapa trải nghiệm mạo hiểm 2 ngày",
                destination="Sapa",
                days=2,
                status="locked",
                checkStatus="invalid",
            )
        elif plan_id == "plan_demo_other_user":
            return PlanPublishInfo(
                planId="plan_demo_other_user",
                planVersionId="plan_version_demo_other_v1",
                ownerId=99999,  # different user
                title="Hà Nội ẩm thực phố cổ 2 ngày",
                destination="Hà Nội",
                days=2,
                status="locked",
                checkStatus="valid",
            )
        else:
            # Dynamic fallback for generic plan_id tests
            return PlanPublishInfo(
                planId=plan_id,
                planVersionId=f"{plan_id}_v1",
                ownerId=actor_id,
                title=f"Lịch trình {plan_id}",
                destination="Điểm đến demo",
                days=3,
                status="locked",
                checkStatus="valid",
            )

    def get_preview(self, plan_version_id: str) -> PlanPreview:
        return PlanPreview(
            planVersionId=plan_version_id,
            title="Lịch trình trải nghiệm đầy đủ",
            destination="Đà Nẵng - Hội An",
            days=4,
            highlights=["Check-in Cầu Vàng Bà Nà Hills", "Thưởng thức Cao Lầu phố cổ Hội An", "Ngắm rồng phun lửa Cầu Rồng"],
            daySummaries=[
                PlanDaySummary(day=1, theme="Đón sân bay & Dạo biển Mỹ Khê"),
                PlanDaySummary(day=2, theme="Khám phá Bà Nà Hills & Cầu Vàng"),
                PlanDaySummary(day=3, theme="Tham quan phố cổ Hội An & Thả đèn hoa đăng"),
                PlanDaySummary(day=4, theme="Mua sắm chợ Hàn & Tiễn sân bay"),
            ],
        )

    def clone_for_buyer(
        self,
        plan_version_id: str,
        buyer_id: int,
        source_listing_version_id: str,
    ) -> PlanCopyResult:
        return PlanCopyResult(
            planId=f"buyer_plan_{buyer_id}_{plan_version_id[:8]}",
            planVersionId=f"buyer_version_{buyer_id}_1",
            sourcePlanVersionId=plan_version_id,
            sourceListingVersionId=source_listing_version_id,
        )

    def list_publishable_plans(self, actor_id: int) -> list[PlanPublishInfo]:
        return [
            self.get_publish_info("plan_demo_valid", actor_id),
            self.get_publish_info("plan_demo_draft", actor_id),
            self.get_publish_info("plan_demo_invalid", actor_id),
        ]
