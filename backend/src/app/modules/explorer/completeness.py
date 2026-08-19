from app.modules.explorer.contract import ExplorerCompleteness, SourceCompleteness
from app.modules.explorer.models import SourceExtractionResult


def build_completeness(
    results: list[SourceExtractionResult] | None,
    deduplicated: int,
    minimum_synthesis_coverage: float,
) -> ExplorerCompleteness | None:
    if not results:
        return None
    discarded: dict[str, int] = {}
    sources = []
    complete = True
    for result in results:
        for key, count in result.discarded_mentions.items():
            discarded[key] = discarded.get(key, 0) + count
        synthesis = result.synthesis_coverage_ratio
        complete = complete and result.status == "succeeded" and (
            synthesis is None or synthesis >= minimum_synthesis_coverage
        )
        sources.append(
            SourceCompleteness(
                sourceIndex=result.source_index,
                sourceRef=result.source_ref,
                coverageStatus=result.coverage_status,
                coverageRatio=result.coverage_ratio,
                rawMentionCount=result.raw_mention_count,
                filteredMentionCount=result.filtered_mention_count,
                deduplicatedPlaceCount=result.deduplicated_place_count,
                sourceChunkCount=result.source_chunk_count,
                processedSourceChunkCount=result.processed_source_chunk_count,
                synthesisCoverageRatio=synthesis,
                discarded=result.discarded_mentions,
            )
        )
    return ExplorerCompleteness(
        sources=sources,
        rawMentionCount=sum(item.raw_mention_count for item in results),
        filteredMentionCount=sum(item.filtered_mention_count for item in results),
        deduplicatedPlaceCount=deduplicated,
        discarded=discarded,
        complete=complete,
    )
