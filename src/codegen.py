"""Code generation utilities for OPNXT.

Generates implementation scaffolds or code snippets from the Software
Design Description (SDD) using an LLM when available. Falls back to
well-structured placeholders to keep the developer workflow unblocked.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple
import json


def _llm_generate_json_mapping(llm, prompt: str) -> Optional[Dict[str, str]]:
    """Invoke an LLM to return a JSON mapping of file_path -> file_content.

    The prompt must instruct the model to return ONLY a JSON object. We then
    parse and return it. Returns None if LLM is unavailable or output invalid.
    """
    if not llm:
        return None
    try:
        res = llm.invoke(prompt)
        content = getattr(res, "content", None) or str(res)
        # Try to locate a JSON object in the response
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            obj = json.loads(content[start : end + 1])
            if isinstance(obj, dict):
                # Ensure all values are strings
                return {str(k): str(v) for k, v in obj.items()}
    except Exception:
        return None
    return None


def generate_code_from_sdd(sdd_markdown: str, project_root: Path, llm=None) -> Dict[str, str]:
    """Generate code files from an SDD markdown string.

    - If LLM is available, ask it to produce a JSON mapping of file paths to
      code contents. The files will be written under `generated_code/` by the
      caller for safety unless the mapping contains safe paths within the
      project directory.
    - If LLM is not available or fails, return a small set of scaffold files
      to get the developer started.

    Returns a mapping of relative file path -> file contents.
    """
    base_dir = Path("generated_code")

    system_prompt = (
        "You are an expert software agent assisting with code generation.\n"
        "Input is a Software Design Description (SDD) in Markdown.\n"
        "Task: Produce a JSON object ONLY, mapping relative file paths to their file contents.\n"
        "Constraints:\n"
        "- Use Python.\n"
        "- Prefer placing outputs under generated_code/ to avoid overwriting existing code.\n"
        "- Ensure code is immediately runnable and includes necessary imports.\n"
        "- Do not include explanations, markdown fences, or prose. Output raw JSON only.\n"
    )
    user_prompt = (
        f"SDD (Markdown):\n\n{sdd_markdown}\n\n"
        "Return JSON mapping of file paths (e.g., 'generated_code/module.py') to file contents."
    )

    mapping = _llm_generate_json_mapping(llm, system_prompt + "\n\n" + user_prompt)
    if mapping:
        # Normalize to safe relative paths
        safe_mapping: Dict[str, str] = {}
        for p, content in mapping.items():
            rel = Path(p)
            if rel.is_absolute():
                # force under generated_code/
                rel = base_dir / rel.name
            # prevent directory traversal
            rel = Path(*[part for part in rel.parts if part not in ("..",)])
            # ensure base_dir prefix
            if not str(rel).startswith(str(base_dir)):
                rel = base_dir / rel.name
            safe_mapping[str(rel)] = content
        return safe_mapping

    # Fallback scaffolds
    fallback: Dict[str, str] = {
        str(base_dir / "README.md"): (
            "# Generated Code Scaffold\n\n"
            "An LLM was not available. This scaffold was created to help you start.\n"
            "- Add your modules in this folder.\n"
            "- Integrate with your app as needed.\n\n"
            "## Quickstart\n"
            "This scaffold includes a minimal Streamlit web app you can run locally.\n\n"
            "### Prerequisites\n"
            "- Python 3.11+\n"
            "- Dependencies from the repository's `requirements.txt` (includes `streamlit`).\n\n"
            "### Run the app\n"
            "```bash\n"
            "streamlit run generated_code/webapp/streamlit_app.py\n"
            "```\n\n"
            "The app is a simple feature voting demo you can expand per your SDD.\n"
        ),
        str(base_dir / "app" / "__init__.py"): "# package init\n",
        str(base_dir / "app" / "service.py"): (
            "def hello(name: str) -> str:\n"
            "    \"\"\"Return a friendly greeting.\n\n"
            "    Replace with real implementation per the SDD.\n"
            "    \"\"\"\n"
            "    return f'Hello, {name}!'\n"
        ),
        str(base_dir / "app" / "cli.py"): (
            "import argparse\n"
            "from .service import hello\n\n"
            "def main():\n"
            "    parser = argparse.ArgumentParser(description='Generated app CLI')\n"
            "    parser.add_argument('--name', default='World')\n"
            "    args = parser.parse_args()\n"
            "    print(hello(args.name))\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        str(base_dir / "webapp" / "streamlit_app.py"): (
            "import streamlit as st\n"
            "from typing import Dict\n\n"
            "st.set_page_config(page_title='Generated Web App', page_icon='🧩', layout='centered')\n"
            "st.title('Feature Voting Demo')\n"
            "st.caption('Generated by OPNXT fallback scaffold — extend per your SDD')\n\n"
            "if 'features' not in st.session_state:\n"
            "    st.session_state.features: Dict[str, int] = {}\n\n"
            "with st.form('add_feature', clear_on_submit=True):\n"
            "    name = st.text_input('Propose a feature', placeholder='e.g., Dark mode')\n"
            "    submitted = st.form_submit_button('Add')\n"
            "    if submitted and name.strip():\n"
            "        st.session_state.features.setdefault(name.strip(), 0)\n"
            "        st.success(f'Added feature: {name.strip()}')\n\n"
            "st.subheader('Vote on features')\n"
            "if not st.session_state.features:\n"
            "    st.info('No features yet — add one above!')\n"
            "else:\n"
            "    for feat, votes in sorted(st.session_state.features.items(), key=lambda kv: kv[1], reverse=True):\n"
            "        cols = st.columns([6, 1, 1])\n"
            "        with cols[0]:\n"
            "            st.write(f'**{feat}** — {votes} votes')\n"
            "        with cols[1]:\n"
            "            if st.button('👍', key=f'up_{feat}'):\n"
            "                st.session_state.features[feat] += 1\n"
            "        with cols[2]:\n"
            "            if st.button('🗑️', key=f'del_{feat}'):\n"
            "                del st.session_state.features[feat]\n"
            "                st.experimental_rerun()\n\n"
            "st.divider()\n"
            "st.caption('Tip: Wire this to a backend per your SDD (e.g., FastAPI + database).')\n"
        ),
    }
    return fallback


def write_generated_files(mapping: Dict[str, str], project_root: Path) -> Tuple[int, int]:
    """Write generated files to disk relative to project_root.

    Returns (written_count, skipped_count). Skips files that already exist to
    avoid overwriting user code.
    """
    written = 0
    skipped = 0
    for rel, content in mapping.items():
        path = project_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            skipped += 1
            continue
        path.write_text(content, encoding="utf-8")
        written += 1
    return written, skipped
