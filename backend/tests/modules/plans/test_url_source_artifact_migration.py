from app.modules.plans.explorer.model import SourceDocument


def test_source_document_is_the_only_explorer_artifact_table() -> None:
    assert SourceDocument.__tablename__ == "source_documents"
    assert "artifacts" in SourceDocument.__table__.columns
    assert "extracted_context" in SourceDocument.__table__.columns
