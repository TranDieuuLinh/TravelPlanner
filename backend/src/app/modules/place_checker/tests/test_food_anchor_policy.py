from app.modules.place_checker.evaluation.contract import PlaceEvaluationBatch
from app.modules.place_checker.selection.food.anchor_policy import select_food_anchors
from app.modules.place_checker.tests.analysis_fixtures import evaluated_place
from app.shared.contracts.place import Coordinates


def test_anchor_policy_keeps_all_real_activity_anchors() -> None:
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

    assert len(anchors) == 21
    assert anchors[0].place_id == "mandatory"
    assert [item.place_id for item in anchors[1:4]] == [
        "optional:0",
        "optional:1",
        "optional:2",
    ]


def test_anchor_policy_includes_entertainment_and_excludes_food_venues() -> None:
    places = [
        evaluated_place("travel", mandatory=True, category="travel_place"),
        evaluated_place("evening", mandatory=False, category="entertainment"),
        evaluated_place("restaurant", mandatory=False, category="restaurant"),
        evaluated_place("drink", mandatory=False, category="drink_dessert"),
    ]

    anchors = select_food_anchors(PlaceEvaluationBatch(places=places), days=2)

    assert [item.place_id for item in anchors] == ["travel", "evening"]
