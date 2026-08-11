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
