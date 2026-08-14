from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.dependencies.database import get_db
from app.core.database import Base
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def create_source(
    client: TestClient,
    *,
    name: str = "Sales DB",
    source_type: str = "database",
    description: str | None = "Production sales data",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/sources",
        json={
            "name": name,
            "source_type": source_type,
            "description": description,
            "properties": {"owner": "data-platform"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_source_crud_and_status_lifecycle(client: TestClient) -> None:
    created = create_source(client)
    source_id = created["id"]
    assert created["is_active"] is True

    fetched = client.get(f"/api/v1/sources/{source_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Sales DB"

    updated = client.patch(
        f"/api/v1/sources/{source_id}",
        json={"name": "Sales Warehouse", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Sales Warehouse"
    assert updated.json()["description"] is None

    deactivated = client.patch(
        f"/api/v1/sources/{source_id}/status", json={"is_active": False}
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    reactivated = client.patch(
        f"/api/v1/sources/{source_id}/status", json={"is_active": True}
    )
    assert reactivated.json()["is_active"] is True

    deleted = client.delete(f"/api/v1/sources/{source_id}")
    assert deleted.status_code == 204
    inactive = client.get("/api/v1/sources", params={"is_active": "false"})
    assert inactive.json()["items"][0]["id"] == source_id


def test_pagination_search_and_filters(client: TestClient) -> None:
    create_source(client, name="Alpha Database", source_type="database")
    create_source(client, name="Beta API", source_type="api", description="Customer feed")
    create_source(client, name="Gamma API", source_type="api", description="Other feed")

    page = client.get("/api/v1/sources", params={"page": 1, "page_size": 2})
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert page.json()["pages"] == 2
    assert [item["name"] for item in page.json()["items"]] == [
        "Alpha Database",
        "Beta API",
    ]

    filtered = client.get(
        "/api/v1/sources", params={"search": "customer", "source_type": "api"}
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["name"] == "Beta API"


def test_duplicate_and_not_found_errors_are_consistent(client: TestClient) -> None:
    create_source(client, name="Sales DB")
    duplicate = client.post(
        "/api/v1/sources",
        json={"name": "sales db", "source_type": "database"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "source_name_conflict"
    assert duplicate.json()["request_id"]

    missing = client.get("/api/v1/sources/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "source_not_found"


@pytest.mark.parametrize(
    ("method", "url", "payload"),
    [
        ("post", "/api/v1/sources", {"name": "   ", "source_type": "api"}),
        ("patch", "/api/v1/sources/00000000-0000-0000-0000-000000000000", {}),
    ],
)
def test_invalid_payloads_use_validation_error_envelope(
    client: TestClient, method: str, url: str, payload: dict[str, object]
) -> None:
    response = client.request(method, url, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["request_id"]
