from app.modules.place_checker.activity_pool_selection import select_activity_coverage
from app.modules.place_checker.evaluation_contract import PlaceEvaluationBatch
from app.modules.place_checker.pool_policy import ACCOMMODATION_POOL_TARGET
from app.modules.place_checker.scoring_contract import ScoredCandidate
from app.shared.tools.search_places.normalization import normalize_text


class CandidatePoolBalancer:
    @classmethod
    def select_entity_type_quotas(
        cls,
        ranked: list[ScoredCandidate],
        existing_places: PlaceEvaluationBatch,
        *,
        activity_target: int,
        food_target: int,
        entertainment_target: int,
    ) -> list[ScoredCandidate]:
        existing = {
            "travel_place": 0,
            "restaurant": 0,
            "entertainment": 0,
            "accommodation": 0,
        }
        for evaluation in existing_places.places:
            if not evaluation.planner_eligible or not evaluation.place.place_id:
                continue
            category = (
                evaluation.place.metadata.category
                if evaluation.place.metadata
                else None
            )
            existing[cls._entity_type(category)] += 1

        selected_keys: set[str] = set()
        for entity_type in (
            "travel_place",
            "restaurant",
            "entertainment",
            "accommodation",
        ):
            candidates = [
                item
                for item in ranked
                if cls._entity_type(item.candidate.category) == entity_type
            ]
            target = {
                "travel_place": activity_target,
                "restaurant": food_target,
                "entertainment": entertainment_target,
                "accommodation": ACCOMMODATION_POOL_TARGET,
            }[entity_type]
            limit = max(0, target - existing[entity_type])
            selected_for_type = (
                select_activity_coverage(candidates, limit)
                if entity_type == "travel_place"
                else cls.balance_categories(candidates, limit)
            )
            selected_keys.update(
                item.candidate.candidate_key for item in selected_for_type
            )
        selected = [
            item for item in ranked if item.candidate.candidate_key in selected_keys
        ]
        return [
            item.model_copy(update={"rank": position})
            for position, item in enumerate(selected, 1)
        ]

    @staticmethod
    def balance_categories(
        ranked: list[ScoredCandidate],
        limit: int,
    ) -> list[ScoredCandidate]:
        """Reserve discovery-group slots, then fill remaining slots by score."""
        if limit <= 0:
            return []
        if len(ranked) <= limit:
            return [
                item.model_copy(update={"rank": index})
                for index, item in enumerate(ranked, 1)
            ]

        groups: dict[str, list[ScoredCandidate]] = {}
        for item in ranked:
            key = item.candidate.pool_category or item.candidate.category or "unknown"
            groups.setdefault(key, []).append(item)
        ordered_groups = sorted(groups)
        selected: list[ScoredCandidate] = []
        index = 0
        while len(selected) < limit and ordered_groups:
            key = ordered_groups[index % len(ordered_groups)]
            group = groups[key]
            if group:
                selected.append(group.pop(0))
            else:
                ordered_groups.remove(key)
                if not ordered_groups:
                    break
                index -= 1
            index += 1
        return [
            item.model_copy(update={"rank": position})
            for position, item in enumerate(selected, 1)
        ]

    @staticmethod
    def _entity_type(category: str | None) -> str:
        normalized = normalize_text(category)
        if normalized == "restaurant":
            return "restaurant"
        if normalized in {"drink dessert", "drink_dessert", "entertainment"}:
            return "entertainment"
        if normalized == "accommodation":
            return "accommodation"
        return "travel_place"
