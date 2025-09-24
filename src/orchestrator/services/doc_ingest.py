from __future__ import annotations

from typing import List, Tuple
import io
import os
import re

# Optional imports guarded
try:
    from docx import Document  # type: ignore
except Exception:  # pragma: no cover
    Document = None  # type: ignore

try:
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None  # type: ignore


def parse_text_from_bytes(filename: str, data: bytes) -> str:
    """Parse common document types into plain text.
    Supports .pdf (via pypdf), .md/.txt (utf-8), and .docx (optional python-docx).
    Falls back to utf-8 decode with replacement.
    """
    name = (filename or '').lower()
    if name.endswith('.pdf'):
        if PdfReader is None:
            return ''
        # with PdfReader available
        try:
            bio = io.BytesIO(data)
            reader = PdfReader(bio)
            texts: List[str] = []
            for page in reader.pages:
                try:
                    t = page.extract_text() or ''
                except Exception:
                    t = ''
                if t:
                    texts.append(t)
            return '\n'.join(texts)
        except Exception:
            pass
    if name.endswith('.docx'):
        if Document is None:
            return ''
        # with python-docx available
        try:
            bio = io.BytesIO(data)
            doc = Document(bio)
            paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
            return '\n'.join(paragraphs)
        except Exception:
            pass
    # Fallback for .md/.txt and generic decode
    try:
        return data.decode('utf-8', errors='replace')
    except Exception:
        return ''


def extract_shall_statements(text: str) -> List[str]:
    """Extract or normalize SHALL-style requirements from free-form text.
    - Splits by lines, then sentences; handles bullets and numbering
    - Converts intent verbs (should|must|will|enable|allow|support|provide|include) to canonical form
    - Deduplicates and enforces trailing punctuation
    """
    out: List[str] = []
    if not text:
        return out
    lines = text.splitlines()
    for ln in lines:
        cleaned = re.sub(r"^[-*•\u2022\u2023\u25E6\u2043–—\d\.\)\s]+", "", str(ln or '').strip())
        if not cleaned:
            continue
        # Split by sentence terminators or semicolons
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\s*;\s+", cleaned) if s and s.strip()]
        for s in sentences:
            if len(s) < 6:
                continue
            # Skip headings or metadata lines
            if re.match(r"^(note|summary|context)[:\s]", s, flags=re.IGNORECASE):
                continue
            t = s
            if not re.search(r"\bshall\b", t, flags=re.IGNORECASE):
                if re.search(r"\b(should|must|will|require|enable|allow|support|provide|include)\b", t, flags=re.IGNORECASE):
                    # Convert to canonical SHALL
                    if not re.search(r"[.!?]$", t):
                        t = t + "."
                    t = "The system SHALL " + t[0].upper() + t[1:]
                else:
                    # Fallback: treat short bullet-like phrases as requirements if they have >=2 words
                    words = re.split(r"\s+", t.strip())
                    if len([w for w in words if w]) >= 2:
                        # Capitalize first letter and ensure punctuation
                        if not re.search(r"[.!?]$", t):
                            t = t + "."
                        t = "The system SHALL " + t[0].upper() + t[1:]
                    else:
                        # Not clearly a requirement line; skip
                        continue
            else:
                # Ensure canonical casing and punctuation
                if not re.search(r"[.!?]$", t):
                    t = t + "."
                t = re.sub(r"^the\s+system\s+shall", "The system SHALL", t, flags=re.IGNORECASE)
            if t.startswith("The system SHALL "):
                out.append(t)
    # Deduplicate while preserving order
    seen = set()
    uniq: List[str] = []
    for r in out:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq
