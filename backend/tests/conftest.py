"""Shared test fixtures: one TestClient + autouse auth override."""

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.schemas import UserPayload

MOCK_USER_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def authed_client(client: TestClient):
    app.dependency_overrides[get_current_user] = lambda: UserPayload(
        user_id=MOCK_USER_ID,
        email="testuser@example.com",
        role="authenticated",
    )
    yield client
    app.dependency_overrides.clear()
