from __future__ import annotations

import os
from threading import Lock

from .models import DeliveryRecord


class DeliveryStore:
    def __init__(self) -> None:
        self._records: dict[str, DeliveryRecord] = {}
        self._lock = Lock()
        self._collection_name = os.getenv("SLATE_FIRESTORE_COLLECTION")
        self._collection = None
        if self._collection_name:
            from google.cloud import firestore

            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            self._collection = firestore.Client(project=project).collection(self._collection_name)

    @property
    def backend(self) -> str:
        return "firestore" if self._collection is not None else "memory"

    def put(self, record: DeliveryRecord) -> DeliveryRecord:
        if self._collection is not None:
            self._collection.document(record.delivery_id).set(record.model_dump(mode="json"))
            return record
        with self._lock:
            self._records[record.delivery_id] = record.model_copy(deep=True)
        return record

    def get(self, delivery_id: str) -> DeliveryRecord | None:
        if self._collection is not None:
            snapshot = self._collection.document(delivery_id).get()
            return DeliveryRecord.model_validate(snapshot.to_dict()) if snapshot.exists else None
        with self._lock:
            record = self._records.get(delivery_id)
            return record.model_copy(deep=True) if record else None

    def list(self) -> list[DeliveryRecord]:
        if self._collection is not None:
            records = [DeliveryRecord.model_validate(item.to_dict()) for item in self._collection.stream()]
            return sorted(records, key=lambda item: item.created_at, reverse=True)
        with self._lock:
            return [record.model_copy(deep=True) for record in self._records.values()]
