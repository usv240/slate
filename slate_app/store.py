from __future__ import annotations

from threading import Lock

from .models import DeliveryRecord


class DeliveryStore:
    def __init__(self) -> None:
        self._records: dict[str, DeliveryRecord] = {}
        self._lock = Lock()

    def put(self, record: DeliveryRecord) -> DeliveryRecord:
        with self._lock:
            self._records[record.delivery_id] = record.model_copy(deep=True)
        return record

    def get(self, delivery_id: str) -> DeliveryRecord | None:
        with self._lock:
            record = self._records.get(delivery_id)
            return record.model_copy(deep=True) if record else None

    def list(self) -> list[DeliveryRecord]:
        with self._lock:
            return [record.model_copy(deep=True) for record in self._records.values()]
