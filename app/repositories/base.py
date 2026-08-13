from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class MetadataConflictError(ValueError):
    """Raised when a metadata uniqueness constraint is violated."""


class Repository(Generic[ModelT]):
    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def get(self, entity_id: str) -> ModelT | None:
        return self.session.get(self.model, entity_id)

    def list(self, *, active_only: bool = True) -> Sequence[ModelT]:
        statement = select(self.model)
        if active_only and hasattr(self.model, "is_active"):
            statement = statement.where(self.model.is_active.is_(True))  # type: ignore[attr-defined]
        return self.session.scalars(statement).all()

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        self._flush()
        return entity

    def update(self, entity: ModelT, **values: Any) -> ModelT:
        for field, value in values.items():
            if not hasattr(entity, field):
                raise AttributeError(f"{self.model.__name__} has no field {field!r}")
            setattr(entity, field, value)
        self._flush()
        return entity

    def deactivate(self, entity: ModelT) -> ModelT:
        if not hasattr(entity, "is_active"):
            raise TypeError(f"{self.model.__name__} does not support active state")
        entity.is_active = False  # type: ignore[attr-defined]
        self._flush()
        return entity

    def delete(self, entity: ModelT) -> None:
        self.session.delete(entity)
        self._flush()

    def _flush(self) -> None:
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise MetadataConflictError(
                f"{self.model.__name__} violates a uniqueness or integrity constraint"
            ) from exc
