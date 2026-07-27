from app.modules.plans.domain.entities import TravelIntent
from app.modules.plans.explorer.preference_parser import PreferenceParser
from app.modules.plans.explorer.question_builder import ExplorerQuestionBuilder
from app.modules.plans.schema import ExplorerRequest


class ExplorerService:
    def __init__(
        self,
        parser: PreferenceParser | None = None,
        question_builder: ExplorerQuestionBuilder | None = None,
    ) -> None:
        self.parser = parser or PreferenceParser()
        self.question_builder = question_builder or ExplorerQuestionBuilder()

    def explore(self, payload: ExplorerRequest) -> TravelIntent:
        return TravelIntent(
            destination=payload.destination.strip(),
            days=payload.days,
            budget=payload.budget,
            travelStyle=payload.travel_style.strip(),
            pace=payload.pace,
            interests=self.parser.normalize(payload.interests),
            mustVisitPlaces=[place.strip() for place in payload.must_visit_places if place.strip()],
            avoidPlaces=[place.strip() for place in payload.avoid_places if place.strip()],
            constraints=[constraint.strip() for constraint in payload.constraints if constraint.strip()],
            clarifyingQuestions=self.question_builder.build(payload),
        )
