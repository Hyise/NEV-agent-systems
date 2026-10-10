"""Pure states and errors for the versioned vehicle-series catalog."""

from enum import StrEnum


class CatalogRunStatus(StrEnum):
    QUEUED = "queued"
    DISCOVERING = "discovering"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    COMPLETED_SHORT = "completed_short"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CatalogRunConflict(ValueError):
    """Raised when a catalog run conflicts with current catalog state."""


class CatalogSelectionError(ValueError):
    """Raised when requested series cannot be resolved from the active catalog."""

    def __init__(self, message: str, invalid_series_ids: list[str] | None = None):
        super().__init__(message)
        self.invalid_series_ids = invalid_series_ids or []
