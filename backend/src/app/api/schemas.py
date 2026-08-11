from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.explorer.public import ExplorerImageInput, ExplorerInput
from app.modules.information_finder.public import SourceReference
from app.modules.plan_editor.public import EditOperation
from app.modules.supervisor.public import SupervisorRoute
from app.shared.contracts.itinerary import Itinerary


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )


class InvokeRequest(ApiModel):
    thread_id: str = Field(min_length=1, max_length=200)
    message: str | None = Field(default=None, max_length=4000)
    urls: list[str] = Field(default_factory=list, max_length=20)
    images: list[ExplorerImageInput] = Field(default_factory=list, max_length=20)
    existing_itinerary: Itinerary | None = None
    edit_operation: EditOperation | None = None

    def model_post_init(self, __context) -> None:
        explorer_input = ExplorerInput(
            raw_prompt=self.message, urls=self.urls, images=self.images
        )
        self.message = explorer_input.raw_prompt
        self.urls = explorer_input.urls


class InvokeResponse(ApiModel):
    request_id: str
    route: SupervisorRoute
    response: str
    itinerary: Itinerary | None = None
    clarification_question: str | None = None
    warnings: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
