from datetime import datetime
from math import ceil
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import SourceType


class SourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: SourceType
    description: str | None = Field(default=None, max_length=5000)
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_type: SourceType | None = None
    description: str | None = Field(default=None, max_length=5000)
    properties: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value

    @model_validator(mode="after")
    def require_a_change(self) -> "SourceUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class SourceStatusUpdate(BaseModel):
    is_active: bool


class SourceResponse(SourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(
        cls, items: list[SourceResponse], *, total: int, page: int, page_size: int
    ) -> "SourceListResponse":
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=ceil(total / page_size) if total else 0,
        )
