from app.modules.information_finder.contract import GeneratedAnswer, RetrievedSource
from app.modules.information_finder.errors import AnswerProviderInvalidOutput
from app.modules.information_finder.normalization import normalize_answer_text


def validate_and_render_answer(
    generated: GeneratedAnswer,
    available_sources: list[RetrievedSource],
) -> tuple[str, list[RetrievedSource]]:
    source_by_id = {source.source_id: source for source in available_sources}
    cited_ids: list[str] = []
    for claim in generated.claims:
        for source_id in claim.source_ids:
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
    for claim in generated.claims:
        claim_text = normalize_answer_text(claim.text)
        if not claim_text:
            raise AnswerProviderInvalidOutput("Answer claim became empty after normalization")
        unique_claim_ids = list(dict.fromkeys(claim.source_ids))
        markers = "".join(f"[{citation_number[item]}]" for item in unique_claim_ids)
        rendered_claims.append(f"{claim_text} {markers}")
    if generated.caveat and generated.caveat.strip():
        rendered_claims.append(generated.caveat.strip())
    return "\n\n".join(rendered_claims), [source_by_id[item] for item in cited_ids]
