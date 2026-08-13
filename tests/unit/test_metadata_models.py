from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.database import Base
from app.models.enums import (
    DatasetType,
    ExecutionStatus,
    IncrementalStrategy,
    QualitySeverity,
    SourceType,
    StepType,
)
from app.models.metadata import (
    Connection,
    Dataset,
    DatasetColumn,
    Execution,
    IncrementalConfiguration,
    Pipeline,
    PipelineStep,
    QualityRule,
    Source,
    Transformation,
)
from app.models.validation import MetadataValidationError
from app.repositories.base import MetadataConflictError
from app.repositories.metadata import DatasetRepository, PipelineRepository, SourceRepository


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as database_session:
        yield database_session
    engine.dispose()


def test_complete_metadata_graph_and_repository_queries(session: Session) -> None:
    source = Source(name="  sales  ", source_type=SourceType.DATABASE)
    connection = Connection(name="primary", connection_type="postgresql", source=source)
    source_repository = SourceRepository(session)
    source_repository.add(source)

    input_dataset = Dataset(
        name="orders",
        namespace="public",
        dataset_type=DatasetType.TABLE,
        source=source,
        connection=connection,
    )
    output_dataset = Dataset(
        name="orders_clean",
        namespace="analytics",
        dataset_type=DatasetType.TABLE,
        source=source,
        connection=connection,
    )
    order_id = DatasetColumn(
        name="order_id", data_type="bigint", ordinal_position=0, is_primary_key=True
    )
    input_dataset.columns.append(order_id)

    pipeline = Pipeline(name="daily_orders")
    step = PipelineStep(name="clean", step_type=StepType.TRANSFORM, position=0)
    step.transformations.append(
        Transformation(
            name="remove_nulls",
            transformation_type="sql",
            expression="order_id IS NOT NULL",
            input_dataset=input_dataset,
            output_dataset=output_dataset,
        )
    )
    pipeline.steps.append(step)
    pipeline.incremental_config = IncrementalConfiguration(
        strategy=IncrementalStrategy.WATERMARK,
        watermark_column="updated_at",
        dataset=input_dataset,
    )
    execution = Execution(
        pipeline=pipeline,
        run_id="run-001",
        status=ExecutionStatus.SUCCEEDED,
        started_at=datetime.now(UTC),
    )
    execution.finished_at = execution.started_at + timedelta(minutes=1)
    input_dataset.quality_rules.append(
        QualityRule(
            name="order_id_not_null",
            rule_type="not_null",
            severity=QualitySeverity.ERROR,
            column=order_id,
        )
    )

    session.add_all([input_dataset, output_dataset, pipeline, execution])
    session.commit()

    assert source.name == "sales"
    assert PipelineRepository(session).get_with_steps(pipeline.id).steps[0].name == "clean"
    loaded_dataset = DatasetRepository(session).get_with_columns(input_dataset.id)
    assert loaded_dataset is not None
    assert loaded_dataset.columns[0].name == "order_id"


def test_unique_source_name_is_reported_as_metadata_conflict(session: Session) -> None:
    repository = SourceRepository(session)
    repository.add(Source(name="sales", source_type=SourceType.DATABASE))
    session.commit()

    with pytest.raises(MetadataConflictError):
        repository.add(Source(name="sales", source_type=SourceType.API))


def test_watermark_strategy_requires_a_watermark_column(session: Session) -> None:
    pipeline = Pipeline(name="invalid_incremental")
    pipeline.incremental_config = IncrementalConfiguration(
        strategy=IncrementalStrategy.WATERMARK
    )
    session.add(pipeline)

    with pytest.raises(MetadataValidationError, match="watermark_column"):
        session.flush()


def test_quality_rule_column_must_belong_to_its_dataset(session: Session) -> None:
    source = Source(name="quality-source", source_type=SourceType.DATABASE)
    first = Dataset(
        name="first", namespace="default", dataset_type=DatasetType.TABLE, source=source
    )
    second = Dataset(
        name="second", namespace="default", dataset_type=DatasetType.TABLE, source=source
    )
    foreign_column = DatasetColumn(name="id", data_type="integer", ordinal_position=0)
    second.columns.append(foreign_column)
    first.quality_rules.append(
        QualityRule(
            name="invalid_rule",
            rule_type="not_null",
            severity=QualitySeverity.ERROR,
            column=foreign_column,
        )
    )
    session.add(source)

    with pytest.raises(MetadataValidationError, match="must belong"):
        session.flush()
