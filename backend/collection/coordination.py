"""Cross-service reservation for external Autohome access."""

from dataclasses import dataclass
from threading import Lock
from typing import Literal

from .domain import TaskControlError

ExternalAccessKind = Literal["catalog", "collection", "sales"]


@dataclass(frozen=True)
class ExternalAccessReservation:
    kind: ExternalAccessKind
    operation_id: str


class ExternalAccessCoordinator:
    def __init__(self):
        self._lock = Lock()
        self._reservation: ExternalAccessReservation | None = None

    def try_reserve(self, kind: ExternalAccessKind, operation_id: str) -> bool:
        reservation = ExternalAccessReservation(kind, operation_id)
        with self._lock:
            if self._reservation is not None:
                return False
            self._reservation = reservation
            return True

    def release(self, kind: ExternalAccessKind, operation_id: str) -> None:
        expected = ExternalAccessReservation(kind, operation_id)
        with self._lock:
            if self._reservation != expected:
                raise TaskControlError("外部访问预约与释放方不一致")
            self._reservation = None

    def current(self) -> ExternalAccessReservation | None:
        with self._lock:
            return self._reservation
