from enum import StrEnum


class SourceType(StrEnum):
    DATABASE = "database"
    FILE = "file"
    API = "api"
    STREAM = "stream"
    CLOUD_STORAGE = "cloud_storage"


class StepType(StrEnum):
    EXTRACT = "extract"
    TRANSFORM = "transform"
    LOAD = "load"
    VALIDATE = "validate"


class DatasetType(StrEnum):
    TABLE = "table"
    VIEW = "view"
    FILE = "file"
    STREAM = "stream"


class IncrementalStrategy(StrEnum):
    FULL = "full"
    WATERMARK = "watermark"
    CDC = "cdc"
    APPEND = "append"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
