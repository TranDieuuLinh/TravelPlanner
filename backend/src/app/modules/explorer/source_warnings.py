from urllib.parse import urlparse

from app.modules.explorer.models import BatchCoverage, SourceExtractionResult


def source_warnings(
    coverage: BatchCoverage | None,
    source_results: list[SourceExtractionResult] | None,
) -> list[str]:
    warnings: list[str] = []
    if coverage == "partial":
        warnings.append("Một số nguồn không trích xuất được; kết quả dùng các nguồn còn lại.")
    for result in source_results or []:
        label = _source_label(result)
        if result.coverage_status == "partial":
            ratio = (
                f"{result.coverage_ratio:.0%}"
                if result.coverage_ratio is not None
                else "không xác định"
            )
            warnings.append(f"Nguồn {label} chỉ được phân tích {ratio}.")
        if result.synthesis_coverage_ratio is not None and result.synthesis_coverage_ratio < 1:
            warnings.append(
                f"Nguồn {label} chỉ tổng hợp thành công "
                f"{result.processed_source_chunk_count}/{result.source_chunk_count} chunk."
            )
        if (
            result.expected_place_count is not None
            and result.extracted_place_count < result.expected_place_count
        ):
            warnings.append(
                f"Nguồn {label} mới giữ {result.extracted_place_count}/"
                f"{result.expected_place_count} địa điểm dự kiến."
            )
        for failure in result.branch_failures:
            branch = "OCR frame" if failure.branch == "frame_ocr" else "STT audio"
            warnings.append(f"Nguồn {label} bị lỗi nhánh {branch} ({failure.error.code}).")
        if result.status in {"failed_retryable", "failed_permanent"}:
            code = result.error.code if result.error else "SOURCE_EXTRACTION_FAILED"
            warnings.append(f"Nguồn {label} thất bại ({code}).")
    return warnings


def _source_label(result: SourceExtractionResult) -> str:
    if result.source_kind == "url":
        host = urlparse(result.source_ref).hostname or "URL"
        return f"URL #{result.source_index + 1} ({host})"
    return f"ảnh #{result.source_index + 1}"
