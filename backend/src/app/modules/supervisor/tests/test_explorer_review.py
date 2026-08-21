from app.modules.explorer.public import ExplorerReview
from app.modules.supervisor.explorer_review import compose_explorer_review


def defaults_review() -> ExplorerReview:
    return ExplorerReview.model_validate({
        "kind": "defaults_proposed",
        "intakeId": "defaults-1",
        "defaultedFields": ["budget", "people", "shortPreferences"],
        "tripContext": {
            "inputADM": "Hanoi",
            "days": 2,
            "budget": {"level": "low", "amountPerPerson": 1_172_432},
            "people": {"adults": 2},
            "shortPreferences": ["giá rẻ", "thiên nhiên"],
        },
    })


def test_supervisor_review_renders_structured_defaults() -> None:
    response, clarification = compose_explorer_review(defaults_review())

    assert "1.172.432" in response
    assert clarification == response


def test_missing_destination_review_returns_question() -> None:
    review = ExplorerReview(
        kind="missing_fields",
        intakeId="missing-1",
        missingFields=["inputADM"],
    )

    response, clarification = compose_explorer_review(review)

    assert response == "Bạn muốn đi tỉnh hoặc thành phố nào?"
    assert clarification == response
