from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies.database import DatabaseSession
from app.schemas.pipeline import (
    PipelineCreate,
    PipelineListResponse,
    PipelineResponse,
    PipelineStatusUpdate,
    PipelineSummary,
    PipelineUpdate,
)
from app.services.metadata.pipelines import PipelineService

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.post("", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
def create_pipeline(payload: PipelineCreate, session: DatabaseSession) -> PipelineResponse:
    return PipelineResponse.model_validate(PipelineService(session).create(payload))


@router.get("", response_model=PipelineListResponse)
def list_pipelines(
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    is_active: bool | None = None,
) -> PipelineListResponse:
    items, total = PipelineService(session).list(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )
    return PipelineListResponse.build(
        [PipelineSummary.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{pipeline_id}", response_model=PipelineResponse)
def get_pipeline(pipeline_id: UUID, session: DatabaseSession) -> PipelineResponse:
    return PipelineResponse.model_validate(PipelineService(session).get(str(pipeline_id)))


@router.patch("/{pipeline_id}", response_model=PipelineResponse)
def update_pipeline(
    pipeline_id: UUID, payload: PipelineUpdate, session: DatabaseSession
) -> PipelineResponse:
    pipeline = PipelineService(session).update(str(pipeline_id), payload)
    return PipelineResponse.model_validate(pipeline)


@router.patch("/{pipeline_id}/status", response_model=PipelineResponse)
def update_pipeline_status(
    pipeline_id: UUID, payload: PipelineStatusUpdate, session: DatabaseSession
) -> PipelineResponse:
    pipeline = PipelineService(session).set_status(
        str(pipeline_id), is_active=payload.is_active
    )
    return PipelineResponse.model_validate(pipeline)


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(pipeline_id: UUID, session: DatabaseSession) -> Response:
    PipelineService(session).delete(str(pipeline_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
