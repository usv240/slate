from slate_app.store import DeliveryStore


def test_memory_store_probe_is_live():
    assert DeliveryStore().probe() is True


def test_configured_store_defaults_to_official_rest_transport(monkeypatch):
    import sys
    import types

    observed = {}

    class FakeApiClient:
        def __init__(self, **kwargs):
            observed.update(kwargs)

    class FakeCollection:
        pass

    class FakeClient:
        def __init__(self, *, project):
            observed["project"] = project
            self._credentials = "credentials"
            self._client_options = "options"
            self._firestore_api_internal = None

        def collection(self, name):
            observed["collection"] = name
            observed["api"] = self._firestore_api_internal
            return FakeCollection()

    fake_firestore = types.ModuleType("google.cloud.firestore")
    fake_firestore.Client = FakeClient
    fake_service = types.ModuleType("google.cloud.firestore_v1.services.firestore")
    fake_service.FirestoreClient = FakeApiClient
    monkeypatch.setitem(sys.modules, "google.cloud.firestore", fake_firestore)
    monkeypatch.setitem(
        sys.modules,
        "google.cloud.firestore_v1.services.firestore",
        fake_service,
    )
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    monkeypatch.setenv("SLATE_FIRESTORE_COLLECTION", "deliveries")
    monkeypatch.delenv("SLATE_FIRESTORE_TRANSPORT", raising=False)

    store = DeliveryStore()

    assert store.backend == "firestore"
    assert observed["transport"] == "rest"
    assert observed["project"] == "project"
    assert observed["collection"] == "deliveries"
    assert observed["api"] is not None
