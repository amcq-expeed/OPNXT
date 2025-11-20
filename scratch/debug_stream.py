from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure.doc_store import get_doc_store
from src.orchestrator.services.project_stream import reset_project_stream
from tests.utils import admin_headers

def main() -> None:
    client = TestClient(app)
    headers = admin_headers(client)
    resp = client.post(
        "/projects",
        json={"name": "StreamDbg", "description": "Doc stream debug"},
        headers=headers,
    )
    print("create status", resp.status_code)
    data = resp.json()
    print("create data", data)
    project_id = data["project_id"]
    reset_project_stream(project_id)
    store = get_doc_store()
    store.save_document(project_id, "SRS.md", "# Initial\n", meta={"seed": True})

    with client.stream(
        "GET",
        f"/projects/{project_id}/documents/stream",
        headers=headers,
    ) as response:
        print("stream status", response.status_code)
        iterator = response.iter_text()
        for idx in range(5):
            try:
                chunk = next(iterator)
            except StopIteration:
                print("no more chunks")
                break
            print(f"chunk {idx}:", repr(chunk))

if __name__ == "__main__":
    main()
