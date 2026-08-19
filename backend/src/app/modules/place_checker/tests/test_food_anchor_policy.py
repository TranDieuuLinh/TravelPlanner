from app.modules.place_checker.evaluation_contract import PlaceEvaluationBatch
from app.modules.place_checker.food_anchor_policy import select_food_anchors
from app.modules.place_checker.tests.analysis_fixtures import evaluated_place
from app.shared.contracts.place import Coordinates


def test_anchor_policy_keeps_mandatory_and_caps_optional_candidates() -> None:
    places = [
        evaluated_place("mandatory", mandatory=True, category="travel_place"),
        *[
            evaluated_place(
                f"optional:{index}",
                mandatory=False,
                category="travel_place",
                coordinates=Coordinates(
                    latitude=21 + index * 0.01,
                    longitude=105 + index * 0.01,
                ),
            )
            for index in range(20)
        ],
    ]

    anchors = select_food_anchors(PlaceEvaluationBatch(places=places), days=3)

    assert len(anchors) == 8
    assert anchors[0].place_id == "mandatory"
    assert [item.place_id for item in anchors[1:4]] == [
        "optional:0",
        "optional:1",
        "optional:2",
    ]


def test_anchor_policy_does_not_drop_mandatory_places_over_soft_cap() -> None:
    places = [
        evaluated_place(
            f"mandatory:{index}", mandatory=True, category="travel_place"
        )
        for index in range(14)
    ]

    anchors = select_food_anchors(PlaceEvaluationBatch(places=places), days=2)

    assert len(anchors) == 14
