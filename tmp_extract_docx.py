from zipfile import ZipFile
from pathlib import Path
import xml.etree.ElementTree as ET


def docx_text(path: Path) -> str:
    with ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    texts = []
    for para in root.findall(".//w:p", ns):
        parts = []
        for run in para.findall(".//w:t", ns):
            if run.text:
                parts.append(run.text)
        if parts:
            texts.append("".join(parts))
    return "\n".join(texts)


base = Path(r"c:\\Users\\AdamThacker\\Projects\\OPNXT\\docs\\Claude")
files = [
    "ChatPRD - Feedback on new idea.docx",
    "OPNXT - Doc Generation on Demand.docx",
]

for name in files:
    print(f"--- {name} ---")
    try:
        text = docx_text(base / name)
    except Exception as exc:  # pragma: no cover
        print(f"Error reading {name}: {exc}")
    else:
        print(text)
        print()
        out_path = base / f"{Path(name).stem}.txt"
        out_path.write_text(text, encoding="utf-8")
        print(f"[saved to {out_path}]\n")
