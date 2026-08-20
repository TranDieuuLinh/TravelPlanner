from app.modules.place_checker.evaluation.contract import PlaceEvaluationBatch
from app.modules.place_checker.planning.category import planner_category_for_candidate
from app.modules.place_checker.evaluation.price_policy import has_planner_cost
from app.modules.place_checker.selection.pool_policy import ACCOMMODATION_POOL_TARGET
from app.modules.place_checker.scoring.contract import ScoredCandidate


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
        drink_dessert_target: int,
    ) -> list[ScoredCandidate]:
        existing = {
            "travel_place": 0,
            "restaurant": 0,
            "drink_dessert": 0,
            "entertainment": 0,
            "accommodation": 0,
        }
        for evaluation in existing_places.places:
            if (
                not evaluation.planner_eligible
                or not evaluation.place.place_id
                or not cls._has_handoff_metadata(evaluation)
            ):
                continue
            category = (
                evaluation.place.metadata.category
                if evaluation.place.metadata
                else None
            )
            metadata = evaluation.place.metadata
            existing[
                cls._entity_type(
                    category,
                    name=evaluation.place.canonical_name,
                    tags=metadata.tags if metadata else (),
                    pool_category=cls._pool_category(metadata.tags if metadata else ()),
                    context=(
                        metadata.source_note.text
                        if metadata and metadata.source_note
                        else None
                    ),
                )
            ] += 1

        selected_keys: set[str] = set()
        for entity_type in (
            "travel_place",
            "restaurant",
            "drink_dessert",
            "entertainment",
            "accommodation",
        ):
            candidates = [
                item
                for item in ranked
                if cls._entity_type(
                    item.candidate.category,
                    name=item.candidate.canonical_name,
                    tags=item.candidate.tags,
                    pool_category=item.candidate.pool_category,
                )
                == entity_type
            ]
            target = {
                "travel_place": activity_target,
                "restaurant": food_target,
                "drink_dessert": drink_dessert_target,
                "entertainment": entertainment_target,
                "accommodation": ACCOMMODATION_POOL_TARGET,
            }[entity_type]
            limit = max(0, target - existing[entity_type])
            selected_for_type = cls.balance_categories(candidates, limit)
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
    def _entity_type(
        category: str | None,
        *,
        name: str | None = None,
        tags: list[str] | tuple[str, ...] = (),
        pool_category: str | None = None,
        context: str | None = None,
    ) -> str:
        normalized = planner_category_for_candidate(
            category,
            name=name,
            tags=tags,
            pool_category=pool_category,
            context=context,
        )
        if normalized == "restaurant":
            return "restaurant"
        if normalized == "drink_dessert":
            return "drink_dessert"
        if normalized == "entertainment":
            return "entertainment"
        if normalized == "accommodation":
            return "accommodation"
        return "travel_place"

    @staticmethod
    def _pool_category(tags: list[str] | tuple[str, ...]) -> str | None:
        return next(
            (tag.split(":", 1)[1] for tag in tags if tag.startswith("pool_category:")),
            None,
        )

    @staticmethod
    def _has_handoff_metadata(evaluation) -> bool:
        metadata = evaluation.place.metadata
        if metadata is None or metadata.coordinates is None:
            return False
        if metadata.typical_duration_minutes is None:
            return False
        return has_planner_cost(
            category=metadata.category,
            minimum=metadata.minimum_cost,
            typical=metadata.typical_cost,
            maximum=metadata.maximum_cost,
            tier=metadata.cost_tier,
        )
