from app.modules.information_finder.contract import (
    EntitySpan,
    FactItem,
    FactListBlock,
    InformationFinderOutput,
    TextSpan,
    VerseBlock,
)


def test_fact_list_and_verse_serialize_with_camel_case_and_entity_span():
    output = InformationFinderOutput(
        answer="Hồ Gươm ở Hà Nội.",
        content_blocks=[
            FactListBlock(
                type="factList",
                title="Thông tin nổi bật",
                items=[
                    FactItem(
                        label="Địa điểm",
                        text="Hồ Gươm ở Hà Nội.",
                        highlights=["Hà Nội"],
                        source_ids=["source-1"],
                        inline_spans=[
                            TextSpan(type="text", text="Hồ Gươm ở "),
                            EntitySpan(
                                type="entity",
                                text="Hà Nội",
                                entity_id="place-1",
                            ),
                            TextSpan(type="text", text="."),
                        ],
                    )
                ],
            ),
            VerseBlock(
                type="verse",
                title="Bài thơ",
                author="Tác giả",
                lines=["Dòng một", "Dòng hai"],
                source_ids=["source-2"],
            ),
        ],
    )

    payload = output.model_dump(by_alias=True)

    assert payload["contentBlocks"][0]["items"][0]["inlineSpans"][1]["entityId"] == "place-1"
    assert payload["contentBlocks"][1]["lines"] == ["Dòng một", "Dòng hai"]
    assert payload["metadata"] == {
        "generationMode": "none",
        "validationStatus": "no_sources",
        "confidence": "unavailable",
        "fallbackUsed": False,
        "claimCount": 0,
        "citedSourceCount": 0,
    }
