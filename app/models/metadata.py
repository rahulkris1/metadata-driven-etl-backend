from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import ActiveStateMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    DatasetType,
    DependencyType,
    ExecutionStatus,
    IncrementalStrategy,
    LoadStrategy,
    QualitySeverity,
    SourceType,
    StepType,
)


class Source(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("name", name="uq_sources_name"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    connections: Mapped[list[Connection]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    datasets: Mapped[list[Dataset]] = relationship(back_populates="source")


class Connection(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("source_id", "name", name="uq_connections_source_name"),)

    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    connection_type: Mapped[str] = mapped_column(String(50), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    secret_reference: Mapped[str | None] = mapped_column(String(500))

    source: Mapped[Source] = relationship(back_populates="connections")
    datasets: Mapped[list[Dataset]] = relationship(back_populates="connection")


class Pipeline(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "pipelines"
    __table_args__ = (UniqueConstraint("name", name="uq_pipelines_name"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    schedule: Mapped[str | None] = mapped_column(String(120))
    schedule_timezone: Mapped[str] = mapped_column(
        String(64), default="UTC", server_default="UTC", nullable=False
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    steps: Mapped[list[PipelineStep]] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan", order_by="PipelineStep.position"
    )
    incremental_config: Mapped[IncrementalConfiguration | None] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan", uselist=False
    )
    executions: Mapped[list[Execution]] = relationship(back_populates="pipeline")
    dependencies: Mapped[list[PipelineDependency]] = relationship(
        back_populates="pipeline",
        cascade="all, delete-orphan",
        foreign_keys="PipelineDependency.pipeline_id",
    )
    dependents: Mapped[list[PipelineDependency]] = relationship(
        back_populates="depends_on_pipeline",
        foreign_keys="PipelineDependency.depends_on_pipeline_id",
    )


class PipelineStep(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "pipeline_steps"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "name", name="uq_pipeline_steps_pipeline_name"),
        UniqueConstraint("pipeline_id", "position", name="uq_pipeline_steps_pipeline_position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
    )

    pipeline_id: Mapped[str] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    step_type: Mapped[StepType] = mapped_column(Enum(StepType), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), index=True
    )
    target_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), index=True
    )
    load_strategy: Mapped[LoadStrategy | None] = mapped_column(Enum(LoadStrategy))

    pipeline: Mapped[Pipeline] = relationship(back_populates="steps")
    transformations: Mapped[list[Transformation]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )
    mappings: Mapped[list[ColumnMapping]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )
    source_dataset: Mapped[Dataset | None] = relationship(
        foreign_keys=[source_dataset_id], back_populates="source_steps"
    )
    target_dataset: Mapped[Dataset | None] = relationship(
        foreign_keys=[target_dataset_id], back_populates="target_steps"
    )


class Dataset(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "namespace", "name", name="uq_datasets_source_namespace_name"
        ),
    )

    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("connections.id", ondelete="SET NULL"), index=True
    )
    namespace: Mapped[str] = mapped_column(String(255), default="default", nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_type: Mapped[DatasetType] = mapped_column(Enum(DatasetType), nullable=False)
    location: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    source: Mapped[Source] = relationship(back_populates="datasets")
    connection: Mapped[Connection | None] = relationship(back_populates="datasets")
    columns: Mapped[list[DatasetColumn]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetColumn.ordinal_position",
    )
    transformations_in: Mapped[list[Transformation]] = relationship(
        back_populates="input_dataset", foreign_keys="Transformation.input_dataset_id"
    )
    transformations_out: Mapped[list[Transformation]] = relationship(
        back_populates="output_dataset", foreign_keys="Transformation.output_dataset_id"
    )
    quality_rules: Mapped[list[QualityRule]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )
    source_steps: Mapped[list[PipelineStep]] = relationship(
        foreign_keys="PipelineStep.source_dataset_id", back_populates="source_dataset"
    )
    target_steps: Mapped[list[PipelineStep]] = relationship(
        foreign_keys="PipelineStep.target_dataset_id", back_populates="target_dataset"
    )


class DatasetColumn(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "dataset_columns"
    __table_args__ = (
        UniqueConstraint("dataset_id", "name", name="uq_dataset_columns_dataset_name"),
        UniqueConstraint(
            "dataset_id", "ordinal_position", name="uq_dataset_columns_dataset_ordinal"
        ),
        CheckConstraint("ordinal_position >= 0", name="ordinal_non_negative"),
    )

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_nullable: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_primary_key: Mapped[bool] = mapped_column(default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    dataset: Mapped[Dataset] = relationship(back_populates="columns")
    quality_rules: Mapped[list[QualityRule]] = relationship(back_populates="column")


class Transformation(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "transformations"
    __table_args__ = (UniqueConstraint("step_id", "name", name="uq_transformations_step_name"),)

    step_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    input_dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), index=True)
    output_dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    transformation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    expression: Mapped[str | None] = mapped_column(Text)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    step: Mapped[PipelineStep] = relationship(back_populates="transformations")
    input_dataset: Mapped[Dataset | None] = relationship(
        back_populates="transformations_in", foreign_keys=[input_dataset_id]
    )
    output_dataset: Mapped[Dataset | None] = relationship(
        back_populates="transformations_out", foreign_keys=[output_dataset_id]
    )


class ColumnMapping(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "column_mappings"
    __table_args__ = (
        UniqueConstraint("step_id", "target_column", name="uq_column_mappings_step_target"),
    )

    step_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_column: Mapped[str | None] = mapped_column(String(255))
    target_column: Mapped[str] = mapped_column(String(255), nullable=False)
    expression: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str | None] = mapped_column(String(100))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    step: Mapped[PipelineStep] = relationship(back_populates="mappings")


class PipelineDependency(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "pipeline_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_id", "depends_on_pipeline_id", name="uq_pipeline_dependencies_pair"
        ),
        CheckConstraint("pipeline_id <> depends_on_pipeline_id", name="not_self_dependency"),
    )

    pipeline_id: Mapped[str] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    depends_on_pipeline_id: Mapped[str] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dependency_type: Mapped[DependencyType] = mapped_column(
        Enum(DependencyType), default=DependencyType.SUCCESS, nullable=False
    )

    pipeline: Mapped[Pipeline] = relationship(
        back_populates="dependencies", foreign_keys=[pipeline_id]
    )
    depends_on_pipeline: Mapped[Pipeline] = relationship(
        back_populates="dependents", foreign_keys=[depends_on_pipeline_id]
    )


class IncrementalConfiguration(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "incremental_configurations"
    __table_args__ = (UniqueConstraint("pipeline_id", name="uq_incremental_config_pipeline"),)

    pipeline_id: Mapped[str] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), index=True)
    strategy: Mapped[IncrementalStrategy] = mapped_column(Enum(IncrementalStrategy), nullable=False)
    watermark_column: Mapped[str | None] = mapped_column(String(255))
    initial_value: Mapped[str | None] = mapped_column(String(1000))
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    pipeline: Mapped[Pipeline] = relationship(back_populates="incremental_config")
    dataset: Mapped[Dataset | None] = relationship()


class Execution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_executions_run_id"),
        Index("ix_executions_pipeline_status", "pipeline_id", "status"),
    )

    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus), default=ExecutionStatus.PENDING, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_by: Mapped[str | None] = mapped_column(String(255))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    pipeline: Mapped[Pipeline] = relationship(back_populates="executions")


class QualityRule(UUIDPrimaryKeyMixin, TimestampMixin, ActiveStateMixin, Base):
    __tablename__ = "quality_rules"
    __table_args__ = (
        UniqueConstraint("dataset_id", "name", name="uq_quality_rules_dataset_name"),
    )

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    column_id: Mapped[str | None] = mapped_column(
        ForeignKey("dataset_columns.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[QualitySeverity] = mapped_column(Enum(QualitySeverity), nullable=False)
    expression: Mapped[str | None] = mapped_column(Text)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    dataset: Mapped[Dataset] = relationship(back_populates="quality_rules")
    column: Mapped[DatasetColumn | None] = relationship(back_populates="quality_rules")
