import streamlit as st
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
from src.core import summarize_project
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from src.sdlc_generator import generate_all_docs, markdown_to_pdf, write_json_bundle
from src import validate_docs as vdoc
from src.codegen import generate_code_from_sdd, write_generated_files
from test_automation import generate_pytests, write_tests
from deploy import scaffold_github_actions
from src.backlog import generate_backlog_from_srs, write_backlog_outputs
from src.phase_guides import (
    ensure_guides_exist,
    load_phase_guide,
    generate_phase_guides,
    DEFAULT_CHECKLISTS,
    REQUIRED_DOCS,
    generate_guides_index,
    get_phase_filename,
)
import io
import zipfile
import json
import re

# Feature flag: hide Interaction Mode & Audience controls from UI (keep functionality)
HIDE_MODE_AND_AUDIENCE = True

try:
    from src.discovery_agent import IntelligentDiscoveryAgent
    DISCOVERY_AVAILABLE = True
except ImportError:
    DISCOVERY_AVAILABLE = False



st.set_page_config(page_title="OPNXT SDLC Assistant", page_icon="💬", layout="centered")

# Global UI polish (enterprise look & feel)
st.markdown(
    """
    <style>
      :root { --brand:#0B5FFF; }
      html, body, [class^="css"] { font-size: 17px; }
      .block-container { padding-top: 1.25rem; padding-bottom: 2rem; max-width: 1100px; }
      h1 { font-weight: 700; letter-spacing: .2px; }
      hr.opnxt { border: none; border-top: 1px solid #E6E9EF; margin: .25rem 0 1.25rem; }
      /* Sidebar tweaks */
      section[data-testid="stSidebar"] .block-container { padding-top: .75rem; }
      /* Buttons */
      div.stButton > button[kind="primary"] { background: var(--brand); border-color: var(--brand); color: #fff; }
      div.stButton > button[kind="primary"]:hover { filter: brightness(0.95); }
      div.stButton > button { width: 100%; }
      div.stButton > button:focus-visible { outline: 3px solid #1a73e8; outline-offset: 2px; }
      /* Cards */
      .opnxt-card { background: #fff; border: 1px solid #E6E9EF; border-radius: 10px; padding: 1rem 1.25rem; box-shadow: 0 2px 8px rgba(16,24,40,.04); }
      .opnxt-muted { color: #475467; font-size: .98rem; }
      /* Inputs */
      textarea { line-height: 1.5; }
      textarea::placeholder { color: #475467; opacity: 1; }
      textarea:focus-visible { outline: 3px solid #1a73e8 !important; outline-offset: 2px; }
      /* Labels */
      label { color:#101828 !important; font-weight:600 !important; }
      /* Skip link */
      .skip-link { position:absolute; left:-10000px; top:auto; width:1px; height:1px; overflow:hidden; }
      .skip-link:focus { position:static; width:auto; height:auto; padding:.5rem .75rem; background:#0B5FFF; color:#fff; border-radius:6px; }
      /* Reduce motion preference */
      @media (prefers-reduced-motion: reduce) {
        * { scroll-behavior: auto !important; animation: none !important; transition: none !important; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Config & LLM ----------
load_dotenv()

def get_llm():
    """Return a ChatOpenAI instance configured for xAI Grok via OpenAI-compatible API.

    Environment variables supported:
    - XAI_API_KEY or OPENAI_API_KEY
    - OPENAI_BASE_URL (defaults to xAI endpoint https://api.x.ai/v1)
    - XAI_MODEL (defaults to grok-2-latest)
    """
    api_key = os.getenv("XAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.x.ai/v1")
    model = os.getenv("XAI_MODEL", "grok-2-latest")
    if not api_key:
        return None
    try:
        return ChatOpenAI(api_key=api_key, base_url=base_url, model=model, temperature=0.2)
    except Exception:
        return None

LLM = get_llm()

# ---------- SDLC Flow ----------
SDLC_PHASES: List[str] = [
    "Planning",
    "Requirements",
    "Design",
    "Implementation",
    "Testing",
    "Deployment",
    "Maintenance",
]

SDLC_QUESTIONS: Dict[str, List[str]] = {
    "Planning": [
        "What is the main goal of the project?",
        "Who are the key stakeholders and target users?",
        "What is the desired timeline or launch window?",
    ],
    "Requirements": [
        "List the top 3-5 core features (functional requirements).",
        "Any non-functional requirements (performance, security, compliance)?",
        "What are the success metrics or KPIs?",
    ],
    "Design": [
        "Any constraints or preferences for architecture/tech stack?",
        "What integrations or external systems are needed?",
        "Any data model or API considerations?",
    ],
    "Implementation": [
        "Preferred development approach (agile/kanban) and team roles?",
        "How should we prioritize the MVP scope?",
    ],
    "Testing": [
        "What is the testing strategy (unit, integration, e2e)?",
        "Any QA environments or test data considerations?",
    ],
    "Deployment": [
        "Release strategy (staged/blue-green/canary)?",
        "Target environments (cloud/provider/regions)?",
    ],
    "Maintenance": [
        "Monitoring/observability needs?",
        "Support/SLAs and incident response expectations?",
    ],
}

# Additional human-friendly helper text to guide answers in Chat Mode
SDLC_QUESTION_HELP: Dict[str, List[str]] = {
    "Planning": [
        "Briefly describe the business outcome you want. Example: 'Enable users to upload and share photos with smart tagging.'",
        "Who cares about this project and who will use it day-to-day? Example roles: Product Owner, Customer Success, End Users.",
        "Share any deadlines or milestones (e.g., beta in 6 weeks, GA next quarter). Note major dependencies or constraints.",
    ],
    "Requirements": [
        "List capabilities as clear statements. Example: 'The system SHALL allow users to reset passwords via email.'",
        "Call out NFRs like performance, security, accessibility. Example: 'P95 latency < 300ms', 'Encrypt data at rest'.",
        "What will tell us we succeeded? Example: 'DAU +20%', 'Support < 2h response for P1 incidents'.",
    ],
    "Design": [
        "Any preferred patterns, services, or tech. Example: 'Microservices on FastAPI with a Postgres DB.'",
        "What systems do we integrate with and how? Example: 'Stripe for billing via REST webhooks'.",
        "Describe key entities and relationships. Example: 'User, Project, Task with many-to-one links'.",
    ],
    "Implementation": [
        "How will the team work? Example: 'Two-week sprints, code reviews required, trunk-based'.",
        "What’s the smallest valuable slice (MVP) and how do we sequence it?",
    ],
    "Testing": [
        "Which test levels and coverage targets? Example: '80% unit coverage, e2e for critical flows'.",
        "Any special environment or data needs? Example: 'Mask PII in seed data; ephemeral preview envs'.",
    ],
    "Deployment": [
        "How do we roll out safely? Example: 'Blue/green with canary for 10% traffic first'.",
        "Where will it run? Example: 'AWS us-east-1, Terraform modules, multi-AZ'.",
    ],
    "Maintenance": [
        "What signals do we watch? Example: 'SLO 99.9% uptime; alerts on error rate spikes'.",
        "How do we support users and respond to incidents? Include SLAs and on-call info.",
    ],
}

# Plain-language one-liners per phase for beginner audience
SDLC_PLAIN_LANGUAGE: Dict[str, str] = {
    "Planning": (
        "Define what you want to build, who it's for, when you need it, and what success looks like."
    ),
    "Requirements": (
        "List what the product must do (features) and how well it should do it (performance, security, etc.)."
    ),
    "Design": (
        "Sketch how the system will work: key parts, how they talk, data shapes, and important trade-offs."
    ),
    "Implementation": (
        "Decide how you'll build it: coding standards, MVP scope, and how the team will work together."
    ),
    "Testing": (
        "Plan how you'll test: levels, coverage, environments, and linking tests back to requirements."
    ),
    "Deployment": (
        "Figure out how to ship safely: environments, rollout plan, and rollback steps."
    ),
    "Maintenance": (
        "Plan how you'll keep it healthy: monitoring, on-call/support, and change management."
    ),
}

# Best-practice prompts aligned to IEEE/ISO standards for guidance in both modes
BEST_PRACTICES: Dict[str, str] = {
    "Planning": (
        "Follow ISO/IEC/IEEE 12207 planning principles. Clarify goals, constraints, "
        "stakeholders, and milestones. Capture risks, assumptions, and success criteria."
    ),
    "Requirements": (
        "Use ISO/IEC/IEEE 29148 and IEEE 830-style clarity: uniquely identified, "
        "verifiable, unambiguous, and prioritized requirements. Include NFRs aligned to "
        "ISO/IEC 25010 quality attributes (security, performance, usability, reliability)."
    ),
    "Design": (
        "Apply IEEE 1016 guidance. Describe architecture views, interfaces, data models, "
        "and design rationale. Note patterns, constraints, and key trade-offs."
    ),
    "Implementation": (
        "Map design to modules with clear responsibilities, coding standards, and "
        "definition of done. Reference secure coding practices (e.g., OWASP, ISO 27001 controls)."
    ),
    "Testing": (
        "Define test levels and coverage aligned to ISO/IEC/IEEE 29119 concepts. Include "
        "traceability from requirements, environments, test data, and acceptance criteria."
    ),
    "Deployment": (
        "Plan environments, release strategies, and rollback. Include change control and "
        "operational readiness checks (monitoring, logging, security baselines)."
    ),
    "Maintenance": (
        "Specify monitoring/observability SLOs, incident response, and update cadence. Maintain "
        "a change log and configuration management consistent with ISO/IEC/IEEE 12207."
    ),
}

# Minimal SDLC glossary for sidebar reference
SDLC_GLOSSARY: Dict[str, str] = {
    "SRS": "Software Requirements Specification — a document describing functional and non-functional requirements.",
    "SDD": "Software Design Description — a document detailing architecture, components, interfaces, and data.",
    "Test Plan": "A plan that outlines the test strategy, scope, approach, resources, and schedule of testing activities.",
    "Traceability": "The relationship linking requirements to design, implementation, and tests to ensure coverage.",
    "NFR": "Non-Functional Requirement — quality attributes like performance, security, usability, and reliability.",
    "CI": "Continuous Integration — automated building and testing of code changes.",
    "Canary": "A deployment strategy that releases to a small subset of users before full rollout.",
}

def next_phase(current: str) -> str:
    idx = SDLC_PHASES.index(current)
    return SDLC_PHASES[idx + 1] if idx + 1 < len(SDLC_PHASES) else ""

def summarize_phase(phase: str, answers: List[str]) -> str:
    """Use LLM to summarize a phase if available, else fallback."""
    if not answers:
        return f"No inputs captured for {phase}."
    joined = "\n".join(f"- {a}" for a in answers)
    if LLM:
        try:
            prompt = (
                "You are an SDLC assistant. Summarize the following inputs for the phase '"
                f"{phase}'. Provide a crisp, actionable summary with bullets.\n\nInputs:\n{joined}"
            )
            res = LLM.invoke(prompt)
            return res.content if hasattr(res, "content") else str(res)
        except Exception:
            pass
    # Fallback
    return f"{phase} summary based on inputs:\n{joined}"

# ---------- Guides Integration (Markdown) ----------
def _locate_first(paths: List[Path]) -> Optional[Path]:
    """Return the first existing path from a list, else None."""
    for p in paths:
        if p.exists():
            return p
    return None

def load_guides() -> Dict[str, Tuple[Optional[Path], str]]:
    """Load optional guide Markdown files if present.

    Returns a mapping of key -> (path, content):
    - 'creation' => CREATION_GUIDE.md
    - 'validation' => VALIDATION_CHECKLIST.md
    - 'change' => CHANGE_TRACKER.md
    """
    search_roots = [Path("."), Path("docs"), Path("templates"), Path("generated_code"), Path("./OPNXT"), Path("./opnxt")]
    filenames = {
        "creation": "CREATION_GUIDE.md",
        "validation": "VALIDATION_CHECKLIST.md",
        "change": "CHANGE_TRACKER.md",
    }
    guides: Dict[str, Tuple[Optional[Path], str]] = {}
    for key, fname in filenames.items():
        candidates = [root / fname for root in search_roots]
        found = _locate_first(candidates)
        if found and found.exists():
            try:
                guides[key] = (found, found.read_text(encoding="utf-8"))
            except Exception:
                guides[key] = (found, "")
        else:
            guides[key] = (None, "")
    return guides

def render_focus_content(topic: str, content: str):
    """Render guide content inside the chat as markdown, with a heading."""
    title_map = {
        "creation": "Creation Guide",
        "validation": "Validation Checklist",
        "change": "Change Tracker",
    }
    header = title_map.get(topic, topic.title())
    with st.chat_message("assistant"):
        st.markdown(f"### {header}")
        if content.strip():
            st.markdown(content)
        else:
            st.info("No content found for this guide. Add the Markdown file to the project to enable it.")

# ---------- Session State ----------
if "discovery_agent" not in st.session_state and DISCOVERY_AVAILABLE:
    st.session_state.discovery_agent = IntelligentDiscoveryAgent()
if "discovery_mode" not in st.session_state:
    st.session_state.discovery_mode = False
if "discovery_complete" not in st.session_state:
    st.session_state.discovery_complete = False
if "messages" not in st.session_state:
    st.session_state.messages = []
if "phase" not in st.session_state:
    st.session_state.phase = "Planning"
if "q_index" not in st.session_state:
    st.session_state.q_index = 0
if "answers" not in st.session_state:
    st.session_state.answers = {p: [] for p in SDLC_PHASES}
if "summaries" not in st.session_state:
    st.session_state.summaries = {p: "" for p in SDLC_PHASES}
if "generated_docs" not in st.session_state:
    st.session_state.generated_docs = {}
if "awaiting_confirmation" not in st.session_state:
    st.session_state.awaiting_confirmation = False
if "pending_phase" not in st.session_state:
    st.session_state.pending_phase = ""
if "auto_validate" not in st.session_state:
    st.session_state.auto_validate = True
if "awaiting_codegen" not in st.session_state:
    st.session_state.awaiting_codegen = False
if "awaiting_testgen" not in st.session_state:
    st.session_state.awaiting_testgen = False
if "awaiting_ci_setup" not in st.session_state:
    st.session_state.awaiting_ci_setup = False
if "guides" not in st.session_state:
    st.session_state.guides = load_guides()
if "ui_mode" not in st.session_state:
    st.session_state.ui_mode = "Chat Mode"  # or "Form Mode"
if "audience" not in st.session_state:
    st.session_state.audience = "Beginner"  # Beginner | Intermediate | Expert
if "show_guidance" not in st.session_state:
    st.session_state.show_guidance = True
if "user_generated_docs" not in st.session_state:
    st.session_state.user_generated_docs = False
if "phase_progress" not in st.session_state:
    # phase_progress: Dict[phase_key, Dict[item_text, bool]]
    st.session_state.phase_progress = {p: {item: False for item in DEFAULT_CHECKLISTS.get(p, [])} for p in SDLC_PHASES}
    # Ensure guide files exist initially
    try:
        ensure_guides_exist(Path("docs"))
        # Initialize check statuses from existing guide files if present
        def _parse_checks(md: str) -> dict:
            checks = {}
            for line in md.splitlines():
                ls = line.lstrip()
                if ls.startswith("- [x] ") or ls.startswith("- [ ] "):
                    checked = ls.startswith("- [x] ")
                    text = ls[6:]
                    checks[text] = checked
            return checks
        for p in SDLC_PHASES:
            path, content = load_phase_guide(p, Path("docs"))
            if content:
                parsed = _parse_checks(content)
                # Only adopt known items
                for item in DEFAULT_CHECKLISTS.get(p, []):
                    if item in parsed:
                        st.session_state.phase_progress[p][item] = parsed[item]
        # Sync guides with parsed progress
        generate_phase_guides(progress=st.session_state.phase_progress, out_dir=Path("docs"))
    except Exception:
        pass

# Automatic validation sweep on app load/rerun: keeps MD checkboxes in sync
def _collect_rendered_docs_from_disk(docs_dir: Path) -> Dict[str, str]:
    files = ["ProjectCharter.md", "SRS.md", "SDD.md", "TestPlan.md"]
    out: Dict[str, str] = {}
    for f in files:
        p = docs_dir / f
        if p.exists():
            try:
                out[f] = p.read_text(encoding="utf-8")
            except Exception:
                pass
    return out

try:
    _docs_dir = Path("docs")
    # Prefer in-memory generated docs; fall back to reading from disk
    _rendered_docs = st.session_state.get("generated_docs", {}) or _collect_rendered_docs_from_disk(_docs_dir)
    if _rendered_docs:
        # Run a silent validation for all phases to auto-tick doc-tied items
        for _phase in SDLC_PHASES:
            try:
                vdoc.validate_phase(_phase, _docs_dir, _rendered_docs)
                # Sync session state from the freshly written guide
                _f = _docs_dir / get_phase_filename(_phase)
                if _f.exists():
                    try:
                        _content = _f.read_text(encoding="utf-8")
                        _parsed = {}
                        for _line in _content.splitlines():
                            _ls = _line.lstrip()
                            if _ls.startswith("- [x] ") or _ls.startswith("- [ ] "):
                                _checked = _ls.startswith("- [x] ")
                                _text = _ls[6:]
                                _parsed[_text] = _checked
                        for _item in DEFAULT_CHECKLISTS.get(_phase, []):
                            st.session_state.phase_progress.setdefault(_phase, {})
                            if _item in _parsed:
                                st.session_state.phase_progress[_phase][_item] = _parsed[_item]
                    except Exception:
                        pass
            except Exception:
                pass
        # Regenerate guides index quietly
        try:
            generate_guides_index(_docs_dir)
        except Exception:
            pass
except Exception:
    pass

def render_phase_guide_panel(phase: str):
    with st.expander(f"{phase} — Phase Guide", expanded=False):
        # Show current guide markdown
        path, content = load_phase_guide(phase, Path("docs"))
        if content:
            st.markdown(content)
        else:
            st.info("Phase guide not found yet. It will be generated automatically.")
        st.divider()
        st.caption("Checklist — update as you progress:")
        changed = False
        for item in DEFAULT_CHECKLISTS.get(phase, []):
            cur = st.session_state.phase_progress.get(phase, {}).get(item, False)
            new_val = st.checkbox(item, value=cur, key=f"chk_{phase}_{item}")
            if new_val != cur:
                st.session_state.phase_progress[phase][item] = new_val
                changed = True
        if changed:
            # Persist changes to docs/*_guide.md
            try:
                generate_phase_guides(progress=st.session_state.phase_progress, out_dir=Path("docs"))
                try:
                    generate_guides_index(Path("docs"))
                except Exception:
                    pass
                st.success("Guide checklist updated.")
            except Exception:
                st.warning("Failed to update guide file; changes kept in session.")

def _sync_doc_tied_checks(docs_dir: Path):
    """Set checklist items that reference produced docs to checked if present."""
    for phase, required in REQUIRED_DOCS.items():
        for req in required:
            if (docs_dir / req).exists():
                # Find matching checklist item text and flip to True
                for item in DEFAULT_CHECKLISTS.get(phase, []):
                    if req in item:
                        st.session_state.phase_progress.setdefault(phase, {})
                        st.session_state.phase_progress[phase][item] = True
    try:
        generate_phase_guides(progress=st.session_state.phase_progress, out_dir=docs_dir)
        try:
            generate_guides_index(docs_dir)
        except Exception:
            pass
    except Exception:
        pass

st.markdown('<a href="#main" class="skip-link">Skip to main content</a>', unsafe_allow_html=True)
st.title("OPNXT PMO and SDLC Automation Assistant")
# Removed under-title caption while mode controls are hidden to reduce confusion and improve clarity
st.markdown("<hr class='opnxt'>", unsafe_allow_html=True)

# Sidebar: Phase Guides quick access
with st.sidebar:
    st.header("Guides")
    idx_path = Path("docs") / "guides_index.md"
    if idx_path.exists():
        if st.button("Open Guides Index", key="btn_guides_index"):
            st.session_state.view_doc = idx_path.name
            st.rerun()
    else:
        st.caption("Guides index will appear after guides are generated.")
    # Link to current phase guide
    try:
        cur_fname = get_phase_filename(st.session_state.get("phase", "Planning"))
        cur_path = Path("docs") / cur_fname
        if st.button("Current Phase Guide", key="btn_current_phase_guide"):
            st.session_state.view_doc = cur_path.name
            st.rerun()
    except Exception:
        pass

    st.markdown("---")
    st.subheader("Documents")
    # Optional quick reset for visibility state
    try:
        if st.session_state.ui_mode == "Simple Request Mode":
            if st.button("New Request", key="reset_ui_btn"):
                st.session_state.user_generated_docs = False
                if "simple_req" in st.session_state:
                    st.session_state.simple_req["docs_generated"] = False
                    st.session_state.simple_req["questions"] = []
                    st.session_state.simple_req["question_answers"] = {}
                    st.session_state.simple_req["description"] = ""
                st.rerun()
    except Exception:
        pass
    # Track selected document for preview
    if "view_doc" not in st.session_state:
        st.session_state.view_doc = None
    docs_dir = Path("docs")
    # Only show docs after user initiated generation in THIS session
    _docs_ready = bool(st.session_state.get("user_generated_docs", False))

    # If in Simple Request Mode and no docs_generated, force-hide
    try:
        if st.session_state.ui_mode == "Simple Request Mode" and not st.session_state.get("simple_req", {}).get("docs_generated", False):
            _docs_ready = False
            st.session_state.user_generated_docs = False
    except Exception:
        pass

    if _docs_ready:
        doc_files = [
            ("ProjectCharter.md", "Project Charter"),
            ("SRS.md", "SRS"),
            ("SDD.md", "SDD"),
            ("TestPlan.md", "Test Plan"),
            ("Backlog.md", "Backlog"),
            ("Backlog.csv", "Backlog (CSV)"),
            ("Backlog.json", "Backlog (JSON)"),
        ]
        for fname, label in doc_files:
            p = docs_dir / fname
            if not p.exists():
                continue
            cols = st.columns([3, 2])
            with cols[0]:
                if st.button(label, key=f"view_{fname}"):
                    st.session_state.view_doc = fname
                    st.rerun()
            with cols[1]:
                try:
                    data = p.read_bytes()
                    mime = (
                        "text/markdown" if fname.endswith(".md") else
                        "text/csv" if fname.endswith(".csv") else
                        "application/json" if fname.endswith(".json") else
                        "application/octet-stream"
                    )
                    st.download_button("Download", data=data, file_name=fname, mime=mime, key=f"dl_{fname}")
                except Exception:
                    pass
    else:
        st.caption("No documents yet. Generate them from Simple Request or other modes.")

# Global mode selector (hidden by flag)
if not HIDE_MODE_AND_AUDIENCE:
    st.markdown("<hr class='opnxt'>", unsafe_allow_html=True)
if not HIDE_MODE_AND_AUDIENCE:
    if DISCOVERY_AVAILABLE:
        mode_options = ["Simple Request Mode", "AI Discovery Mode", "Classic Chat Mode", "Form Mode"]
        help_text = (
            "Simple: Plain-English request with background generation | "
            "AI Discovery: Intelligent conversation | Classic Chat: Original OPNXT flow | Form: Direct input"
        )
    else:
        mode_options = ["Simple Request Mode", "Chat Mode", "Form Mode"]
        help_text = (
            "Simple: Plain-English request with background generation | "
            "Chat Mode: OPNXT structured flow | Form Mode: Direct input"
        )
    selected_mode = st.radio(
        "Interaction Mode",
        options=mode_options,
        horizontal=True,
        help=help_text
    )
else:
    # Default silently to Simple Request Mode when hidden
    selected_mode = "Simple Request Mode"

# Map selection to internal state
if selected_mode == "AI Discovery Mode" and DISCOVERY_AVAILABLE:
    st.session_state.ui_mode = "Chat Mode"
    st.session_state.discovery_mode = True
elif selected_mode == "Classic Chat Mode":
    st.session_state.ui_mode = "Chat Mode" 
    st.session_state.discovery_mode = False
elif selected_mode == "Simple Request Mode":
    st.session_state.ui_mode = "Simple Request Mode"
    st.session_state.discovery_mode = False
    # Reset doc visibility for a fresh simple request flow
    try:
        sr = st.session_state.get("simple_req", {})
        # If no description yet or no generation has occurred, reset flags and state
        if not sr or not sr.get("description") or not sr.get("docs_generated", False):
            st.session_state.user_generated_docs = False
            # Initialize/refresh simple_req container
            st.session_state.simple_req = {
                "description": sr.get("description", "") if sr else "",
                "answers": {"Planning": [], "Requirements": [], "Design": []},
                "q_index": 0,
                "docs_generated": False,
                "questions": [],
                "question_answers": {},
            }
    except Exception:
        st.session_state.user_generated_docs = False
else:
    st.session_state.ui_mode = "Form Mode"
    st.session_state.discovery_mode = False
st.markdown("---")

# Audience selector
if not HIDE_MODE_AND_AUDIENCE:
    aud_col1, aud_col2 = st.columns([1, 3])
    with aud_col1:
        st.write("Audience:")
    with aud_col2:
        st.session_state.audience = st.selectbox(
            "Choose your familiarity level",
            options=["Beginner", "Intermediate", "Expert"],
            index=["Beginner", "Intermediate", "Expert"].index(st.session_state.audience),
            label_visibility="collapsed",
        )
    st.caption("We adapt explanations and prompts based on your selection.")
else:
    # Keep default internally without rendering controls
    st.session_state.audience = st.session_state.get("audience", "Beginner")
if not HIDE_MODE_AND_AUDIENCE:
    st.markdown("<hr class='opnxt'>", unsafe_allow_html=True)

# ---------- Simple Request Mode ----------
st.markdown('<main id="main" role="main">', unsafe_allow_html=True)
if st.session_state.ui_mode == "Simple Request Mode":
    st.header("Simple Request")
    st.markdown("<div aria-hidden='true' style='display:inline-block;background:#ECF2FF;color:#0B5FFF;border:1px solid #C9D8FF;border-radius:999px;padding:.2rem .6rem;font-weight:600;margin:.25rem 0 .75rem;'>Start here</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='opnxt-muted'>Describe what you'd like to build in plain English. I'll generate the necessary SDLC documents and a backlog in the background, and only ask optional follow-ups if needed.</div>",
        unsafe_allow_html=True,
    )

    if "simple_req" not in st.session_state:
        st.session_state.simple_req = {
            "description": "",
            "answers": {"Planning": [], "Requirements": [], "Design": []},
            "q_index": 0,
            "docs_generated": False,
        }

    with st.container():
        st.markdown("<div class='opnxt-card'>", unsafe_allow_html=True)
        desc = st.text_area(
            "What would you like to create?",
            value=st.session_state.simple_req.get("description", ""),
            placeholder="E.g., Build an Apptor-based CRUD event platform with search, email automation, and reporting.",
            height=220,
        )
        st.markdown("</div>", unsafe_allow_html=True)
    st.session_state.simple_req["description"] = desc

    # If the description has changed since last time, reset follow-ups to avoid stale carry-over
    if st.session_state.simple_req.get("last_desc") != desc:
        st.session_state.simple_req["last_desc"] = desc
        st.session_state.simple_req["questions"] = []
        st.session_state.simple_req["question_answers"] = {}

    # We do not render clarifying questions upfront. They will be suggested after generation if needed.
    has_desc = bool(desc.strip())
    if not has_desc:
        st.caption("Enter a request above, then click Generate. I'll suggest any follow-up questions only if needed.")
        # Enforce hidden documents until a new generation happens
        st.session_state.user_generated_docs = False

    colA, colB = st.columns(2)
    with colA:
        gen_clicked = st.button("Generate Plan & Docs", type="primary", disabled=not has_desc, use_container_width=True)
    with colB:
        update_clicked = st.button("Update Docs with Answers", disabled=not has_desc, use_container_width=True)

    def _compose_data():
        # Build minimal data structure for templates
        proj = summarize_project(desc)
        # Seed phase answers
        answers = {p: [] for p in SDLC_PHASES}
        if desc:
            answers["Planning"].append(f"Goal: {proj.get('summary', desc)}")
        # Include any follow-up answers captured post-generation
        for q, a in st.session_state.simple_req.get("question_answers", {}).items():
            if a:
                answers["Planning"].append(f"{q} {a}")
        # Map top features to Requirements
        derived_features: list[str] = []
        # Derive features from description when possible
        lower_desc = (desc or "").lower()
        if "birthday" in lower_desc:
            derived_features.extend([
                "Generate a personalized 'Happy Birthday' message",
                "Generate a celebratory image matching the birthday theme",
                "Render a simple web page with the message and image",
                "Allow downloading or copying the greeting",
            ])
        if "image" in lower_desc:
            if "generate" in lower_desc or "ai" in lower_desc:
                if "image" not in derived_features:
                    derived_features.append("Generate an AI image based on prompts")
        if "html" in lower_desc:
            derived_features.append("Serve a static HTML/CSS/JS page")
        # Person name extraction (very simple)
        name_match = re.search(r"for\s+([A-Z][a-z]+\s+[A-Z][a-z]+)", desc or "")
        recipient = name_match.group(1) if name_match else "the recipient"
        # Combine manual feature bullets and derived features
        qa_vals = list(st.session_state.simple_req.get("question_answers", {}).values())
        manual_features: list[str] = []
        for val in qa_vals:
            if not val:
                continue
            manual_features.extend([x.strip(" -•\t") for x in re.split(r",|;|\n", val) if x.strip()])
        all_features = manual_features + [f for f in derived_features if f not in manual_features]
        if all_features:
            for f in all_features:
                answers["Requirements"].append(f"The system SHALL support: {f}.")
        # Add explicit SHALL requirements only for birthday-greeting use cases
        if "birthday" in lower_desc:
            answers["Requirements"].append(
                f"The system SHALL generate a personalized greeting addressed to {recipient}."
            )
            answers["Requirements"].append(
                f"The system SHALL generate an accompanying celebratory image relevant to {recipient}'s birthday."
            )
            answers["Requirements"].append(
                "The system SHALL combine the message and image into a single shareable page."
            )
        # Heuristic parser for structured multi-line inputs (e.g., Ohio Tech Day)
        sections: dict[str, list[str]] = {}
        current = None
        for raw in (desc or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            # New section if ends with ':' or looks like a title line
            if line.endswith(":") or re.match(r"^[A-Z][\w &/()'-]+$", line):
                current = line.rstrip(":").strip()
                sections.setdefault(current, [])
                continue
            # Bullet or content under a section
            if current:
                item = line.lstrip("-•\t ")
                sections[current].append(item)

        def _add_req(prefix: str, items: list[str], template: str):
            for it in items:
                t = it.strip()
                if not t:
                    continue
                answers["Requirements"].append(template.format(item=t))

        # Map known sections to requirements
        if sections:
            if "Event Types to Support" in sections:
                _add_req("Event Types", sections["Event Types to Support"], "The system SHALL support event type: {item}.")
            if "Event Data Fields" in sections:
                _add_req("Event Data Fields", sections["Event Data Fields"], "The system SHALL store event data field: {item}.")
            if "Host Profiles Include" in sections:
                _add_req("Host Profiles", sections["Host Profiles Include"], "The system SHALL maintain host profile field: {item}.")
            if "Request Types" in sections:
                _add_req("Request Types", sections["Request Types"], "The system SHALL support request type: {item}.")
            if "Search & Discovery" in sections:
                _add_req("Search & Discovery", sections["Search & Discovery"], "The system SHALL provide discovery capability: {item}.")
            if "Sponsorship Management" in sections:
                _add_req("Sponsorship Management", sections["Sponsorship Management"], "The system SHALL support sponsorship capability: {item}.")
            if "Email Templates & Notifications" in sections:
                _add_req("Email Templates & Notifications", sections["Email Templates & Notifications"], "The system SHALL provide email/notification capability: {item}.")
            if "Notification System" in sections:
                _add_req("Notification System", sections["Notification System"], "The system SHALL trigger automated notification: {item}.")
            if "Dashboard & Reporting" in sections:
                _add_req("Dashboard & Reporting", sections["Dashboard & Reporting"], "The system SHALL provide reporting capability: {item}.")
            if "User Types & Roles" in sections:
                # Add to planning stakeholders
                for it in sections["User Types & Roles"]:
                    answers["Planning"].append(f"Stakeholder: {it}")
            if "Primary Users" in sections:
                for it in sections["Primary Users"]:
                    answers["Planning"].append(f"Primary Users: {it}")
            # Technical Considerations to Design
            if "Technical Considerations" in sections:
                for it in sections["Technical Considerations"]:
                    answers["Design"].append(f"Technical consideration: {it}")
            # Success metrics
            if "Success Metrics" in sections:
                for it in sections["Success Metrics"]:
                    answers["Requirements"].append(f"Success Metric: {it}")
            # Conference Management
            if "Annual Conference Data" in sections:
                _add_req("Conference", sections["Annual Conference Data"], "The system SHALL maintain conference data: {item}.")

        # If platform specified (e.g., Apptor), set design baseline
        if "apptor" in lower_desc:
            answers["Design"].append("Platform: Apptor low-code. Model-driven CRUD for entities.")
            answers["Design"].append("Entities: Event, Host, Request, Sponsor, Conference, User.")
            answers["Design"].append("Integrations: Email service, social media aggregation, storage for media artifacts.")
            answers["Design"].append("Search: Location + filters by type/date, directory lookup.")

        # Tech constraints to Design
        tech = (
            st.session_state.simple_req["answers"]["Planning"][2]
            if len(st.session_state.simple_req["answers"]["Planning"]) > 2 else ""
        )
        if tech:
            answers["Design"].append(f"Preferred tech/constraints: {tech}")
        # Insert baseline design (conditional)
        if "apptor" in lower_desc:
            # Prefer Apptor platform guidance
            pass  # already appended in platform-specific block below
        else:
            if not tech:
                answers["Design"].append(
                    "Architecture: Static HTML/CSS/JS frontend. Optional lightweight server or edge function."
                )
            # Only add AI-specific integrations if the request implies AI generation
            if ("ai" in lower_desc) or ("image" in lower_desc and "generate" in lower_desc):
                answers["Design"].append(
                    "Integrations: AI text/image generation via provider API; configure API key via environment variable."
                )
                answers["Design"].append(
                    f"Personalization: Accept a recipient name (e.g., '{recipient}') and theme keywords to seed prompts."
                )
        # Security to Requirements (NFR)
        sec = (
            st.session_state.simple_req["answers"]["Planning"][3]
            if len(st.session_state.simple_req["answers"]["Planning"]) > 3 else ""
        )
        if sec:
            answers["Requirements"].append(f"NFR - Security/Compliance: {sec}")
        # Baseline NFRs for this use case
        answers["Requirements"].append("NFR - Performance: First render within 2.5s on a typical broadband connection.")
        answers["Requirements"].append("NFR - Accessibility: Page meets WCAG 2.1 AA for color contrast and alt text on images.")
        answers["Requirements"].append("NFR - Privacy: Do not persist PII beyond recipient name in the client; no server storage by default.")
        summaries = {p: summarize_phase(p, answers[p]) for p in SDLC_PHASES}
        data = {
            "project": {"title": proj.get("title", "Untitled Project")},
            "answers": answers,
            "summaries": summaries,
            "phases": SDLC_PHASES,
            "request": desc,
        }
        return data

    if gen_clicked or update_clicked:
        if not desc.strip():
            st.warning("Please describe what you'd like to create before generating.")
        else:
            data = _compose_data()
            out_dir = Path("docs")
            st.session_state.generated_docs = generate_all_docs(
                data, templates_root=Path("templates")/"sdlc", out_dir=out_dir
            )
            bundle_path = out_dir / "sdlc_bundle.json"
            write_json_bundle(data, st.session_state.generated_docs, bundle_path)
            _sync_doc_tied_checks(out_dir)

            # Generate backlog from SRS
            srs_path = out_dir / "SRS.md"
            backlog = generate_backlog_from_srs(srs_path)
            write_backlog_outputs(backlog, out_dir)

            st.session_state.simple_req["docs_generated"] = True
            st.success("Documents and backlog generated! Use the left sidebar under 'Documents' to view or download.")
            st.session_state.user_generated_docs = True
            st.rerun()

            # Suggest clarifying questions only if the request seems underspecified
            def _suggest_questions(text: str) -> list[str]:
                qs: list[str] = []
                lt = text.lower()
                if not re.search(r"\b(user|role|audience|recipient)\b", lt):
                    qs.append("Who are the primary users or audience?")
                if not re.search(r"\bfeature|shall|must|can\b", lt):
                    qs.append("List the top 2–3 features you definitely need.")
                if not re.search(r"\bhtml|react|vue|api|integration|stack\b", lt):
                    qs.append("Any preferences for tech stack or integrations?")
                if not re.search(r"\bsecurity|privacy|hipaa|soc2|compliance\b", lt):
                    qs.append("Any security/compliance requirements (e.g., SOC2, HIPAA)?")
                return qs

            suggested = _suggest_questions(desc)
            st.session_state.simple_req.setdefault("questions", suggested)
            st.session_state.simple_req.setdefault("question_answers", {})

    # If we have suggested questions, render a lightweight follow-up panel to capture answers and regenerate
    if st.session_state.simple_req.get("docs_generated") and st.session_state.simple_req.get("questions"):
        with st.expander("Suggested follow-up questions (optional)", expanded=False):
            qa = st.session_state.simple_req.setdefault("question_answers", {})
            for i, q in enumerate(st.session_state.simple_req["questions"]):
                key = f"sr_follow_{i}"
                qa[q] = st.text_input(q, value=qa.get(q, ""), key=key)
            apply_clicked = st.button("Apply Clarifications and Update Docs")
            if apply_clicked:
                # Re-run generation with added answers
                data = _compose_data()
                out_dir = Path("docs")
                st.session_state.generated_docs = generate_all_docs(
                    data, templates_root=Path("templates")/"sdlc", out_dir=out_dir
                )
                bundle_path = out_dir / "sdlc_bundle.json"
                write_json_bundle(data, st.session_state.generated_docs, bundle_path)
                _sync_doc_tied_checks(out_dir)
                # Update backlog as well
                srs_path = out_dir / "SRS.md"
                backlog = generate_backlog_from_srs(srs_path)
                write_backlog_outputs(backlog, out_dir)
                st.success("Docs updated with your clarifications.")
                st.session_state.user_generated_docs = True
                st.rerun()

    # If a document is selected in the sidebar, render a lightweight preview here
    if st.session_state.view_doc:
        try:
            p = Path("docs") / st.session_state.view_doc
            st.markdown(f"### Preview: {st.session_state.view_doc}")
            if p.suffix == ".md":
                st.code(p.read_text(encoding="utf-8"), language="markdown")
            elif p.suffix == ".csv":
                content = p.read_text(encoding="utf-8")
                st.dataframe([r.split(",") for r in content.splitlines()])
            elif p.suffix == ".json":
                st.json(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass

    st.stop()
st.markdown('</main>', unsafe_allow_html=True)

# ---------- AI Discovery Mode ----------
if (
    st.session_state.get("discovery_mode", False)
    and st.session_state.ui_mode == "Chat Mode"
    and DISCOVERY_AVAILABLE
):
    # Initialize discovery greeting
    if not st.session_state.messages:
        greeting = (
            "Hi! I'm your AI Project Manager with intelligent discovery capabilities. "
            "I'll ask smart questions based on your industry and project type to gather all the information needed.\n\n"
            "Tell me about your project - what would you like to build?"
        )
        st.session_state.messages.append({"role": "assistant", "content": greeting})

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Discovery input handling
    if not st.session_state.get("discovery_complete", False):
        discovery_input = st.chat_input("Tell me about your project...")

        if discovery_input:
            # Add user message
            st.session_state.messages.append({"role": "user", "content": discovery_input})
            with st.chat_message("user"):
                st.write(discovery_input)

            # Process with discovery agent
            response = st.session_state.discovery_agent.process_message(discovery_input)

            # Add agent response
            st.session_state.messages.append({"role": "assistant", "content": response['message']})
            with st.chat_message("assistant"):
                st.write(response['message'])

                # Show discovery progress panel
                if response.get('context_summary'):
                    context = response['context_summary']
                    with st.expander("Discovery Progress", expanded=True):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Completeness", f"{int(context['completeness'] * 100)}%")
                        with col2:
                            st.metric("Questions Asked", context['questions_asked'])
                        with col3:
                            st.metric("Info Gathered", context['info_gathered'])

                        if context.get('industry'):
                            st.write(f"**Industry:** {context['industry'].title()}")
                        if context.get('project_type'):
                            st.write(f"**Project Type:** {context['project_type']}")

            # Handle discovery completion
            if response.get('ready'):
                st.session_state.discovery_complete = True

                # Convert to OPNXT format and populate existing session state
                opnxt_answers = st.session_state.discovery_agent.export_to_opnxt_format()
                st.session_state.answers.update(opnxt_answers)

                # Generate summaries for existing OPNXT workflow
                for phase, answers in opnxt_answers.items():
                    if answers:
                        st.session_state.summaries[phase] = f"Summary for {phase}:\n- " + "\n- ".join(answers)

                st.balloons()
                st.success("Discovery complete! Your project information has been captured and is ready for document generation.")

                # Auto-generate documents button (immediate)
                if st.button("Generate SDLC Documents", type="primary"):
                    data = {
                        "project": {"title": st.session_state.discovery_agent.context.project_type or "Untitled Project"},
                        "answers": st.session_state.answers,
                        "summaries": st.session_state.summaries,
                        "phases": SDLC_PHASES,
                    }
                    out_dir = Path("docs")
                    st.session_state.generated_docs = generate_all_docs(data, templates_root=Path("templates")/"sdlc", out_dir=out_dir)
                    bundle_path = out_dir / "sdlc_bundle.json"
                    write_json_bundle(data, st.session_state.generated_docs, bundle_path)
                    _sync_doc_tied_checks(out_dir)

                    st.success("SDLC Documents generated! See below for preview and download.")
                    st.rerun()

    else:
        # Discovery is complete: persist clear next-step actions even across reruns
        with st.chat_message("assistant"):
            st.markdown("Discovery is complete and your information is captured. Choose an action below.")
        act1, act2, act3 = st.columns(3)
        with act1:
            if st.button("Generate SDLC Documents", type="primary", use_container_width=True):
                data = {
                    "project": {"title": st.session_state.discovery_agent.context.project_type or "Untitled Project"},
                    "answers": st.session_state.answers,
                    "summaries": st.session_state.summaries,
                    "phases": SDLC_PHASES,
                }
                out_dir = Path("docs")
                st.session_state.generated_docs = generate_all_docs(data, templates_root=Path("templates")/"sdlc", out_dir=out_dir)
                bundle_path = out_dir / "sdlc_bundle.json"
                write_json_bundle(data, st.session_state.generated_docs, bundle_path)
                _sync_doc_tied_checks(out_dir)
                st.success("SDLC Documents generated! See below for preview and download.")
                st.rerun()
        with act2:
            if st.button("Start New Discovery", use_container_width=True):
                st.session_state.discovery_agent = IntelligentDiscoveryAgent()
                st.session_state.discovery_complete = False
                st.session_state.messages = []
                st.rerun()
        with act3:
            if st.button("Switch to Classic Chat", use_container_width=True):
                st.session_state.discovery_mode = False
                st.session_state.ui_mode = "Chat Mode"
                st.rerun()

    # Discovery sidebar status
    with st.sidebar:
        if st.session_state.get("discovery_mode", False):
            st.subheader("AI Discovery Status")

            agent = st.session_state.discovery_agent
            progress = agent.context.completeness
            st.progress(progress, text=f"Discovery Progress: {int(progress * 100)}%")

            if agent.context.industry:
                st.write(f"**Industry:** {agent.context.industry.title()}")
            if agent.context.project_type:
                st.write(f"**Project:** {agent.context.project_type}")

            st.write(f"**Conversation Turns:** {agent.context.conversation_turns}")
            st.write(f"**Information Items:** {len(agent.context.information_gathered)}")

            if agent.context.information_gathered:
                with st.expander("Gathered Information"):
                    for key, value in agent.context.information_gathered.items():
                        st.write(f"• **{key.replace('_', ' ').title()}:** {value}")

            if st.button("Start New Discovery", type="secondary"):
                st.session_state.discovery_agent = IntelligentDiscoveryAgent()
                st.session_state.discovery_complete = False
                st.session_state.messages = []
                st.rerun()


# System greeting on first load (Chat Mode only)
if st.session_state.ui_mode == "Chat Mode" and not st.session_state.get("discovery_mode", False) and not st.session_state.messages:
    greeting = (
        "Hi! I'm OPNXT. We'll progress through SDLC phases starting with Planning, "
        "then Requirements, Design, Implementation, Testing, Deployment, and Maintenance.\n\n"
        "Let's begin with Planning."
    )
    st.session_state.messages.append({"role": "assistant", "content": greeting})

# Determine current phase and questions BEFORE rendering Chat Mode (used by guide panel)
current_phase = st.session_state.phase
questions = SDLC_QUESTIONS[current_phase]

# Helper functions must be defined before first use
def get_current_question_text() -> str:
    if not questions:
        return ""
    idx = st.session_state.q_index
    if idx < 0 or idx >= len(questions):
        st.session_state.q_index = 0
        idx = 0
    return questions[idx]

def ask_current_question():
    q = get_current_question_text()
    if not q:
        return
    # Compose a more human-friendly message with helper details
    try:
        idx = st.session_state.q_index if 0 <= st.session_state.q_index < len(SDLC_QUESTION_HELP.get(current_phase, [])) else None
        base_helper = SDLC_QUESTION_HELP.get(current_phase, [])[idx] if idx is not None else ""
        # Audience adjustment
        audience = st.session_state.get("audience", "Beginner")
        if audience == "Beginner":
            plain = SDLC_PLAIN_LANGUAGE.get(current_phase, "")
            helper = f"{plain} — {base_helper}" if plain else base_helper
        elif audience == "Expert":
            helper = base_helper.split(". ")[0] if base_helper else ""
        else:
            helper = base_helper
    except Exception:
        helper = ""
    display = f"**{current_phase}** — {q}\n\n<small>{helper}</small>" if helper else f"**{current_phase}** — {q}"
    # Avoid duplicating the same assistant question back-to-back
    new_content = f"[{current_phase}] {q}"
    if not (st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant" and new_content == st.session_state.messages[-1]["content"]):
        st.session_state.messages.append({"role": "assistant", "content": new_content})
    with st.chat_message("assistant"):
        st.markdown(display, unsafe_allow_html=True)

# Render chat history (Chat Mode only, excluding AI Discovery)
if st.session_state.ui_mode == "Chat Mode" and not st.session_state.get("discovery_mode", False):
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    # Show phase guide at the start of Chat Mode viewport
    render_phase_guide_panel(current_phase)
    # What's next panel for clarity and manual control
    with st.expander("What's next?", expanded=True):
        st.write(f"Phase: {current_phase} — Question {st.session_state.q_index + 1} of {len(questions)}")
        st.caption("Answer the current question in the chat box below. I'll immediately ask the next one, or you can use the buttons here.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Skip to Next Question"):
                # If already at the last question, complete the phase
                if st.session_state.q_index >= len(questions) - 1:
                    st.session_state.q_index = len(questions)
                    st.rerun()
                else:
                    st.session_state.q_index = st.session_state.q_index + 1
                    ask_current_question()
                    st.stop()
        with col2:
            if st.button("Summarize This Phase Now"):
                # Force phase completion path
                st.session_state.q_index = len(questions)
                # Re-run to trigger the completion branch above
                st.rerun()

# If last message wasn't a question for the current phase/index, ask it (Chat Mode only)
# Do not auto-ask while we're awaiting phase confirmation to avoid repetition
if (
    st.session_state.ui_mode == "Chat Mode" and not st.session_state.get("discovery_mode", False)
    and not st.session_state.get("awaiting_confirmation", False)
    and (not st.session_state.messages or (
        st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant"
        and questions and get_current_question_text() not in st.session_state.messages[-1]["content"]
        and not st.session_state.messages[-1]["content"].startswith("Great! Here's a quick take")
    ))
):
    # Ensure we don't duplicate the same question continuously
    # Only ask if the last assistant message is not already this exact question
    last_assistant = next((m for m in reversed(st.session_state.messages) if m["role"] == "assistant"), None)
    expected = f"[{current_phase}] {get_current_question_text()}"
    if not last_assistant or expected not in last_assistant["content"]:
        ask_current_question()

# Chat input (Chat Mode only)
prompt = st.chat_input("Answer the question or provide more details…") if (st.session_state.ui_mode == "Chat Mode" and not st.session_state.get("discovery_mode", False)) else None
if prompt:
    # Record user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # Slash command handling: /focus <creation|validation|change>
    lc_prompt = prompt.strip().lower()
    if lc_prompt.startswith("/focus"):
        parts = lc_prompt.split()
        topic = parts[1] if len(parts) > 1 else ""
        valid_topics = {"creation", "validation", "change"}
        if topic in valid_topics:
            # Reload guides to pick up any newly added files
            st.session_state.guides = load_guides()
            path, content = st.session_state.guides.get(topic, (None, ""))
            render_focus_content(topic, content)
            # Also add a reference note to chat history for transcript completeness
            note = f"Displayed {topic} guide" + (f" from {path.as_posix()}" if path else ". File not found.")
            st.session_state.messages.append({"role": "assistant", "content": note})
        else:
            with st.chat_message("assistant"):
                st.warning("Usage: /focus <creation|validation|change>")
        st.stop()

    # Basic ambiguity handling: if response is too short or vague, ask for clarification
    def is_ambiguous(text: str) -> bool:
        lc = text.strip().lower()
        # Treat certain short explicit answers as acceptable (not ambiguous)
        explicit_ok = {"none", "n/a", "na", "tbd", "no", "not applicable"}
        if lc in explicit_ok:
            return False
        words = lc.split()
        short = len(words) < 3  # relax threshold so concise answers pass
        vague = any(w in lc for w in ["not sure", "idk", "maybe", "tbd", "unknown"])
        return short and vague  # only block if both short and vague

    # Control commands to advance the flow quickly
    _cmd = prompt.strip().lower()
    if _cmd in {"next", "proceed", "skip", "continue"} or _cmd.startswith("/next"):
        st.session_state.q_index += 1
        if st.session_state.q_index >= len(questions):
            # Force completion branch
            st.session_state.q_index = len(questions)
            st.rerun()
        else:
            ask_current_question()
            st.stop()

    if st.session_state.awaiting_confirmation:
        # Interpret confirmation response
        reply = prompt.strip().lower()
        positive = any(t in reply for t in ["yes", "yep", "looks good", "good", "ok", "okay"]) and not any(u in reply for u in ["change", "edit", "update", "revise", "no"])
        needs_changes = any(t in reply for t in ["no", "change", "edit", "update", "revise", "tweak"])

        if positive and not needs_changes:
            # proceed to next phase
            st.session_state.awaiting_confirmation = False
            st.session_state.pending_phase = ""
            nxt = next_phase(current_phase)
            if nxt:
                st.session_state.phase = nxt
                st.session_state.q_index = 0
                with st.chat_message("assistant"):
                    st.markdown(f"Moving to the next phase: **{nxt}**.")
                # Ask first question of next phase
                current_phase = st.session_state.phase
                questions = SDLC_QUESTIONS[current_phase]
                ask_current_question()
                st.stop()
            else:
                # No next phase: all phases complete – prompt to generate docs
                st.session_state.awaiting_confirmation = False
                with st.chat_message("assistant"):
                    st.markdown("All phases confirmed complete. Use the sidebar to generate SDLC docs or say 'Generate SDLC Docs'.")
                st.stop()
        else:
            # loop back into targeted refinement: re-ask the phase questions
            st.session_state.awaiting_confirmation = False
            st.session_state.pending_phase = ""
            st.session_state.phase = current_phase
            st.session_state.q_index = 0
            with st.chat_message("assistant"):
                st.markdown(f"Let's refine **{current_phase}**. I'll re-ask a few targeted questions to capture changes.")
            ask_current_question()
            st.stop()

    # Action handlers: codegen/testgen/ci with explicit confirmation
    def _is_positive(text: str) -> bool:
        lc = text.strip().lower()
        return any(t in lc for t in ["yes", "y", "ok", "okay", "do it", "proceed", "run"]) and not any(u in lc for u in ["no", "not now", "later", "cancel", "stop"])

    def run_codegen_action():
        docs = st.session_state.get("generated_docs", {})
        sdd = docs.get("SDD.md", "")
        if not sdd:
            with st.chat_message("assistant"):
                st.warning("No SDD found. Generate SDLC docs first to enable code generation.")
            return
        mapping = generate_code_from_sdd(sdd, project_root=Path("."), llm=LLM)
        written, skipped = write_generated_files(mapping, project_root=Path("."))
        files_list = "\n".join(f"- {p}" for p in mapping.keys())
        with st.chat_message("assistant"):
            st.success(f"Code generation complete. Wrote {written} files, skipped {skipped}. Files:\n{files_list}")

    def run_testgen_action():
        docs = st.session_state.get("generated_docs", {})
        srs = docs.get("SRS.md", "")
        tplan = docs.get("TestPlan.md", "")
        mapping = generate_pytests(srs_md=srs, testplan_md=tplan, llm=LLM)
        written, skipped = write_tests(mapping, project_root=Path("."))
        files_list = "\n".join(f"- {p}" for p in mapping.keys())
        with st.chat_message("assistant"):
            st.success(f"Test generation complete. Wrote {written} files, skipped {skipped}. Files:\n{files_list}")

    def run_ci_setup_action():
        path, created = scaffold_github_actions(Path("."))
        with st.chat_message("assistant"):
            if created:
                st.success(f"GitHub Actions CI workflow created at {path.as_posix()}")
            else:
                st.info(f"CI workflow already exists at {path.as_posix()}")

    # Check awaited actions
    if st.session_state.awaiting_codegen:
        if _is_positive(prompt):
            st.session_state.awaiting_codegen = False
            run_codegen_action()
            # After codegen, offer tests
            with st.chat_message("assistant"):
                st.markdown("Ready to generate tests from SRS/Test Plan? Reply 'Yes' to proceed.")
            st.session_state.awaiting_testgen = True
            st.stop()
        else:
            st.session_state.awaiting_codegen = False
    if st.session_state.awaiting_testgen:
        if _is_positive(prompt):
            st.session_state.awaiting_testgen = False
            run_testgen_action()
            # After tests, offer CI setup
            with st.chat_message("assistant"):
                st.markdown("Set up GitHub Actions CI to run tests on pushes? Reply 'Yes' to scaffold.")
            st.session_state.awaiting_ci_setup = True
            st.stop()
        else:
            st.session_state.awaiting_testgen = False
    if st.session_state.awaiting_ci_setup:
        if _is_positive(prompt):
            st.session_state.awaiting_ci_setup = False
            run_ci_setup_action()
            st.stop()
        else:
            st.session_state.awaiting_ci_setup = False

    # Save answer for the current phase/question (normal path), unless ambiguous
    if is_ambiguous(prompt):
        with st.chat_message("assistant"):
            # Restate the current question with helper tips so it's clear what to provide
            idx = st.session_state.q_index if 0 <= st.session_state.q_index < len(SDLC_QUESTION_HELP.get(current_phase, [])) else None
            base_helper = SDLC_QUESTION_HELP.get(current_phase, [])[idx] if idx is not None else ""
            audience = st.session_state.get("audience", "Beginner")
            if audience == "Beginner":
                plain = SDLC_PLAIN_LANGUAGE.get(current_phase, "")
                helper = f"{plain} — {base_helper}" if plain else base_helper
            elif audience == "Expert":
                helper = base_helper.split(". ")[0] if base_helper else ""
            else:
                helper = base_helper
            st.warning("I need a bit more detail to proceed. Please add specifics, examples, or constraints.")
            st.markdown(f"Re-stating the question for clarity: <br><br> <b>{get_current_question_text()}</b>", unsafe_allow_html=True)
            if helper:
                st.caption(helper)
            st.info("Tip: You can also use the 'What's next?' panel above to skip to the next question or summarize the phase.")
        st.stop()
    else:
        st.session_state.answers[current_phase].append(prompt)

    # Advance question index or phase
    st.session_state.q_index += 1
    phase_completed = st.session_state.q_index >= len(questions)

    if phase_completed:
        # Summarize phase and move to next
        summary_text = summarize_phase(current_phase, st.session_state.answers[current_phase])
        st.session_state.summaries[current_phase] = summary_text
        progress_msg = (
            f"Completed phase: **{current_phase}**.\n\n{summary_text}\n\n"
            f"Progress: {SDLC_PHASES.index(current_phase) + 1}/{len(SDLC_PHASES)} phases."
        )
        st.session_state.messages.append({"role": "assistant", "content": progress_msg})
        with st.chat_message("assistant"):
            st.markdown(progress_msg)

        # Post-phase validation loop
        # 1) Validate current phase checklist against available docs and standards
        try:
            phase_result = vdoc.validate_phase(current_phase, Path("docs"), st.session_state.get("generated_docs", {}))
            # Sync session checklist state from updated guide
            _p = Path("docs") / get_phase_filename(current_phase)
            if _p.exists():
                try:
                    _content = _p.read_text(encoding="utf-8")
                    _parsed = {}
                    for _line in _content.splitlines():
                        _ls = _line.lstrip()
                        if _ls.startswith("- [x] ") or _ls.startswith("- [ ] "):
                            _checked = _ls.startswith("- [x] ")
                            _text = _ls[6:]
                            _parsed[_text] = _checked
                    # Only update known items for this phase
                    for _item in DEFAULT_CHECKLISTS.get(current_phase, []):
                        st.session_state.phase_progress.setdefault(current_phase, {})
                        if _item in _parsed:
                            st.session_state.phase_progress[current_phase][_item] = _parsed[_item]
                except Exception:
                    pass
            # 2) Emit prompts for outstanding items in chat
            prompts = vdoc.prompts_for_outstanding(current_phase, phase_result)
            if prompts:
                with st.chat_message("assistant"):
                    st.markdown("Outstanding items detected for this phase. Please address the following:")
                    for pmsg in prompts:
                        st.markdown(f"- {pmsg}")
        except Exception:
            pass

        confirm_q = "Does this match your intent? Any changes? Reply 'Yes' to proceed or describe changes."
        st.session_state.awaiting_confirmation = True
        st.session_state.pending_phase = current_phase
        st.session_state.messages.append({"role": "assistant", "content": confirm_q})
        with st.chat_message("assistant"):
            st.markdown(confirm_q)
        st.stop()

        nxt = next_phase(current_phase)
        if nxt:
            st.session_state.phase = nxt
            st.session_state.q_index = 0
            with st.chat_message("assistant"):
                st.markdown(f"Moving to the next phase: **{nxt}**.")
            # Ask first question of next phase
            current_phase = st.session_state.phase
            questions = SDLC_QUESTIONS[current_phase]
            ask_current_question()
        else:
            # All phases complete: generate SDLC documents
            with st.chat_message("assistant"):
                st.markdown("All SDLC phases complete. Generating SDLC documents (Charter, SRS, SDD, Test Plan)…")
            data = {
                "project": {"title": st.session_state.answers.get("Planning", ["Untitled Project"])[0] if st.session_state.answers.get("Planning") else "Untitled Project"},
                "answers": st.session_state.answers,
                "summaries": st.session_state.summaries,
                "phases": SDLC_PHASES,
            }
            out_dir = Path("docs")
            st.session_state.generated_docs = generate_all_docs(data, templates_root=Path("templates")/"sdlc", out_dir=out_dir)
            # Write JSON bundle
            bundle_path = out_dir / "sdlc_bundle.json"
            write_json_bundle(data, st.session_state.generated_docs, bundle_path)
            # Update phase guides to reflect any new doc presence and auto-check tied items
            _sync_doc_tied_checks(out_dir)
            # Optional auto-validate
            if st.session_state.auto_validate:
                report = vdoc.build_report(st.session_state.generated_docs)
                report_path = out_dir / "validation_report.json"
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
                issues = report.get("issues", {})
                total_missing = sum(len(v) for v in issues.values() if v)
                with st.chat_message("assistant"):
                    if total_missing == 0:
                        st.markdown("Auto-validation complete: no missing sections detected. ✅")
                    else:
                        st.markdown(f"Auto-validation detected {total_missing} missing sections across documents. See validation_report.json for details.")
                # Additionally, validate and auto-tick all phase checklists now that docs exist
                try:
                    aggregate_prompts: List[str] = []
                    for _phase in SDLC_PHASES:
                        _vres = vdoc.validate_phase(_phase, out_dir, st.session_state.generated_docs)
                        # Sync session state per phase
                        _f = out_dir / get_phase_filename(_phase)
                        if _f.exists():
                            try:
                                _content = _f.read_text(encoding="utf-8")
                                _parsed = {}
                                for _line in _content.splitlines():
                                    _ls = _line.lstrip()
                                    if _ls.startswith("- [x] ") or _ls.startswith("- [ ] "):
                                        _checked = _ls.startswith("- [x] ")
                                        _text = _ls[6:]
                                        _parsed[_text] = _checked
                                for _item in DEFAULT_CHECKLISTS.get(_phase, []):
                                    st.session_state.phase_progress.setdefault(_phase, {})
                                    if _item in _parsed:
                                        st.session_state.phase_progress[_phase][_item] = _parsed[_item]
                            except Exception:
                                pass
                        aggregate_prompts.extend(vdoc.prompts_for_outstanding(_phase, _vres))
                    if aggregate_prompts:
                        with st.chat_message("assistant"):
                            st.markdown("Phase checklist review complete. Remaining items:")
                            for _p in aggregate_prompts:
                                st.markdown(f"- {_p}")
                except Exception:
                    pass
            with st.chat_message("assistant"):
                st.success("Documents generated in docs/ folder. See below to preview and download.")

    else:
        # Immediately ask the next question to make the flow obvious
        ask_current_question()
        st.stop()

    # Toggle for extra guidance
    st.toggle("Show extra guidance", key="show_guidance")

# ---------------------- Form Mode ----------------------
if st.session_state.ui_mode == "Form Mode":
    st.subheader("Phase-specific Forms")
    # Show plain-language guidance for beginners
    if st.session_state.show_guidance:
        st.info(SDLC_PLAIN_LANGUAGE.get(current_phase, ""))
    st.caption(BEST_PRACTICES.get(current_phase, ""))
    # Render the phase guide panel in Form Mode as well
    render_phase_guide_panel(current_phase)

    # Allow selecting a phase to edit
    selected_phase = st.selectbox("Select Phase", SDLC_PHASES, index=SDLC_PHASES.index(current_phase))
    if selected_phase != current_phase:
        st.session_state.phase = selected_phase
        st.session_state.q_index = 0
        current_phase = selected_phase
        questions = SDLC_QUESTIONS[current_phase]

    def _save_phase_inputs(phase: str, items: List[str]):
        cleaned = [i.strip() for i in items if i and i.strip()]
        st.session_state.answers[phase] = cleaned
        st.success(f"Saved {len(cleaned)} item(s) for {phase}.")

    # Render forms per phase
    if current_phase == "Planning":
        goals = st.text_area("Project goals (one per line)", value="\n".join(st.session_state.answers.get("Planning", [])), help="State measurable goals aligned to business outcomes.")
        stakeholders = st.text_area("Stakeholders & target users", help="List roles, sponsors, and primary user personas.")
        timeline = st.text_input("Timeline / launch window", help="Key dates, dependencies, and constraints.")
        if st.button("Save Planning Inputs"):
            items = []
            if goals.strip():
                items.extend([g.strip() for g in goals.splitlines() if g.strip()])
            if stakeholders.strip():
                items.append(f"Stakeholders: {stakeholders.strip()}")
            if timeline.strip():
                items.append(f"Timeline: {timeline.strip()}")
            _save_phase_inputs("Planning", items)

    elif current_phase == "Requirements":
        funcs = st.text_area("Functional requirements (one per line)", value="\n".join([a for a in st.session_state.answers.get("Requirements", []) if not a.lower().startswith("nfr:")]), help="Use SHALL statements when possible.")
        nfrs = st.text_area("Non-functional requirements (NFRs)", help="e.g., performance, security (ISO 27001), availability, usability (ISO 25010)")
        kpis = st.text_area("Success metrics / KPIs", help="Define measurable outcomes and acceptance criteria.")
        if st.button("Save Requirements Inputs"):
            items = []
            if funcs.strip():
                items.extend([f.strip() for f in funcs.splitlines() if f.strip()])
            if nfrs.strip():
                for n in nfrs.splitlines():
                    if n.strip():
                        items.append(f"NFR: {n.strip()}")
            if kpis.strip():
                items.append(f"KPIs: {kpis.strip()}")
            _save_phase_inputs("Requirements", items)

    elif current_phase == "Design":
        arch = st.text_area("Architecture & components", help="High-level architecture view, patterns, and components.")
        interfaces = st.text_area("Interfaces & integrations", help="APIs, protocols, external systems.")
        data = st.text_area("Data model considerations", help="Entities, schemas, domains, privacy.")
        if st.button("Save Design Inputs"):
            items = []
            if arch.strip():
                items.append(f"Architecture: {arch.strip()}")
            if interfaces.strip():
                items.append(f"Interfaces: {interfaces.strip()}")
            if data.strip():
                items.append(f"Data: {data.strip()}")
            _save_phase_inputs("Design", items)

    elif current_phase == "Implementation":
        approach = st.text_input("Development approach & roles", help="Agile/Kanban, code ownership, review policy.")
        mvp = st.text_area("MVP scope & priorities", help="Initial deliverables and sequencing.")
        if st.button("Save Implementation Inputs"):
            items = []
            if approach.strip():
                items.append(f"Approach: {approach.strip()}")
            if mvp.strip():
                items.append(f"MVP: {mvp.strip()}")
            _save_phase_inputs("Implementation", items)

    elif current_phase == "Testing":
        strategy = st.text_area("Testing strategy", help="Unit/integration/e2e, automation, coverage.")
        env = st.text_area("QA environments & test data", help="Test environments, data mgmt, synthetic data.")
        if st.button("Save Testing Inputs"):
            items = []
            if strategy.strip():
                items.append(f"Strategy: {strategy.strip()}")
            if env.strip():
                items.append(f"Environments: {env.strip()}")
            _save_phase_inputs("Testing", items)

    elif current_phase == "Deployment":
        rel = st.text_input("Release strategy", help="Staged, blue/green, canary, rollback.")
        target = st.text_input("Target environments", help="Cloud/provider/regions, IaC.")
        if st.button("Save Deployment Inputs"):
            items = []
            if rel.strip():
                items.append(f"Release: {rel.strip()}")
            if target.strip():
                items.append(f"Targets: {target.strip()}")
            _save_phase_inputs("Deployment", items)

    elif current_phase == "Maintenance":
        obs = st.text_area("Monitoring & observability", help="Metrics, logs, traces, SLOs.")
        support = st.text_area("Support/SLAs & incident response", help="Ticketing, escalation, RTO/RPO.")
        if st.button("Save Maintenance Inputs"):
            items = []
            if obs.strip():
                items.append(f"Observability: {obs.strip()}")
            if support.strip():
                items.append(f"Support: {support.strip()}")
            _save_phase_inputs("Maintenance", items)

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Summarize Phase"):
            summary_text = summarize_phase(current_phase, st.session_state.answers[current_phase])
            st.session_state.summaries[current_phase] = summary_text
            st.success("Phase summarized.")
            st.markdown(summary_text)
    with col2:
        nxt = next_phase(current_phase)
        if st.button("Mark Phase Complete ➜ Next", disabled=(not nxt)):
            summary_text = summarize_phase(current_phase, st.session_state.answers[current_phase])
            st.session_state.summaries[current_phase] = summary_text
            if nxt:
                st.session_state.phase = nxt
                st.session_state.q_index = 0
                st.info(f"Moved to next phase: {nxt}")
    with col3:
        if st.button("Generate SDLC Docs Now"):
            data = {
                "project": {"title": st.session_state.answers.get("Planning", ["Untitled Project"])[0] if st.session_state.answers.get("Planning") else "Untitled Project"},
                "answers": st.session_state.answers,
                "summaries": st.session_state.summaries,
                "phases": SDLC_PHASES,
            }
            out_dir = Path("docs")
            st.session_state.generated_docs = generate_all_docs(data, templates_root=Path("templates")/"sdlc", out_dir=out_dir)
            bundle_path = out_dir / "sdlc_bundle.json"
            write_json_bundle(data, st.session_state.generated_docs, bundle_path)
            _sync_doc_tied_checks(out_dir)
            if st.session_state.auto_validate:
                report = vdoc.build_report(st.session_state.generated_docs)
                report_path = out_dir / "validation_report.json"
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
                issues = report.get("issues", {})
                total_missing = sum(len(v) for v in issues.values() if v)
                if total_missing == 0:
                    st.success("Auto-validation complete: no missing sections detected. ✅")
                else:
                    st.warning(f"Auto-validation detected {total_missing} missing sections. See validation_report.json.")
            st.success("Documents generated in docs/ folder. See below to preview and download.")

# Sidebar
with st.sidebar:
    st.header("Settings")
    st.write("Backend: xAI Grok (OpenAI-compatible)")
    st.write("Set XAI_API_KEY (or OPENAI_API_KEY) and OPENAI_BASE_URL if needed.")
    st.caption("If no API key is set, answers are still captured and simple local summaries are used.")

    st.divider()
    st.subheader("Guides")
    guides = st.session_state.get("guides", {})
    def _guide_button(key: str, label: str):
        path, content = guides.get(key, (None, ""))
        btn_label = label + (" ✅" if path else " ❔")
        if st.button(btn_label, use_container_width=True, key=f"guide_btn_{key}"):
            render_focus_content(key, content)
    _guide_button("creation", "Open Creation Guide")
    _guide_button("validation", "Open Validation Checklist")
    _guide_button("change", "Open Change Tracker")

    st.caption("Tip: In chat, type /focus creation, /focus validation, or /focus change")
    st.divider()
    with st.expander("SDLC Glossary", expanded=False):
        for term, definition in SDLC_GLOSSARY.items():
            st.markdown(f"- **{term}**: {definition}")
    st.subheader("Generate Artifacts")
    st.checkbox("Auto-validate after generation", value=st.session_state.auto_validate, key="auto_validate")

    def render_prd(answers: Dict[str, List[str]], summaries: Dict[str, str]) -> str:
        """Render a PRD.md document from collected answers and summaries.

        Uses templates/sdlc_template.md as a loose skeleton but fills content
        based on captured inputs. This is intentionally simple and can be
        upgraded to a proper templating engine later.
        """
        title = "Project PRD"
        planning = "\n".join(f"- {a}" for a in answers.get("Planning", [])) or "- N/A"
        requirements = "\n".join(f"- {a}" for a in answers.get("Requirements", [])) or "- N/A"
        design = "\n".join(f"- {a}" for a in answers.get("Design", [])) or "- N/A"
        impl = "\n".join(f"- {a}" for a in answers.get("Implementation", [])) or "- N/A"
        testing = "\n".join(f"- {a}" for a in answers.get("Testing", [])) or "- N/A"
        deploy = "\n".join(f"- {a}" for a in answers.get("Deployment", [])) or "- N/A"
        maint = "\n".join(f"- {a}" for a in answers.get("Maintenance", [])) or "- N/A"

        # Try to read the template header if present
        template_path = Path("templates/sdlc_template.md")
        header = template_path.read_text(encoding="utf-8") if template_path.exists() else "# Project Name\n\n## Overview\n"

        # Compose PRD
        content = f"""
{header}

---
_Generated: {datetime.utcnow().isoformat()}Z_

## Phase Summaries
{summaries.get('Planning', '')}

{summaries.get('Requirements', '')}

{summaries.get('Design', '')}

{summaries.get('Implementation', '')}

{summaries.get('Testing', '')}

{summaries.get('Deployment', '')}

{summaries.get('Maintenance', '')}

## Inputs by Phase
### Planning
{planning}

### Requirements
{requirements}

### Design
{design}

### Implementation
{impl}

### Testing
{testing}

### Deployment
{deploy}

### Maintenance
{maint}
""".strip()
        return content

    if st.button("Generate PRD.md", use_container_width=True):
        prd_text = render_prd(st.session_state.answers, st.session_state.summaries)
        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        prd_path = docs_dir / "PRD.md"
        prd_path.write_text(prd_text, encoding="utf-8")
        st.success(f"PRD generated at {prd_path.as_posix()}")
        st.download_button(
            label="Download PRD.md",
            data=prd_text,
            file_name="PRD.md",
            mime="text/markdown",
            use_container_width=True,
        )

    if st.button("Generate SDLC Docs (Charter/SRS/SDD/Test Plan)", use_container_width=True):
        data = {
            "project": {"title": st.session_state.answers.get("Planning", ["Untitled Project"])[0] if st.session_state.answers.get("Planning") else "Untitled Project"},
            "answers": st.session_state.answers,
            "summaries": st.session_state.summaries,
            "phases": SDLC_PHASES,
        }
        out_dir = Path("docs")
        st.session_state.generated_docs = generate_all_docs(data, templates_root=Path("templates")/"sdlc", out_dir=out_dir)
        # Write JSON bundle
        bundle_path = out_dir / "sdlc_bundle.json"
        write_json_bundle(data, st.session_state.generated_docs, bundle_path)
        # Optional auto-validate
        if st.session_state.auto_validate:
            report = vdoc.build_report(st.session_state.generated_docs)
            report_path = out_dir / "validation_report.json"
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            issues = report.get("issues", {})
            total_missing = sum(len(v) for v in issues.values() if v)
            if total_missing == 0:
                st.success("SDLC docs generated. Auto-validation: no missing sections.")
            else:
                st.warning(f"SDLC docs generated. Auto-validation found {total_missing} missing sections. See validation_report.json.")
        else:
            st.success("SDLC docs and JSON bundle generated in docs/ folder.")
        # Offer next action in chat
        st.session_state.awaiting_codegen = True
        st.session_state.messages.append({"role": "assistant", "content": "Ready to generate code from the SDD? Reply 'Yes' to proceed."})

    # Discovery Integration in Sidebar
    if st.session_state.get("discovery_complete", False):
        st.success("Discovery Complete")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Generate Docs", use_container_width=True):
                data = {
                    "project": {"title": st.session_state.discovery_agent.context.project_type or "Untitled Project"},
                    "answers": st.session_state.answers,
                    "summaries": st.session_state.summaries,
                    "phases": SDLC_PHASES,
                }
                out_dir = Path("docs")
                st.session_state.generated_docs = generate_all_docs(data, templates_root=Path("templates")/"sdlc", out_dir=out_dir)
                st.success("Documents generated!")
                st.rerun()
        with col2:
            if st.button("Generate Code", use_container_width=True):
                docs = st.session_state.get("generated_docs", {})
                sdd = docs.get("SDD.md", "")
                if sdd:
                    mapping = generate_code_from_sdd(sdd, project_root=Path("."), llm=LLM)
                    written, skipped = write_generated_files(mapping, project_root=Path("."))
                    st.success(f"Code generated! {written} files created.")
                else:
                    st.warning("Generate documents first.")

    if st.button("Export ALL to PDF (ZIP)", use_container_width=True):
        # Ensure we have generated docs
        if not st.session_state.get("generated_docs"):
            data = {
                "project": {"title": st.session_state.answers.get("Planning", ["Untitled Project"])[0] if st.session_state.answers.get("Planning") else "Untitled Project"},
                "answers": st.session_state.answers,
                "summaries": st.session_state.summaries,
                "phases": SDLC_PHASES,
            }
            out_dir = Path("docs")
            st.session_state.generated_docs = generate_all_docs(data, templates_root=Path("templates")/"sdlc", out_dir=out_dir)

        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname, content in st.session_state.generated_docs.items():
                pdf_name = Path(fname).with_suffix('.pdf').name
                pdf_path = docs_dir / pdf_name
                ok = markdown_to_pdf(content, pdf_path)
                if ok and pdf_path.exists():
                    zf.write(str(pdf_path), arcname=pdf_name)
        zip_buffer.seek(0)
        st.download_button(
            label="Download PDFs (ZIP)",
            data=zip_buffer,
            file_name="sdlc_documents.zip",
            mime="application/zip",
            use_container_width=True,
        )

    st.divider()
    st.subheader("Validate Docs")
    if st.button("Validate Generated Docs", use_container_width=True):
        docs = st.session_state.get("generated_docs", {})
        if not docs:
            st.warning("Generate documents first.")
        else:
            issues = vdoc.validate_all(docs)
            followups = vdoc.followup_questions(issues)
            # Persist validation report
            report = vdoc.build_report(docs)
            reports_dir = Path("docs")
            reports_dir.mkdir(exist_ok=True)
            report_path = reports_dir / "validation_report.json"
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

            if not any(issues.values()):
                st.success("No missing sections detected in the generated docs.")
            else:
                st.warning("Some sections are missing or incomplete. I've posted follow-up questions in chat.")
                # Surface follow-up questions in chat for user to answer
                for (fname, sec, question) in followups[:10]:
                    msg = f"[{fname} :: {sec}] {question}"
                    st.session_state.messages.append({"role": "assistant", "content": msg})
            # Offer report download
            st.download_button(
                label="Download Validation Report (JSON)",
                data=report_path.read_bytes(),
                file_name="validation_report.json",
                mime="application/json",
                use_container_width=True,
            )

    st.divider()
    st.subheader("Automation")
    if st.button("Generate Code from SDD", use_container_width=True):
        docs = st.session_state.get("generated_docs", {})
        sdd = docs.get("SDD.md", "")
        if not sdd:
            st.warning("No SDD found. Generate SDLC docs first.")
        else:
            mapping = generate_code_from_sdd(sdd, project_root=Path("."), llm=LLM)
            written, skipped = write_generated_files(mapping, project_root=Path("."))
            st.success(f"Code generation complete. Wrote {written}, skipped {skipped}.")

    if st.button("Generate Pytests from SRS/Test Plan", use_container_width=True):
        docs = st.session_state.get("generated_docs", {})
        srs = docs.get("SRS.md", "")
        tplan = docs.get("TestPlan.md", "")
        mapping = generate_pytests(srs_md=srs, testplan_md=tplan, llm=LLM)
        written, skipped = write_tests(mapping, project_root=Path("."))
        st.success(f"Test generation complete. Wrote {written}, skipped {skipped}.")

    if st.button("Setup GitHub Actions CI", use_container_width=True):
        path, created = scaffold_github_actions(Path("."))
        if created:
            st.success(f"CI workflow created at {path.as_posix()}")
        else:
            st.info(f"CI workflow already exists at {path.as_posix()}")

# Preview generated SDLC docs in main area
if st.session_state.get("generated_docs"):
    st.divider()
    st.subheader("Generated SDLC Documents")
    tabs = st.tabs(list(st.session_state.generated_docs.keys()))
    for idx, (fname, content) in enumerate(st.session_state.generated_docs.items()):
        with tabs[idx]:
            st.markdown(f"**{fname}**")
            st.download_button(
                label=f"Download {fname}",
                data=content,
                file_name=fname,
                mime="text/markdown",
                use_container_width=True,
            )
            st.markdown(content)

    # JSON bundle download
    bundle_file = Path("docs") / "sdlc_bundle.json"
    if bundle_file.exists():
        st.download_button(
            label="Download SDLC JSON Bundle",
            data=bundle_file.read_bytes(),
            file_name="sdlc_bundle.json",
            mime="application/json",
            use_container_width=True,
        )

    # Validation report download (if exists)
    val_file = Path("docs") / "validation_report.json"
    if val_file.exists():
        st.download_button(
            label="Download Validation Report (JSON)",
            data=val_file.read_bytes(),
            file_name="validation_report.json",
            mime="application/json",
            use_container_width=True,
        )
