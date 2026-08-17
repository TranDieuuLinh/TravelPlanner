from app.modules.place_checker.adapters.postgres_style_candidate_query import (
    STYLE_CANDIDATE_SQL,
    STYLE_INTENT_RESOLUTION_SQL,
)
from app.modules.place_checker.style_candidate_contract import (
    ResolvedStyleIntent,
    StyleCandidate,
    StyleCandidateSourceBatch,
)


class PostgresStyleCandidateMixin:
    async def find_style_candidates(
        self,
        *,
        adm_id: str,
        style_inputs: list[str],
        item_inputs: list[str],
        per_style_limit: int,
    ) -> StyleCandidateSourceBatch:
        pool = await self._get_pool()
        resolution_rows = await pool.fetch(
            STYLE_INTENT_RESOLUTION_SQL,
            list(dict.fromkeys(style_inputs)),
            list(dict.fromkeys(item_inputs)),
        )
        resolved_intents = [
            ResolvedStyleIntent(
                input_value=row["input_value"],
                source=row["request_source"],
                style_id=row["style_id"],
                style_name=row["style_name"],
                item_id=row["item_id"],
                item_name=row["item_name"],
            )
            for row in resolution_rows
        ]
        style_ids = list(
            dict.fromkeys(intent.style_id for intent in resolved_intents)
        )
        candidate_rows = (
            await pool.fetch(
                STYLE_CANDIDATE_SQL,
                adm_id,
                style_ids,
                max(1, per_style_limit),
            )
            if style_ids
            else []
        )
        metadata = await self.get_many(
            list(dict.fromkeys(row["place_id"] for row in candidate_rows))
        )
        candidates = [
            StyleCandidate(
                place_id=row["place_id"],
                place_name=row["place_name"],
                entity_type=row["entity_type"],
                style_id=row["style_id"],
                style_name=row["style_name"],
                item_id=row["item_id"],
                item_name=row["item_name"],
                relationship_source=row["relationship_source"],
                metadata=metadata[row["place_id"]],
            )
            for row in candidate_rows
            if row["place_id"] in metadata
        ]
        resolved_style_inputs = {
            intent.input_value
            for intent in resolved_intents
            if intent.source == "style"
        }
        resolved_item_inputs = {
            intent.input_value
            for intent in resolved_intents
            if intent.source == "item"
        }
        return StyleCandidateSourceBatch(
            resolved_intents=resolved_intents,
            candidates=candidates,
            unresolved_style_inputs=[
                value for value in style_inputs if value not in resolved_style_inputs
            ],
            unresolved_item_inputs=[
                value for value in item_inputs if value not in resolved_item_inputs
            ],
        )
