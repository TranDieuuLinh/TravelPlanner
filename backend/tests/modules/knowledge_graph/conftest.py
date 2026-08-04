"""Standalone conftest for knowledge_graph tests.

Provides isolated fixtures that don't require the full app import.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create an in-memory SQLite database for testing.

    This fixture is isolated from the main app to avoid import issues.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
