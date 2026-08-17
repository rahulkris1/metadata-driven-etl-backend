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


class LoadStrategy(StrEnum):
    APPEND = "append"
    OVERWRITE = "overwrite"
    MERGE = "merge"
    UPSERT = "upsert"
    SCD_TYPE_1 = "scd_type_1"
    SCD_TYPE_2 = "scd_type_2"


class DependencyType(StrEnum):
    SUCCESS = "success"
    COMPLETION = "completion"


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
