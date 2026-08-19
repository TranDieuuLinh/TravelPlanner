from app.modules.explorer.models import AdmEvidence, ExplorerDraft
from app.modules.explorer.service import ExplorerService


def test_adm_alias_with_optional_space_does_not_create_conflict() -> None:
    draft = ExplorerDraft(
        inputAdm="Hanoi",
        admCandidates=[
            AdmEvidence(
                value="Hà Nội",
                evidence="Đi Hà Nội",
                sourceType="raw_prompt",
                confidence=1,
            ),
            AdmEvidence(
                value="Hanoi",
                evidence="Hanoi guide",
                sourceType="caption",
                confidence=0.99,
            ),
        ],
    )

    adm, conflict = ExplorerService.reconcile_adm(
        ExplorerService(None, None, None, None),  # type: ignore[arg-type]
        draft,
    )

    assert adm in {"Hà Nội", "Hanoi"}
    assert conflict is False


def test_main_destination_wins_over_lower_confidence_day_trip() -> None:
    draft = ExplorerDraft(
        inputAdm="Hanoi",
        admCandidates=[
            AdmEvidence(
                value="Hanoi",
                evidence="10 Best Things to Do in Hanoi",
                sourceType="caption",
                confidence=1,
            ),
            AdmEvidence(
                value="Ninh Binh",
                evidence="Day Tour to Ninh Binh",
                sourceType="caption",
                confidence=0.9,
            ),
        ],
    )

    adm, conflict = ExplorerService.reconcile_adm(
        ExplorerService(None, None, None, None),  # type: ignore[arg-type]
        draft,
    )

    assert adm == "Hanoi"
    assert conflict is False


def test_equal_strong_destinations_still_require_clarification() -> None:
    draft = ExplorerDraft(
        inputAdm="Hanoi",
        admCandidates=[
            AdmEvidence(
                value="Hanoi",
                evidence="Visit Hanoi",
                sourceType="caption",
                confidence=1,
            ),
            AdmEvidence(
                value="Ninh Binh",
                evidence="Visit Ninh Binh",
                sourceType="caption",
                confidence=1,
            ),
        ],
    )

    adm, conflict = ExplorerService.reconcile_adm(
        ExplorerService(None, None, None, None),  # type: ignore[arg-type]
        draft,
    )

    assert adm is None
    assert conflict is True


def test_repeated_primary_evidence_breaks_equal_confidence_tie() -> None:
    draft = ExplorerDraft(
        inputAdm="Hanoi",
        admCandidates=[
            AdmEvidence(
                value="Hanoi",
                evidence="The Ultimate Hanoi Bucket List",
                sourceType="caption",
                confidence=0.95,
            ),
            AdmEvidence(
                value="Hanoi",
                evidence="Ready to explore Hanoi?",
                sourceType="caption",
                confidence=0.95,
            ),
            AdmEvidence(
                value="Ninh Binh",
                evidence="Day Tour to Ninh Binh",
                sourceType="caption",
                confidence=0.95,
            ),
        ],
    )

    adm, conflict = ExplorerService.reconcile_adm(
        ExplorerService(None, None, None, None),  # type: ignore[arg-type]
        draft,
    )

    assert adm == "Hanoi"
    assert conflict is False


def test_duplicate_primary_evidence_does_not_break_tie() -> None:
    duplicate = AdmEvidence(
        value="Hanoi",
        evidence="Visit Hanoi",
        sourceType="caption",
        sourceUrl="https://example.com/source",
        confidence=0.95,
    )
    draft = ExplorerDraft(
        inputAdm="Hanoi",
        admCandidates=[
            duplicate,
            duplicate.model_copy(),
            AdmEvidence(
                value="Ninh Binh",
                evidence="Visit Ninh Binh",
                sourceType="caption",
                sourceUrl="https://example.com/source",
                confidence=0.95,
            ),
        ],
    )

    adm, conflict = ExplorerService.reconcile_adm(
        ExplorerService(None, None, None, None),  # type: ignore[arg-type]
        draft,
    )

    assert adm is None
    assert conflict is True
