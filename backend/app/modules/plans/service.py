from app.modules.plans.domain.entities import Plan
from app.modules.plans.explorer.response_formatter import ExploreResponseFormatter
from app.modules.plans.explorer.schema import ExploreTripSpecInput, FullExploreRequest, ExploreResponse
from app.modules.plans.explorer.tools.image_ocr import ImageOcrService, ImageUploadPayload
from app.modules.plans.explorer.tools.url_reels.schema import UrlReelInput
from app.modules.plans.explorer.tools.url_reels.service import UrlReelExtractionService
from app.modules.plans.repository import PlanRepository
from app.modules.plans.schema import BackupPlanCreate, FeatureMapItem, MainPlanCreate, PlanBundleRead
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow


class PlanService:
    def __init__(
        self,
        repository: PlanRepository,
        explore_formatter: ExploreResponseFormatter,
        main_workflow: MainPlanWorkflow,
        backup_workflow: BackupPlanWorkflow,
        image_ocr: ImageOcrService | None = None,
        url_reels: UrlReelExtractionService | None = None,
    ) -> None:
        self.repository = repository
        self.explore_formatter = explore_formatter
        self.main_workflow = main_workflow
        self.backup_workflow = backup_workflow
        self.image_ocr = image_ocr
        self.url_reels = url_reels or UrlReelExtractionService()

    def feature_map(self) -> list[FeatureMapItem]:
        return [
            FeatureMapItem(stage="explore", feature="Explorer", description="Clarify destination, budget, pace, interests, and constraints."),
            FeatureMapItem(stage="create", feature="Planner", description="Generate MacroPlan and DayBriefs for the main itinerary."),
            FeatureMapItem(stage="fill", feature="Finder", description="Choose day windows, fill places, and commit each day."),
            FeatureMapItem(stage="check", feature="CheckOverall", description="Review weather, transport, availability, and plan risks."),
            FeatureMapItem(stage="backup", feature="Backup Planner", description="Create a separate backup plan without mutating the locked main plan."),
        ]

    async def explore_full(self, payload: FullExploreRequest) -> ExploreResponse:
        url_reel_results = [
            self.url_reels.extract(
                UrlReelInput(url=url, destination=payload.destination)
            )
            for url in payload.urls
        ]
        return await self.explore_formatter.format(
            payload,
            url_reel_results=url_reel_results,
        )

    async def explore_from_intake(
        self,
        *,
        raw_request: str,
        destination: str,
        urls: list[str],
        images: list[ImageUploadPayload],
        trip_spec: ExploreTripSpecInput | None = None,
    ) -> ExploreResponse:
        image_contexts = []
        try:
            if images:
                if self.image_ocr is None:
                    raise RuntimeError("Image OCR is not configured.")
                image_contexts = await self.image_ocr.extract_many(
                    images,
                    destination=destination,
                )

            return await self.explore_full(
                FullExploreRequest(
                    rawRequest=raw_request,
                    destination=destination,
                    urls=urls,
                    tripSpec=trip_spec or ExploreTripSpecInput(),
                    imageContexts=image_contexts,
                )
            )
        finally:
            for image in images:
                image.clear_data()

    async def create_main_plan(self, payload: MainPlanCreate) -> Plan:
        plan = await self.main_workflow.run(payload)
        self.repository.save(plan)
        return plan

    async def create_backup_plan(self, plan_id: str, payload: BackupPlanCreate) -> PlanBundleRead:
        main_plan = self.repository.get(plan_id)
        backup_plan, validation = await self.backup_workflow.run(main_plan, payload)
        self.repository.save(backup_plan)
        return PlanBundleRead(
            mainPlan=main_plan.model_dump(by_alias=True),
            backupPlan=backup_plan.model_dump(by_alias=True),
            validation=validation.model_dump(by_alias=True),
        )
