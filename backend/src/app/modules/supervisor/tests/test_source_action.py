from app.modules.explorer.public import (
    ExplorerOutput,
    ExplorerPlace,
    PlaceSource,
    SourceNote,
)
from app.modules.supervisor.source_action import (
    compose_source_summary,
    infer_source_action,
)


def test_source_action_requires_a_source_and_distinguishes_summary() -> None:
    assert infer_source_action("Tóm tắt nội dung liên kết này", attached=False) is None
    assert (
        infer_source_action(
            "Tóm tắt nội dung liên kết này https://example.test/post",
            attached=False,
        )
        == "summarize_source"
    )
    assert (
        infer_source_action(
            "Tạo lịch trình chuyến đi từ liên kết này",
            attached=True,
        )
        == "plan_from_source"
    )


def test_source_summary_uses_only_normalized_explorer_output() -> None:
    output = ExplorerOutput(
        status="ready",
        intakeId="summary-1",
        input_ADM="Hanoi",
        places=[
            ExplorerPlace(
                name="Văn Miếu",
                sourcePlaces=[
                    PlaceSource(
                        origin="url",
                        evidenceType="transcript",
                        sourceUrl="https://example.test/post",
                        evidence="Nguồn nhắc đến Văn Miếu",
                    )
                ],
            )
        ],
        urlNotes=[
            SourceNote(
                summary="Nguồn giới thiệu một hành trình tham quan văn hóa.",
                placeName="Văn Miếu",
                evidenceType="transcript",
                sourceUrl="https://example.test/post",
            )
        ],
    )

    response = compose_source_summary(output)

    assert "Hanoi" in response
    assert "Văn Miếu" in response
    assert "hành trình tham quan văn hóa" in response
