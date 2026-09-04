from __future__ import annotations

from math import ceil

from app.modules.itinerary_planner.routing_models import MatrixCell, MatrixLocation


MatrixRequestBatch = tuple[
    tuple[int, ...],
    tuple[MatrixLocation, ...],
    tuple[int, ...],
    tuple[MatrixLocation, ...],
]


def full_matrix_batches(
    locations: tuple[MatrixLocation, ...],
    max_pairs: int,
) -> tuple[
    tuple[int, tuple[MatrixLocation, ...], int, tuple[MatrixLocation, ...]], ...
]:
    size = len(locations)
    if size == 0:
        return ()
    source_chunk, target_chunk = matrix_batch_shape(size, max_pairs)
    return tuple(
        (
            source_start,
            locations[source_start : source_start + source_chunk],
            target_start,
            locations[target_start : target_start + target_chunk],
        )
        for source_start in range(0, size, source_chunk)
        for target_start in range(0, size, target_chunk)
    )


def missing_matrix_batches(
    locations: tuple[MatrixLocation, ...],
    rows: list[list[MatrixCell | None]],
    *,
    max_pairs: int,
    targeted: bool,
) -> tuple[MatrixRequestBatch, ...]:
    if not targeted:
        return tuple(
            (
                tuple(range(source_start, source_start + len(sources))),
                sources,
                tuple(range(target_start, target_start + len(targets))),
                targets,
            )
            for source_start, sources, target_start, targets in full_matrix_batches(
                locations, max_pairs
            )
            if any(
                rows[source_index][target_index] is None
                for source_index in range(source_start, source_start + len(sources))
                for target_index in range(target_start, target_start + len(targets))
            )
        )

    sources_by_missing_targets: dict[tuple[int, ...], list[int]] = {}
    for source_index, row in enumerate(rows):
        missing_targets = tuple(
            target_index for target_index, cell in enumerate(row) if cell is None
        )
        if missing_targets:
            sources_by_missing_targets.setdefault(missing_targets, []).append(
                source_index
            )
    batches: list[MatrixRequestBatch] = []
    for target_indexes, source_indexes_list in sources_by_missing_targets.items():
        target_chunk_size = min(len(target_indexes), max_pairs)
        for target_offset in range(0, len(target_indexes), target_chunk_size):
            target_chunk = target_indexes[
                target_offset : target_offset + target_chunk_size
            ]
            source_chunk_size = max(1, max_pairs // len(target_chunk))
            for source_offset in range(0, len(source_indexes_list), source_chunk_size):
                source_chunk = tuple(
                    source_indexes_list[
                        source_offset : source_offset + source_chunk_size
                    ]
                )
                batches.append(
                    (
                        source_chunk,
                        tuple(locations[index] for index in source_chunk),
                        target_chunk,
                        tuple(locations[index] for index in target_chunk),
                    )
                )
    return tuple(batches)


def matrix_batch_shape(size: int, max_pairs: int) -> tuple[int, int]:
    """Choose chunks that minimize request count without exceeding max_pairs."""
    best: tuple[int, int, int, int] | None = None
    for target_chunk in range(1, min(size, max_pairs) + 1):
        source_chunk = min(size, max_pairs // target_chunk)
        request_count = ceil(size / source_chunk) * ceil(size / target_chunk)
        covered_pairs = source_chunk * target_chunk
        candidate = (request_count, -covered_pairs, -target_chunk, source_chunk)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    return best[3], -best[2]


def parse_matrix_cells(
    payload: dict,
    source_count: int,
    target_count: int,
) -> tuple[tuple[MatrixCell, ...], ...]:
    rows = payload["sources_to_targets"]
    if len(rows) != source_count:
        raise ValueError("matrix row count mismatch")
    parsed_rows: list[tuple[MatrixCell, ...]] = []
    for row in rows:
        if len(row) != target_count:
            raise ValueError("matrix column count mismatch")
        parsed = []
        for cell in row:
            duration = cell.get("time")
            distance = cell.get("distance")
            reachable = duration is not None and distance is not None
            if reachable and (float(duration) < 0 or float(distance) < 0):
                raise ValueError("negative matrix value")
            parsed.append(
                MatrixCell(
                    duration_seconds=float(duration) if reachable else None,
                    distance_meters=float(distance) * 1000 if reachable else None,
                    reachable=reachable,
                )
            )
        parsed_rows.append(tuple(parsed))
    return tuple(parsed_rows)
