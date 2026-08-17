import re
from datetime import datetime
from math import ceil
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    DependencyType,
    IncrementalStrategy,
    LoadStrategy,
    StepType,
)

CRON_TOKEN = re.compile(r"^[0-9*/?,\-]+$")


def validate_cron(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    fields = value.split(" ")
    if len(fields) != 5 or any(not CRON_TOKEN.fullmatch(field) for field in fields):
        raise ValueError("schedule must be a valid five-field cron expression")
    return value


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("schedule_timezone must be a valid IANA timezone") from exc
    return value


class ColumnMappingInput(BaseModel):
    source_column: str | None = Field(default=None, max_length=255)
    target_column: str = Field(min_length=1, max_length=255)
    expression: str | None = None
    data_type: str | None = Field(default=None, max_length=100)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_column", "target_column")
    @classmethod
    def strip_column_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("column names cannot be blank")
        return value

    @model_validator(mode="after")
    def require_source_or_expression(self) -> "ColumnMappingInput":
        if not self.source_column and not (self.expression or "").strip():
            raise ValueError("A mapping requires source_column or expression")
        return self


class TransformationInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    transformation_type: str = Field(min_length=1, max_length=80)
    expression: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    input_dataset_id: UUID | None = None
    output_dataset_id: UUID | None = None

    @field_validator("name", "transformation_type")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be blank")
        return value

    @model_validator(mode="after")
    def require_configuration(self) -> "TransformationInput":
        if not (self.expression or "").strip() and not self.configuration:
            raise ValueError("A transformation requires expression or configuration")
        return self


class PipelineStepInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    step_type: StepType
    position: int = Field(ge=0)
    configuration: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = Field(default=0, ge=0, le=100)
    source_dataset_id: UUID | None = None
    target_dataset_id: UUID | None = None
    load_strategy: LoadStrategy | None = None
    transformations: list[TransformationInput] = Field(default_factory=list)
    mappings: list[ColumnMappingInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_step(self) -> "PipelineStepInput":
        if self.step_type == StepType.LOAD and self.load_strategy is None:
            raise ValueError("load_strategy is required for load steps")
        mapping_targets = [mapping.target_column.casefold() for mapping in self.mappings]
        if len(mapping_targets) != len(set(mapping_targets)):
            raise ValueError("Mapping target columns must be unique within a step")
        transformation_names = [item.name.casefold() for item in self.transformations]
        if len(transformation_names) != len(set(transformation_names)):
            raise ValueError("Transformation names must be unique within a step")
        return self


class PipelineDependencyInput(BaseModel):
    depends_on_pipeline_id: UUID
    dependency_type: DependencyType = DependencyType.SUCCESS


class IncrementalConfigurationInput(BaseModel):
    strategy: IncrementalStrategy
    dataset_id: UUID | None = None
    watermark_column: str | None = Field(default=None, max_length=255)
    initial_value: str | None = Field(default=None, max_length=1000)
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_watermark(self) -> "IncrementalConfigurationInput":
        if self.strategy == IncrementalStrategy.WATERMARK and not (
            self.watermark_column or ""
        ).strip():
            raise ValueError("watermark_column is required for watermark strategy")
        return self


class PipelineDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    schedule: str | None = Field(default=None, max_length=120)
    schedule_timezone: str = Field(default="UTC", max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)
    steps: list[PipelineStepInput] = Field(min_length=1)
    dependencies: list[PipelineDependencyInput] = Field(default_factory=list)
    incremental_configuration: IncrementalConfigurationInput | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, value: str | None) -> str | None:
        return validate_cron(value)

    @field_validator("schedule_timezone")
    @classmethod
    def validate_schedule_timezone(cls, value: str) -> str:
        return validate_timezone(value)

    @model_validator(mode="after")
    def validate_definition(self) -> "PipelineDefinition":
        names = [step.name.casefold() for step in self.steps]
        positions = [step.position for step in self.steps]
        dependencies = [item.depends_on_pipeline_id for item in self.dependencies]
        if len(names) != len(set(names)):
            raise ValueError("Step names must be unique within a pipeline")
        if len(positions) != len(set(positions)):
            raise ValueError("Step positions must be unique within a pipeline")
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("Pipeline dependencies must be unique")
        return self


class PipelineCreate(PipelineDefinition):
    pass


class PipelineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    schedule: str | None = Field(default=None, max_length=120)
    schedule_timezone: str | None = Field(default=None, max_length=64)
    parameters: dict[str, Any] | None = None
    steps: list[PipelineStepInput] | None = Field(default=None, min_length=1)
    dependencies: list[PipelineDependencyInput] | None = None
    incremental_configuration: IncrementalConfigurationInput | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, value: str | None) -> str | None:
        return validate_cron(value)

    @field_validator("schedule_timezone")
    @classmethod
    def validate_schedule_timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value) if value is not None else None

    @model_validator(mode="after")
    def validate_update(self) -> "PipelineUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if self.steps is not None:
            names = [step.name.casefold() for step in self.steps]
            positions = [step.position for step in self.steps]
            if len(names) != len(set(names)) or len(positions) != len(set(positions)):
                raise ValueError("Step names and positions must be unique within a pipeline")
        if self.dependencies is not None:
            ids = [item.depends_on_pipeline_id for item in self.dependencies]
            if len(ids) != len(set(ids)):
                raise ValueError("Pipeline dependencies must be unique")
        return self


class PipelineStatusUpdate(BaseModel):
    is_active: bool


class ColumnMappingResponse(ColumnMappingInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_active: bool


class TransformationResponse(TransformationInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    input_dataset_id: str | None
    output_dataset_id: str | None
    is_active: bool


class PipelineStepResponse(PipelineStepInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_dataset_id: str | None
    target_dataset_id: str | None
    transformations: list[TransformationResponse]
    mappings: list[ColumnMappingResponse]
    is_active: bool


class PipelineDependencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    depends_on_pipeline_id: str
    dependency_type: DependencyType
    is_active: bool


class IncrementalConfigurationResponse(IncrementalConfigurationInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dataset_id: str | None
    is_active: bool


class PipelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    schedule: str | None
    schedule_timezone: str
    parameters: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    steps: list[PipelineStepResponse]
    dependencies: list[PipelineDependencyResponse]
    incremental_configuration: IncrementalConfigurationResponse | None = Field(
        validation_alias="incremental_config"
    )


class PipelineSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str | None
    schedule: str | None
    schedule_timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PipelineListResponse(BaseModel):
    items: list[PipelineSummary]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(
        cls, items: list[PipelineSummary], *, total: int, page: int, page_size: int
    ) -> "PipelineListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=ceil(total / page_size) if total else 0,
        )
