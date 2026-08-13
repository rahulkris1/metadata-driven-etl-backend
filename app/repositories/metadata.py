from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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
from app.repositories.base import Repository


class SourceRepository(Repository[Source]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Source)

    def get_by_name(self, name: str) -> Source | None:
        return self.session.scalar(select(Source).where(Source.name == name.strip()))


class ConnectionRepository(Repository[Connection]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Connection)

    def get_by_name(self, source_id: str, name: str) -> Connection | None:
        return self.session.scalar(
            select(Connection).where(
                Connection.source_id == source_id, Connection.name == name.strip()
            )
        )


class PipelineRepository(Repository[Pipeline]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Pipeline)

    def get_by_name(self, name: str) -> Pipeline | None:
        return self.session.scalar(select(Pipeline).where(Pipeline.name == name.strip()))

    def get_with_steps(self, pipeline_id: str) -> Pipeline | None:
        return self.session.scalar(
            select(Pipeline)
            .options(selectinload(Pipeline.steps))
            .where(Pipeline.id == pipeline_id)
        )


class PipelineStepRepository(Repository[PipelineStep]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, PipelineStep)


class DatasetRepository(Repository[Dataset]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Dataset)

    def get_by_qualified_name(
        self, source_id: str, namespace: str, name: str
    ) -> Dataset | None:
        return self.session.scalar(
            select(Dataset).where(
                Dataset.source_id == source_id,
                Dataset.namespace == namespace.strip(),
                Dataset.name == name.strip(),
            )
        )

    def get_with_columns(self, dataset_id: str) -> Dataset | None:
        return self.session.scalar(
            select(Dataset)
            .options(selectinload(Dataset.columns))
            .where(Dataset.id == dataset_id)
        )


class DatasetColumnRepository(Repository[DatasetColumn]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DatasetColumn)


class TransformationRepository(Repository[Transformation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Transformation)


class IncrementalConfigurationRepository(Repository[IncrementalConfiguration]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, IncrementalConfiguration)


class ExecutionRepository(Repository[Execution]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Execution)

    def get_by_run_id(self, run_id: str) -> Execution | None:
        return self.session.scalar(select(Execution).where(Execution.run_id == run_id))

    def list_for_pipeline(self, pipeline_id: str) -> Sequence[Execution]:
        return self.session.scalars(
            select(Execution)
            .where(Execution.pipeline_id == pipeline_id)
            .order_by(Execution.created_at.desc())
        ).all()


class QualityRuleRepository(Repository[QualityRule]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, QualityRule)

    def list_for_dataset(self, dataset_id: str) -> Sequence[QualityRule]:
        return self.session.scalars(
            select(QualityRule).where(QualityRule.dataset_id == dataset_id)
        ).all()
