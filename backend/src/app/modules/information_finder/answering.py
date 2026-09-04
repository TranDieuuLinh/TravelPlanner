from app.modules.information_finder.contract import (
    AnswerMetadata,
    ComparisonBlock,
    FactListBlock,
    GeneratedAnswer,
    NoticeBlock,
    ParagraphBlock,
    QuoteBlock,
    RecommendationsBlock,
    RetrievedSource,
    StepsBlock,
    VerseBlock,
)
from app.modules.information_finder.entity_linking import (
    EntityResolver,
    link_verified_entities,
    materialize_entity_spans,
)
from app.modules.information_finder.errors import (
    AnswerProviderError,
    AnswerProviderInvalidOutput,
)
from app.modules.information_finder.ports import AnswerGenerator
from app.modules.information_finder.normalization import normalize_generated_answer_text
from app.modules.information_finder.structured_content import normalize_answer_blocks


def build_answer_metadata(
    *,
    generation_mode: str,
    fallback_used: bool,
    cited_sources: list[RetrievedSource],
    claim_count: int,
) -> AnswerMetadata:
    """Describe answer validation without exposing provider-specific data."""
    if not cited_sources:
        return AnswerMetadata(
            generation_mode="none",
            validation_status="no_cited_content",
            confidence="unavailable",
            fallback_used=fallback_used,
        )
    if generation_mode == "extractive":
        confidence = "low"
    elif all(source.review_status == "approved" for source in cited_sources):
        confidence = "high"
    else:
        confidence = "medium"
    return AnswerMetadata(
        generation_mode=generation_mode,
        validation_status="citation_validated",
        confidence=confidence,
        fallback_used=fallback_used,
        claim_count=claim_count,
        cited_source_count=len(cited_sources),
    )


def invalid_answer_source_ids(
    generated: GeneratedAnswer, sources: list[RetrievedSource]
) -> list[str]:
    allowed = {source.source_id for source in sources}
    ids: list[str] = []
    for claim in generated.claims:
        ids.extend(claim.source_ids)
    for block in generated.blocks:
        ids.extend(block_source_ids(block))
    return list(dict.fromkeys(item for item in ids if item not in allowed))


def block_source_ids(block) -> list[str]:
    ids = list(getattr(block, "source_ids", []))
    for field in ("items", "options"):
        for item in getattr(block, field, []):
            ids.extend(getattr(item, "source_ids", []))
    return ids


def suggestions_from_blocks(blocks) -> list[dict[str, object]]:
    """Turn retrieved, cited recommendations into grounded chat choices."""
    suggestions: list[dict[str, object]] = []
    for block in blocks:
        if getattr(block, "type", None) not in {"recommendations", "comparison"}:
            continue
        entries = getattr(block, "items", None) or getattr(block, "options", None) or []
        for entry in entries[:5]:
            name = str(getattr(entry, "name", "")).strip()
            source_ids = list(dict.fromkeys(getattr(entry, "source_ids", [])))
            if not name or not source_ids:
                continue
            suggestions.append({
                "field": "information_follow_up",
                "label": name,
                "value": f"Cho tôi biết thêm về {name}",
                "sourceIds": source_ids,
            })
    return suggestions


def validate_and_render_answer(
    generated: GeneratedAnswer,
    available_sources: list[RetrievedSource],
) -> tuple[str, list, list[RetrievedSource]]:
    normalized_blocks = normalize_answer_blocks(generated.blocks)
    generated = generated.model_copy(update={"blocks": normalized_blocks})
    source_by_id = {source.source_id: source for source in available_sources}
    cited_ids: list[str] = []
    for source_id in _source_ids(generated):
        if source_id not in source_by_id:
            raise AnswerProviderInvalidOutput(
                "LLM cited a source ID outside the supplied context"
            )
        if source_id not in cited_ids:
            cited_ids.append(source_id)
    if not cited_ids:
        raise AnswerProviderInvalidOutput("Factual answer did not cite a source")

    citation_number = {
        source_id: index for index, source_id in enumerate(cited_ids, start=1)
    }
    rendered_claims = []
    if generated.blocks:
        for block in generated.blocks:
            rendered_claims.append(_render_block(block, citation_number))
    else:
        for claim in generated.claims:
            for source_id in claim.source_ids:
                if source_id not in source_by_id:
                    raise AnswerProviderInvalidOutput(
                        "LLM cited a source ID outside the supplied context"
                    )
            claim_text = normalize_generated_answer_text(claim.text)
            if not claim_text:
                raise AnswerProviderInvalidOutput(
                    "Answer claim became empty after normalization"
                )
            unique_claim_ids = list(dict.fromkeys(claim.source_ids))
            markers = "".join(
                f"[{citation_number[item]}]" for item in unique_claim_ids
            )
            rendered_claims.append(f"{claim_text} {markers}")
    if generated.caveat and generated.caveat.strip():
        rendered_claims.append(generated.caveat.strip())
    return "\n\n".join(rendered_claims), generated.blocks, [
        source_by_id[item] for item in cited_ids
    ]


def _source_ids(generated: GeneratedAnswer):
    if generated.blocks:
        for block in generated.blocks:
            yield from getattr(block, "source_ids", [])
            for field in ("items", "options"):
                for item in getattr(block, field, []):
                    yield from getattr(item, "source_ids", [])
    else:
        for claim in generated.claims:
            yield from claim.source_ids


def _render_block(block, citation_number: dict[str, int]) -> str:
    def marker(source_ids: list[str]) -> str:
        return "".join(f"[{citation_number[item]}]" for item in dict.fromkeys(source_ids))

    if isinstance(block, ParagraphBlock):
        return f"{normalize_generated_answer_text(block.text)} {marker(block.source_ids)}"
    if isinstance(block, FactListBlock):
        title = f"## {block.title}\n\n" if block.title else ""
        items = "\n".join(
            f"- **{item.label}:** {normalize_generated_answer_text(item.text)} "
            f"{marker(item.source_ids)}"
            for item in block.items
        )
        return f"{title}{items}"
    if isinstance(block, VerseBlock):
        title = f"## {block.title}\n\n" if block.title else ""
        author = f"*{block.author}*\n\n" if block.author else ""
        lines = "\n".join(block.lines)
        return f"{title}{author}{lines} {marker(block.source_ids)}"
    if isinstance(block, QuoteBlock):
        attribution = f" — {block.attribution}" if block.attribution else ""
        return f"> {block.text}{attribution} {marker(block.source_ids)}"
    if isinstance(block, RecommendationsBlock):
        title = f"## {block.title}\n\n" if block.title else ""
        items = "\n".join(
            f"- **{item.name}:** {item.reason} {marker(item.source_ids)}"
            for item in block.items
        )
        return f"{title}{items}"
    if isinstance(block, StepsBlock):
        title = f"## {block.title}\n\n" if block.title else ""
        items = "\n".join(
            f"{index}. {item.text} {marker(item.source_ids)}"
            for index, item in enumerate(block.items, start=1)
        )
        return f"{title}{items}"
    if isinstance(block, ComparisonBlock):
        title = f"## {block.title}\n\n" if block.title else ""
        options = "\n".join(
            f"- **{option.name}:** Ưu: {', '.join(option.pros)}; "
            f"Lưu ý: {', '.join(option.cons)} {marker(option.source_ids)}"
            for option in block.options
        )
        return f"{title}{options}"
    if isinstance(block, NoticeBlock):
        return f"> **Lưu ý:** {block.text} {marker(block.source_ids)}"
    raise AnswerProviderInvalidOutput("Unsupported answer block type")


async def generate_and_render_answer(
    query: str,
    sources: list[RetrievedSource],
    *,
    answers: AnswerGenerator,
    fallback_answers: AnswerGenerator | None,
    fallback_enabled: bool,
    entity_resolver: EntityResolver | None,
) -> tuple[str, list, list[RetrievedSource], list[str]]:
    warnings: list[str] = []
    try:
        generated = await answers.generate(query, sources)
        answer, content_blocks, cited_sources = validate_and_render_answer(
            generated, sources
        )
    except AnswerProviderError as exc:
        repair = getattr(answers, "generate_repair", None)
        if callable(repair):
            try:
                generated = await repair(query, sources, [])
                answer, content_blocks, cited_sources = validate_and_render_answer(
                    generated, sources
                )
                warnings.append("answer_repair_succeeded")
                return answer, content_blocks, cited_sources, warnings
            except AnswerProviderError:
                pass
        if not fallback_enabled or fallback_answers is None:
            raise
        generated = await fallback_answers.generate(query, sources)
        answer, content_blocks, cited_sources = validate_and_render_answer(
            generated, sources
        )
        warnings.append(f"answer_extractive_fallback:{exc.code}")

    answer = await link_verified_entities(
        answer,
        generated.entity_names,
        entity_resolver,
        generated.entity_candidates,
    )
    content_blocks = await materialize_entity_spans(
        generated.blocks,
        entity_names=generated.entity_names,
        entity_candidates=generated.entity_candidates,
        resolver=entity_resolver,
    )
    return answer, content_blocks, cited_sources, warnings
