from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies.database import DatabaseSession
from app.models.enums import SourceType
from app.schemas.source import (
    SourceCreate,
    SourceListResponse,
    SourceResponse,
    SourceStatusUpdate,
    SourceUpdate,
)
from app.services.metadata.sources import SourceService

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreate, session: DatabaseSession) -> SourceResponse:
    source = SourceService(session).create(payload)
    return SourceResponse.model_validate(source)


@router.get("", response_model=SourceListResponse)
def list_sources(
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    source_type: SourceType | None = None,
    is_active: bool | None = None,
) -> SourceListResponse:
    items, total = SourceService(session).list(
        page=page,
        page_size=page_size,
        search=search,
        source_type=source_type,
        is_active=is_active,
    )
    return SourceListResponse.build(
        [SourceResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: UUID, session: DatabaseSession) -> SourceResponse:
    return SourceResponse.model_validate(SourceService(session).get(str(source_id)))


@router.patch("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: UUID, payload: SourceUpdate, session: DatabaseSession
) -> SourceResponse:
    source = SourceService(session).update(str(source_id), payload)
    return SourceResponse.model_validate(source)


@router.patch("/{source_id}/status", response_model=SourceResponse)
def update_source_status(
    source_id: UUID, payload: SourceStatusUpdate, session: DatabaseSession
) -> SourceResponse:
    source = SourceService(session).set_status(str(source_id), is_active=payload.is_active)
    return SourceResponse.model_validate(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: UUID, session: DatabaseSession) -> Response:
    SourceService(session).delete(str(source_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
