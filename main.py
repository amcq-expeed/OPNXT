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

st.set_page_config(page_title="OPNXT SDLC Assistant", page_icon="💬", layout="centered")

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

st.title("OPNXT SDLC Automation Assistant 💬")
st.caption("Choose Chat Mode or Form Mode to capture SDLC inputs. Switch anytime; your data persists.")

# Sidebar: Phase Guides quick access
with st.sidebar:
    st.header("Guides")
    idx_path = Path("docs") / "guides_index.md"
    if idx_path.exists():
        st.markdown(f"[Open Guides Index]({idx_path.as_posix()})")
    else:
        st.caption("Guides index will appear after guides are generated.")
    # Link to current phase guide
    try:
        cur_fname = get_phase_filename(st.session_state.get("phase", "Planning"))
        cur_path = Path("docs") / cur_fname
        st.markdown(f"[Current Phase Guide]({cur_path.as_posix()})")
    except Exception:
        pass

# Global mode selector
st.markdown("---")
st.session_state.ui_mode = st.radio(
    "Interaction Mode",
    options=["Chat Mode", "Form Mode"],
    index=["Chat Mode", "Form Mode"].index(st.session_state.ui_mode) if st.session_state.get("ui_mode") else 0,
    horizontal=True,
)
st.markdown("---")

# Audience selector
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
st.markdown("---")

# System greeting on first load (Chat Mode only)
if st.session_state.ui_mode == "Chat Mode" and not st.session_state.messages:
    greeting = (
        "Hi! I'm OPNXT. We'll progress through SDLC phases starting with Planning, "
        "then Requirements, Design, Implementation, Testing, Deployment, and Maintenance.\n\n"
        "Let's begin with Planning."
    )
    st.session_state.messages.append({"role": "assistant", "content": greeting})

# Determine current phase and questions BEFORE rendering Chat Mode (used by guide panel)
current_phase = st.session_state.phase
questions = SDLC_QUESTIONS[current_phase]

# Render chat history (Chat Mode only)
if st.session_state.ui_mode == "Chat Mode":
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    # Show phase guide at the start of Chat Mode viewport
    render_phase_guide_panel(current_phase)

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
    st.session_state.messages.append({"role": "assistant", "content": f"[{current_phase}] {q}"})
    with st.chat_message("assistant"):
        st.markdown(display, unsafe_allow_html=True)

# If last message wasn't a question for the current phase/index, ask it (Chat Mode only)
if st.session_state.ui_mode == "Chat Mode" and (not st.session_state.messages or (
    st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant"
    and questions and get_current_question_text() not in st.session_state.messages[-1]["content"]
    and not st.session_state.messages[-1]["content"].startswith("Great! Here's a quick take")
)):
    # Ensure we don't duplicate the same question continuously
    # Only ask if the last assistant message is not already this exact question
    last_assistant = next((m for m in reversed(st.session_state.messages) if m["role"] == "assistant"), None)
    expected = f"[{current_phase}] {get_current_question_text()}"
    if not last_assistant or expected not in last_assistant["content"]:
        ask_current_question()

# Chat input (Chat Mode only)
prompt = st.chat_input("Answer the question or provide more details…") if st.session_state.ui_mode == "Chat Mode" else None
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
        short = len(lc.split()) < 5
        vague = any(w in lc for w in ["not sure", "idk", "maybe", "tbd", "unknown"])
        return short or vague

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
            st.markdown("I need a bit more detail to proceed. Could you elaborate with specifics, examples, or constraints?")
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
            with st.chat_message("assistant"):
                st.success("Documents generated in docs/ folder. See below to preview and download.")

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
