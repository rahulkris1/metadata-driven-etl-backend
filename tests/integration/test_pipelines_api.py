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


def pipeline_payload(name: str, dependencies: list[dict[str, str]] | None = None) -> dict:
    return {
        "name": name,
        "description": f"{name} definition",
        "schedule": "0 2 * * *",
        "schedule_timezone": "America/New_York",
        "parameters": {"batch_size": 1000},
        "dependencies": dependencies or [],
        "steps": [
            {
                "name": "extract_orders",
                "step_type": "extract",
                "position": 0,
                "retry_count": 2,
                "configuration": {"query": "select * from orders"},
                "transformations": [
                    {
                        "name": "normalize_status",
                        "transformation_type": "sql",
                        "expression": "upper(status)",
                    }
                ],
            },
            {
                "name": "load_orders",
                "step_type": "load",
                "position": 1,
                "load_strategy": "upsert",
                "configuration": {"merge_keys": ["order_id"]},
                "mappings": [
                    {"source_column": "id", "target_column": "order_id"},
                    {
                        "target_column": "loaded_at",
                        "expression": "current_timestamp",
                        "data_type": "timestamp",
                    },
                ],
            },
        ],
        "incremental_configuration": {
            "strategy": "watermark",
            "watermark_column": "updated_at",
            "initial_value": "1970-01-01T00:00:00Z",
        },
    }


def create_pipeline(
    client: TestClient, name: str, dependencies: list[dict[str, str]] | None = None
) -> dict:
    response = client.post(
        "/api/v1/pipelines", json=pipeline_payload(name, dependencies)
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_pipeline_crud_with_complete_definition(client: TestClient) -> None:
    upstream = create_pipeline(client, "upstream")
    created = create_pipeline(
        client,
        "daily_orders",
        [{"depends_on_pipeline_id": upstream["id"], "dependency_type": "success"}],
    )
    pipeline_id = created["id"]

    assert created["schedule"] == "0 2 * * *"
    assert created["schedule_timezone"] == "America/New_York"
    assert len(created["steps"]) == 2
    assert created["steps"][1]["load_strategy"] == "upsert"
    assert len(created["steps"][1]["mappings"]) == 2
    assert created["dependencies"][0]["depends_on_pipeline_id"] == upstream["id"]
    assert created["incremental_configuration"]["strategy"] == "watermark"

    fetched = client.get(f"/api/v1/pipelines/{pipeline_id}")
    assert fetched.status_code == 200
    assert fetched.json()["steps"][0]["transformations"][0]["name"] == "normalize_status"

    updated = client.patch(
        f"/api/v1/pipelines/{pipeline_id}",
        json={"schedule": None, "parameters": {"batch_size": 500}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["schedule"] is None
    assert updated.json()["parameters"] == {"batch_size": 500}

    inactive = client.patch(
        f"/api/v1/pipelines/{pipeline_id}/status", json={"is_active": False}
    )
    assert inactive.status_code == 200
    assert inactive.json()["is_active"] is False

    active = client.patch(
        f"/api/v1/pipelines/{pipeline_id}/status", json={"is_active": True}
    )
    assert active.json()["is_active"] is True

    deleted = client.delete(f"/api/v1/pipelines/{pipeline_id}")
    assert deleted.status_code == 204
    listed = client.get("/api/v1/pipelines", params={"is_active": "false"})
    assert [item["id"] for item in listed.json()["items"]] == [pipeline_id]


def test_pipeline_pagination_search_and_conflict(client: TestClient) -> None:
    create_pipeline(client, "Alpha Pipeline")
    create_pipeline(client, "Beta Pipeline")
    create_pipeline(client, "Gamma Pipeline")

    page = client.get("/api/v1/pipelines", params={"page_size": 2})
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert page.json()["pages"] == 2

    search = client.get("/api/v1/pipelines", params={"search": "beta"})
    assert search.json()["items"][0]["name"] == "Beta Pipeline"

    duplicate = client.post("/api/v1/pipelines", json=pipeline_payload("alpha pipeline"))
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "pipeline_name_conflict"


def test_dependency_cycles_are_rejected(client: TestClient) -> None:
    first = create_pipeline(client, "first")
    second = create_pipeline(
        client,
        "second",
        [{"depends_on_pipeline_id": first["id"], "dependency_type": "completion"}],
    )

    cycle = client.patch(
        f"/api/v1/pipelines/{first['id']}",
        json={
            "dependencies": [
                {
                    "depends_on_pipeline_id": second["id"],
                    "dependency_type": "success",
                }
            ]
        },
    )
    assert cycle.status_code == 422
    assert cycle.json()["error"]["code"] == "invalid_pipeline_configuration"


@pytest.mark.parametrize(
    ("mutator", "expected_message"),
    [
        (lambda body: body.update(schedule="invalid cron"), "cron"),
        (
            lambda body: body["steps"][1].pop("load_strategy"),
            "load_strategy",
        ),
        (
            lambda body: body["steps"][1]["mappings"].append(
                {"source_column": "duplicate", "target_column": "order_id"}
            ),
            "unique",
        ),
    ],
)
def test_invalid_pipeline_definitions_use_validation_envelope(
    client: TestClient, mutator, expected_message: str
) -> None:
    payload = pipeline_payload("invalid")
    mutator(payload)
    response = client.post("/api/v1/pipelines", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert expected_message in response.text


def test_missing_dependency_is_a_configuration_error(client: TestClient) -> None:
    response = client.post(
        "/api/v1/pipelines",
        json=pipeline_payload(
            "missing_dependency",
            [
                {
                    "depends_on_pipeline_id": "00000000-0000-0000-0000-000000000000",
                    "dependency_type": "success",
                }
            ],
        ),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_pipeline_configuration"
