import logging

from app.modules.finisher.contract import FinisherInput, FinisherNote
from app.modules.finisher.ports import FinisherResponseGenerator
from app.modules.itinerary_planner.public import ItineraryPlannerOutput

logger = logging.getLogger(__name__)

_SOURCE_PRIORITY = {
    "url": 0,
    "google_maps": 1,
    "knowledge_graph": 2,
    "backend": 3,
}


class ItineraryFinisher:
    """Turns normalized planner output into a user-facing Vietnamese response."""

    def __init__(self, generator: FinisherResponseGenerator | None = None) -> None:
        self._generator = generator

    async def finish(self, output: ItineraryPlannerOutput) -> str:
        payload = self._input(output)
        fallback = self._fallback(payload)
        if self._generator is None:
            return fallback
        try:
            generated = await self._generator.generate(payload)
            return generated.response.strip() or fallback
        except Exception as exc:
            logger.warning(
                "Itinerary finisher generator failed; using deterministic response (%s)",
                type(exc).__name__,
            )
            return fallback

    @staticmethod
    def _input(output: ItineraryPlannerOutput) -> FinisherInput:
        ranked_notes: list[tuple[int, int, FinisherNote]] = []
        seen: set[tuple[str, str, str | None]] = set()
        position = 0
        stop_count = 0
        for day in output.days:
            stop_count += len(day.stops)
            for stop in day.stops:
                note = stop.notes
                if note is None:
                    continue
                signature = (note.source_type, note.text, note.source_url)
                if signature in seen:
                    continue
                seen.add(signature)
                ranked_notes.append(
                    (
                        _SOURCE_PRIORITY.get(note.source_type, 99),
                        position,
                        FinisherNote(
                            place_name=stop.name,
                            text=note.text[:500],
                            source_type=note.source_type,
                            source_url=note.source_url,
                        ),
                    )
                )
                position += 1
        ranked_notes.sort(key=lambda item: (item[0], item[1]))
        return FinisherInput(
            destination=output.destination,
            day_count=len(output.days),
            stop_count=stop_count,
            notes=[item[2] for item in ranked_notes[:5]],
        )

    @staticmethod
    def _fallback(payload: FinisherInput) -> str:
        response = (
            f"Mình đã xếp lịch {payload.day_count} ngày tại "
            f"{payload.destination} với {payload.stop_count} điểm."
        )
        if not payload.notes:
            return f"{response} Bạn có thể mở từng điểm để xem chi tiết lịch trình."
        note = payload.notes[0]
        source_label = {
            "url": "nguồn URL bạn gửi",
            "google_maps": "Google Maps",
            "knowledge_graph": "dữ liệu địa điểm",
            "backend": "hệ thống lập lịch",
        }.get(note.source_type, "nguồn tham khảo")
        return (
            f"{response} Lưu ý ưu tiên từ {source_label} cho {note.place_name}: "
            f"{note.text} Bạn có thể mở từng điểm để xem đầy đủ ghi chú và nguồn."
        )
