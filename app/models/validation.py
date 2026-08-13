from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.enums import IncrementalStrategy
from app.models.metadata import (
    Dataset,
    DatasetColumn,
    Execution,
    IncrementalConfiguration,
    PipelineStep,
    QualityRule,
)


class MetadataValidationError(ValueError):
    """Raised when metadata violates a domain rule before persistence."""


def _require_trimmed_name(instance: object) -> None:
    name = getattr(instance, "name", None)
    if name is not None:
        normalized = name.strip()
        if not normalized:
            raise MetadataValidationError(f"{type(instance).__name__}.name cannot be blank")
        instance.name = normalized  # type: ignore[attr-defined]


@event.listens_for(Session, "before_flush")
def validate_metadata(session: Session, *_: object) -> None:
    for instance in session.new.union(session.dirty):
        _require_trimmed_name(instance)

        if isinstance(instance, PipelineStep) and instance.position < 0:
            raise MetadataValidationError("Pipeline-step position cannot be negative")

        if isinstance(instance, DatasetColumn) and instance.ordinal_position < 0:
            raise MetadataValidationError("Column ordinal position cannot be negative")

        if isinstance(instance, IncrementalConfiguration):
            if (
                instance.strategy == IncrementalStrategy.WATERMARK
                and not (instance.watermark_column or "").strip()
            ):
                raise MetadataValidationError(
                    "watermark_column is required for the watermark incremental strategy"
                )

        if isinstance(instance, Execution):
            if (
                instance.started_at is not None
                and instance.finished_at is not None
                and instance.finished_at < instance.started_at
            ):
                raise MetadataValidationError("finished_at cannot be earlier than started_at")

        if isinstance(instance, QualityRule) and instance.column is not None:
            if instance.dataset is not None and instance.column.dataset is not instance.dataset:
                raise MetadataValidationError(
                    "A quality-rule column must belong to the rule's dataset"
                )

        if isinstance(instance, Dataset) and instance.connection is not None:
            if instance.source is not None and instance.connection.source is not instance.source:
                raise MetadataValidationError(
                    "A dataset connection must belong to the dataset's source"
                )
