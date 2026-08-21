import asyncio

from app.modules.finisher.contract import FinisherOutput
from app.modules.finisher.service import ItineraryFinisher
from app.modules.itinerary_planner.output_contract import ItineraryPlannerOutput


def planner_output(*, notes: list[dict | None]) -> ItineraryPlannerOutput:
    stops = []
    for index, note in enumerate(notes, start=1):
        stops.append(
            {
                "itemId": f"planner:1:place-{index}",
                "placeId": f"place-{index}",
                "name": f"Điểm {index}",
                "kind": "place",
                "priority": (
                    "url" if note and note["sourceType"] == "url" else "user_input"
                ),
                "startMinute": 480 + index * 60,
                "endMinute": 540 + index * 60,
                "durationMinutes": 60,
                "coordinates": {"latitude": 21.0 + index / 100, "longitude": 105.8},
                "notes": note,
                "costPerPerson": 0,
            }
        )
    return ItineraryPlannerOutput.model_validate(
        {
            "destination": "Hà Nội",
            "timezone": "Asia/Ho_Chi_Minh",
            "people": 2,
            "days": [
                {
                    "day": 1,
                    "date": "2026-08-22",
                    "stops": stops,
                    "legs": [],
                    "activityMinutes": 60 * len(stops),
                    "travelMinutes": 0,
                    "costPerPerson": 0,
                    "costBreakdown": {
                        "accommodation": 0,
                        "food": 0,
                        "localTransport": 0,
                        "activities": 0,
                        "misc": 0,
                        "total": 0,
                        "currency": "VND",
                    },
                }
            ],
            "totalCostPerPerson": 0,
            "currency": "VND",
            "solver": {
                "status": "OPTIMAL",
                "optimalityProven": True,
                "objectiveValue": 0,
                "objectivePolicyVersion": "test-v1",
                "objectiveComponents": {},
                "passes": [],
                "planningTimeMs": 1,
            },
            "unscheduled": [],
            "discardedOptionalCount": 0,
            "warnings": [],
            "phaseTimingsMs": {"total": 1},
        }
    )


def test_deterministic_finisher_prioritizes_url_note_in_vietnamese() -> None:
    output = planner_output(
        notes=[
            {
                "text": "Mô tả từ Google Maps.",
                "sourceType": "google_maps",
            },
            {
                "text": "Nên đến trước 8 giờ để tránh đông.",
                "sourceType": "url",
                "sourceUrl": "https://example.test/video",
            },
        ]
    )

    response = asyncio.run(ItineraryFinisher().finish(output))

    assert "Mình đã xếp lịch 1 ngày tại Hà Nội với 2 điểm" in response
    assert "nguồn URL bạn gửi" in response
    assert "Nên đến trước 8 giờ để tránh đông" in response
    assert "Mô tả từ Google Maps" not in response


def test_finisher_passes_ordered_normalized_notes_to_generator() -> None:
    class Generator:
        payload = None

        async def generate(self, payload):
            self.payload = payload
            return FinisherOutput(response="Lịch trình đã sẵn sàng bằng tiếng Việt.")

    generator = Generator()
    output = planner_output(
        notes=[
            {"text": "Mô tả Google.", "sourceType": "google_maps"},
            {
                "text": "Creator khuyên đi buổi sáng.",
                "sourceType": "url",
                "sourceUrl": "https://example.test/reel",
            },
        ]
    )

    response = asyncio.run(ItineraryFinisher(generator).finish(output))

    assert response == "Lịch trình đã sẵn sàng bằng tiếng Việt."
    assert [note.source_type for note in generator.payload.notes] == [
        "url",
        "google_maps",
    ]


def test_finisher_falls_back_when_generator_fails() -> None:
    class FailedGenerator:
        async def generate(self, payload):
            raise RuntimeError("provider unavailable")

    output = planner_output(notes=[None])

    response = asyncio.run(ItineraryFinisher(FailedGenerator()).finish(output))

    assert response.startswith("Mình đã xếp lịch 1 ngày tại Hà Nội")
    assert "mở từng điểm" in response
