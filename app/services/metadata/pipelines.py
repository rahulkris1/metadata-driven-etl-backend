from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.base import new_uuid
from app.models.metadata import (
    ColumnMapping,
    Dataset,
    IncrementalConfiguration,
    Pipeline,
    PipelineDependency,
    PipelineStep,
    Transformation,
)
from app.repositories.base import MetadataConflictError
from app.repositories.metadata import PipelineRepository
from app.schemas.pipeline import (
    IncrementalConfigurationInput,
    PipelineCreate,
    PipelineDependencyInput,
    PipelineStepInput,
    PipelineUpdate,
)


class PipelineService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PipelineRepository(session)

    def create(self, payload: PipelineCreate) -> Pipeline:
        self._ensure_unique_name(payload.name)
        pipeline = Pipeline(
            id=new_uuid(),
            name=payload.name,
            description=payload.description,
            schedule=payload.schedule,
            schedule_timezone=payload.schedule_timezone,
            parameters=payload.parameters,
        )
        self._set_steps(pipeline, payload.steps)
        self._set_dependencies(pipeline, payload.dependencies)
        self._set_incremental_configuration(
            pipeline, payload.incremental_configuration
        )
        self._commit(lambda: self.repository.add(pipeline))
        return self.get(pipeline.id)

    def get(self, pipeline_id: str) -> Pipeline:
        pipeline = self.repository.get_with_steps(pipeline_id)
        if pipeline is None:
            raise AppError(
                message="Pipeline not found", status_code=404, code="pipeline_not_found"
            )
        return pipeline

    def list(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        is_active: bool | None,
    ) -> tuple[Sequence[Pipeline], int]:
        return self.repository.paginate(
            offset=(page - 1) * page_size,
            limit=page_size,
            search=search,
            is_active=is_active,
        )

    def update(self, pipeline_id: str, payload: PipelineUpdate) -> Pipeline:
        pipeline = self.get(pipeline_id)
        if payload.name is not None and payload.name.casefold() != pipeline.name.casefold():
            self._ensure_unique_name(payload.name, exclude_id=pipeline.id)

        scalar_fields = {
            "name",
            "description",
            "schedule",
            "schedule_timezone",
            "parameters",
        }
        for field in scalar_fields.intersection(payload.model_fields_set):
            setattr(pipeline, field, getattr(payload, field))

        if payload.steps is not None:
            pipeline.steps.clear()
            self.session.flush()
            self._set_steps(pipeline, payload.steps)
        if payload.dependencies is not None:
            pipeline.dependencies.clear()
            self.session.flush()
            self._set_dependencies(pipeline, payload.dependencies)
        if "incremental_configuration" in payload.model_fields_set:
            self._set_incremental_configuration(
                pipeline, payload.incremental_configuration
            )

        self._commit(lambda: self.session.flush())
        return self.get(pipeline.id)

    def set_status(self, pipeline_id: str, *, is_active: bool) -> Pipeline:
        pipeline = self.get(pipeline_id)
        self._commit(lambda: self.repository.update(pipeline, is_active=is_active))
        return self.get(pipeline.id)

    def delete(self, pipeline_id: str) -> None:
        pipeline = self.get(pipeline_id)
        self._commit(lambda: self.repository.deactivate(pipeline))

    def _set_steps(self, pipeline: Pipeline, definitions: list[PipelineStepInput]) -> None:
        for definition in definitions:
            self._validate_dataset_references(definition)
            step = PipelineStep(
                name=definition.name,
                step_type=definition.step_type,
                position=definition.position,
                configuration=definition.configuration,
                retry_count=definition.retry_count,
                source_dataset_id=(
                    str(definition.source_dataset_id) if definition.source_dataset_id else None
                ),
                target_dataset_id=(
                    str(definition.target_dataset_id) if definition.target_dataset_id else None
                ),
                load_strategy=definition.load_strategy,
            )
            step.mappings = [
                ColumnMapping(**mapping.model_dump()) for mapping in definition.mappings
            ]
            step.transformations = [
                Transformation(
                    **item.model_dump(exclude={"input_dataset_id", "output_dataset_id"}),
                    input_dataset_id=(
                        str(item.input_dataset_id) if item.input_dataset_id else None
                    ),
                    output_dataset_id=(
                        str(item.output_dataset_id) if item.output_dataset_id else None
                    ),
                )
                for item in definition.transformations
            ]
            pipeline.steps.append(step)

    def _set_dependencies(
        self, pipeline: Pipeline, definitions: list[PipelineDependencyInput]
    ) -> None:
        proposed_ids = [str(item.depends_on_pipeline_id) for item in definitions]
        for dependency_id in proposed_ids:
            if dependency_id == pipeline.id:
                raise self._configuration_error("A pipeline cannot depend on itself")
            if self.repository.get(dependency_id) is None:
                raise self._configuration_error(
                    f"Dependency pipeline '{dependency_id}' does not exist"
                )
        self._validate_acyclic_dependencies(pipeline.id, proposed_ids)
        pipeline.dependencies = [
            PipelineDependency(
                depends_on_pipeline_id=str(item.depends_on_pipeline_id),
                dependency_type=item.dependency_type,
            )
            for item in definitions
        ]

    def _set_incremental_configuration(
        self,
        pipeline: Pipeline,
        definition: IncrementalConfigurationInput | None,
    ) -> None:
        if definition is None:
            pipeline.incremental_config = None
            return
        if definition.dataset_id is not None:
            self._ensure_dataset_exists(str(definition.dataset_id))
        pipeline.incremental_config = IncrementalConfiguration(
            strategy=definition.strategy,
            dataset_id=str(definition.dataset_id) if definition.dataset_id else None,
            watermark_column=definition.watermark_column,
            initial_value=definition.initial_value,
            options=definition.options,
        )

    def _validate_dataset_references(self, definition: PipelineStepInput) -> None:
        ids = {
            str(value)
            for value in (definition.source_dataset_id, definition.target_dataset_id)
            if value is not None
        }
        for transformation in definition.transformations:
            ids.update(
                str(value)
                for value in (
                    transformation.input_dataset_id,
                    transformation.output_dataset_id,
                )
                if value is not None
            )
        for dataset_id in ids:
            self._ensure_dataset_exists(dataset_id)

    def _ensure_dataset_exists(self, dataset_id: str) -> None:
        if self.session.get(Dataset, dataset_id) is None:
            raise self._configuration_error(f"Dataset '{dataset_id}' does not exist")

    def _validate_acyclic_dependencies(
        self, pipeline_id: str, proposed_dependencies: list[str]
    ) -> None:
        edges: dict[str, set[str]] = {}
        for child, parent in self.repository.dependency_edges(
            exclude_pipeline_id=pipeline_id
        ):
            edges.setdefault(child, set()).add(parent)
        edges[pipeline_id] = set(proposed_dependencies)

        def reaches_origin(node: str, visited: set[str]) -> bool:
            if node == pipeline_id:
                return True
            if node in visited:
                return False
            visited.add(node)
            return any(reaches_origin(parent, visited) for parent in edges.get(node, set()))

        if any(reaches_origin(item, set()) for item in proposed_dependencies):
            raise self._configuration_error("Pipeline dependencies cannot contain a cycle")

    def _ensure_unique_name(self, name: str, exclude_id: str | None = None) -> None:
        existing = self.repository.get_by_name(name)
        if existing is not None and existing.id != exclude_id:
            raise AppError(
                message=f"A pipeline named '{name}' already exists",
                status_code=409,
                code="pipeline_name_conflict",
            )

    def _commit(self, operation: Callable[[], object]) -> None:
        try:
            operation()
            self.session.commit()
        except (MetadataConflictError, IntegrityError) as exc:
            self.session.rollback()
            raise AppError(
                message="Pipeline metadata violates a uniqueness or integrity constraint",
                status_code=409,
                code="pipeline_conflict",
            ) from exc

    @staticmethod
    def _configuration_error(message: str) -> AppError:
        return AppError(message=message, status_code=422, code="invalid_pipeline_configuration")
