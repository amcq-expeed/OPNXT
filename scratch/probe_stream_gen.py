import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator.infrastructure.doc_store import get_doc_store
from src.orchestrator.services.project_stream import (
    reset_project_stream,
    stream_project_documents,
)

async def main():
    project_id = "probe-gen"
    reset_project_stream(project_id)
    store = get_doc_store()
    store.save_document(project_id, "SRS.md", "Hello stream", meta={"seed": True})

    agen = stream_project_documents(project_id)
    event1 = await agen.__anext__()
    print("event1", event1)
    event2 = await agen.__anext__()
    print("event2", event2)

if __name__ == "__main__":
    asyncio.run(main())
