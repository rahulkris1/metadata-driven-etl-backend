from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.enums import SourceType
from app.models.metadata import Source
from app.repositories.base import MetadataConflictError
from app.repositories.metadata import SourceRepository
from app.schemas.source import SourceCreate, SourceUpdate


class SourceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SourceRepository(session)

    def create(self, payload: SourceCreate) -> Source:
        if self.repository.get_by_name(payload.name) is not None:
            raise self._duplicate_name(payload.name)
        source = Source(**payload.model_dump())
        self._persist(lambda: self.repository.add(source))
        return source

    def get(self, source_id: str) -> Source:
        source = self.repository.get(source_id)
        if source is None:
            raise AppError(
                message="Source not found", status_code=404, code="source_not_found"
            )
        return source

    def list(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        source_type: SourceType | None,
        is_active: bool | None,
    ) -> tuple[list[Source], int]:
        items, total = self.repository.paginate(
            offset=(page - 1) * page_size,
            limit=page_size,
            search=search,
            source_type=source_type,
            is_active=is_active,
        )
        return list(items), total

    def update(self, source_id: str, payload: SourceUpdate) -> Source:
        source = self.get(source_id)
        values = payload.model_dump(exclude_unset=True)
        new_name = values.get("name")
        if new_name is not None:
            duplicate = self.repository.get_by_name(new_name)
            if duplicate is not None and duplicate.id != source.id:
                raise self._duplicate_name(new_name)
        self._persist(lambda: self.repository.update(source, **values))
        return source

    def set_status(self, source_id: str, *, is_active: bool) -> Source:
        source = self.get(source_id)
        self._persist(lambda: self.repository.update(source, is_active=is_active))
        return source

    def delete(self, source_id: str) -> None:
        source = self.get(source_id)
        self._persist(lambda: self.repository.deactivate(source))

    def _persist(self, operation: Callable[[], object]) -> None:
        try:
            operation()
            self.session.commit()
        except MetadataConflictError as exc:
            raise AppError(
                message="A source with this name already exists",
                status_code=409,
                code="source_name_conflict",
            ) from exc

    @staticmethod
    def _duplicate_name(name: str) -> AppError:
        return AppError(
            message=f"A source named '{name}' already exists",
            status_code=409,
            code="source_name_conflict",
        )
