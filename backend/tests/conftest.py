from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security_headers import reset_rate_limit_store
from app.db.base import Base
from app.db.session import get_db
from app.main import app

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    reset_rate_limit_store()
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    reset_rate_limit_store()


@pytest.fixture
def db_session(client: TestClient) -> Generator[Session, None, None]:
    with TestingSessionLocal() as db:
        yield db


@pytest.fixture
def registered_client(client: TestClient) -> TestClient:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "traveler@example.com",
            "password": "MatKhauManh123",
            "fullName": "Nguyễn Minh Tuấn",
        },
    )
    assert response.status_code == 201
    return client
