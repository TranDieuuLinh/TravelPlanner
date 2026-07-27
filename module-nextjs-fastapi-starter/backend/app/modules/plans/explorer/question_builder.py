from app.modules.plans.schema import ExplorerRequest


class ExplorerQuestionBuilder:
    def build(self, payload: ExplorerRequest) -> list[str]:
        questions: list[str] = []
        if not payload.interests:
            questions.append("What travel interests should this plan prioritize?")
        if not payload.must_visit_places:
            questions.append("Are there any must-visit places?")
        if not payload.constraints:
            questions.append("Do you have timing, mobility, food, or weather constraints?")
        return questions
