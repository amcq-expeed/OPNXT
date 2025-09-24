import json

from src.orchestrator.services.doc_ingest import parse_text_from_bytes, extract_shall_statements


def test_parse_pdf_with_stub(monkeypatch):
    class StubPage:
        def __init__(self, text):
            self._t = text
        def extract_text(self):
            return self._t
    class StubReader:
        def __init__(self, bio):
            self.pages = [StubPage("hello"), StubPage("world")]

    import src.orchestrator.services.doc_ingest as di
    monkeypatch.setattr(di, "PdfReader", StubReader)

    out = parse_text_from_bytes("file.pdf", b"anything")
    assert "hello" in out and "world" in out


def test_parse_docx_with_stub(monkeypatch):
    class StubParagraph:
        def __init__(self, text):
            self.text = text
    class StubDoc:
        def __init__(self, bio):
            self.paragraphs = [StubParagraph("a"), StubParagraph(""), StubParagraph("b")]

    import src.orchestrator.services.doc_ingest as di
    monkeypatch.setattr(di, "Document", StubDoc)

    out = parse_text_from_bytes("file.docx", b"anything")
    assert out.strip() == "a\nb"


essential_text = "Note: skip\nshould allow export; will log errors\nThe system shall support SSO"


def test_extract_shall_various():
    reqs = extract_shall_statements(essential_text)
    assert any(x.startswith("The system SHALL") for x in reqs)
    # Bullet-like short phrase canonicalization
    reqs2 = extract_shall_statements("- reset password")
    assert any("Reset password." in x for x in reqs2)
