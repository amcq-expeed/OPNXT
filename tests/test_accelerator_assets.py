from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure.accelerator_store import get_accelerator_store
from src.orchestrator.infrastructure.doc_store import get_doc_store
from src.orchestrator.services.accelerator_service import (
    _package_ready_to_run_bundle,
    _slugify,
    _build_live_preview_html,
)
from tests.utils import otp_login


client = TestClient(app)


def test_bundle_and_preview_endpoints(tmp_path, monkeypatch):
    store = get_accelerator_store()
    doc_store = get_doc_store()
    headers, _ = otp_login(client, "adam.thacker@expeed.com")

    session = store.create_session("design-build-guidance", created_by="tester")
    session_id = session.session_id

    bundle_bytes = _package_ready_to_run_bundle({"hello.txt": "hi"})
    slug = _slugify("Design Build Guidance")
    bundle_filename = f"{slug}-bundle.zip"

    store.add_artifact(session_id, bundle_filename, project_id=None, meta={"version": 1})
    store.save_asset(session_id, bundle_filename, bundle_bytes)

    preview_html = _build_live_preview_html("Budget Master")
    preview_filename = f"{slug}-preview.html"
    store.add_artifact(
        session_id,
        preview_filename,
        project_id=None,
        meta={"version": 2},
    )
    doc_store.save_accelerator_preview(
        session_id,
        preview_filename,
        preview_html,
        {"version": 2},
    )
    store_metadata = store.get_session(session_id).metadata
    store_metadata.setdefault("artifacts", store.list_artifacts(session_id))
    store.update_session_metadata(session_id, store_metadata)

    resp = client.get(
        f"/accelerators/sessions/{session_id}/artifacts/{bundle_filename}/download",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.headers.get("content-disposition")
    assert resp.content == bundle_bytes

    resp_html = client.get(
        f"/accelerators/sessions/{session_id}/artifacts/{preview_filename}/preview",
        headers=headers,
    )
    assert resp_html.status_code == 200
    assert "<!doctype html>" in resp_html.text.lower()
