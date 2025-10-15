from __future__ import annotations

from typing import Iterable, List, Optional

from ..domain.chat_intents import ChatIntent


# NOTE: Keep catalog simple and configuration-light for now. Future iterations can
# load from persistence once product-market fit for these intents is validated.
_CHAT_INTENTS: List[ChatIntent] = [
    ChatIntent(
        intent_id="capture-project-kickoff",
        title="Conversational Project Kickoff",
        group="Capture & Plan",
        description="Frame the problem, stakeholders, and scope so the team can align before delivery starts.",
        prefill_prompt="We need to capture a fresh initiative. Help clarify the problem, desired outcomes, primary personas, success metrics, and top risks so we can produce a kickoff charter and BRD.",
        deliverables=["Project Charter", "Business Requirements Document"],
        personas=["pm", "product", "analyst"],
        guardrails=["enterprise-guardrails", "quality-gate"],
        icon="🧭",
        requirement_area="Collaboration",
        core_functionality="Supports real-time collaborative editing, document sharing, and version control (in paid plans).",
        opnxt_benefit="Team Alignment: Ensures all stakeholders (PMs, Engineers, Designers, Executives) are working from a single, up-to-date source of truth.",
    ),
    ChatIntent(
        intent_id="doc-generation",
        title="Doc Generation On Demand",
        group="Deliver & Execute",
        description="Produce SRS, test plans, or architecture docs from project context or a fresh conversation.",
        prefill_prompt="I want to generate delivery-ready documentation. Pull from the latest project context and chat with me to fill any gaps before producing SRS, Test Plan, and Architecture docs.",
        deliverables=["SRS", "Test Plan", "Solution Design Document"],
        personas=["pm", "engineer", "architect"],
        guardrails=["enterprise-guardrails", "quality-gate"],
        icon="📄",
        requirement_area="Rapid Documentation",
        core_functionality="Generates comprehensive PRDs and product specs from minimal, high-level input (e.g., a simple idea or outline) in minutes.",
        opnxt_benefit="Speed: Accelerates the crucial 'Requirements Gathering' and 'Analysis' phases, reducing time to a first draft by a significant margin.",
    ),
    ChatIntent(
        intent_id="document-enhancement",
        title="Document Enhancement",
        group="Improve & Govern",
        description="Refine an existing artifact through guided review without regenerating from scratch.",
        prefill_prompt="Help me improve an existing document. Ask targeted questions, tighten requirements language, and highlight missing NFRs or governance checks before we finalize it.",
        deliverables=["Redline Recommendations", "Updated Artifact"],
        personas=["pm", "analyst", "approver"],
        guardrails=["enterprise-guardrails"],
        icon="🛠️",
        requirement_area="Quality & Structure",
        core_functionality="Uses AI that understands product strategy and management principles to produce structured, high-quality documents that cover all necessary sections.",
        opnxt_benefit="Consistency & Completeness: Ensures PRDs are consistently formatted and meet a high standard, minimizing gaps and omissions in the initial requirements.",
    ),
    ChatIntent(
        intent_id="project-health-audit",
        title="Project Health Audit",
        group="Improve & Govern",
        description="Assess readiness using traceability, coverage, and compliance signals to surface risks.",
        prefill_prompt="We need an audit of this project. Review traceability, coverage, and compliance posture, then summarize risks with recommended next actions.",
        deliverables=["Health Report", "Risk Register"],
        personas=["approver", "pm", "auditor"],
        guardrails=["enterprise-guardrails", "quality-gate"],
        icon="🩺",
        requirement_area="Requirements Refinement",
        core_functionality="Offers 'product coaching' and review features to check for gaps, inconsistencies, and suggest improvements to the document.",
        opnxt_benefit="Analysis & Validation: Aids the 'Design/Analysis' phase by helping PMs and analysts validate requirements and strengthen the product narrative.",
    ),
    ChatIntent(
        intent_id="engineering-accelerator",
        title="Engineering Accelerator",
        group="Deliver & Execute",
        description="Translate intent into implementation guidance, coding suggestions, and test scaffolding.",
        prefill_prompt="Act as my engineering copilot. Given our goals, collaborate on architecture options, coding tasks, and test scaffolds while tracking SDLC gates.",
        deliverables=["Implementation Backlog", "Test Scaffolds"],
        personas=["engineer", "architect"],
        guardrails=["quality-gate"],
        icon="⚙️",
        requirement_area="Technical Specification",
        core_functionality="Ability to generate a separate Technical Specification (Tech Spec) alongside the PRD to detail system architecture, data models, and technical constraints.",
        opnxt_benefit="Design & Implementation Prep: Provides necessary detail for the 'Design' and 'Implementation' phases, ensuring the technical team is aligned with the product vision.",
    ),
    ChatIntent(
        intent_id="feedback-coaching",
        title="Feedback & Coaching Loop",
        group="Capture & Plan",
        description="Provide persona-tailored coaching, next best actions, and prompts to keep momentum.",
        prefill_prompt="Offer coaching tailored to my role. Highlight next best actions, knowledge gaps, and prompts I should explore to move this initiative forward.",
        deliverables=["Action Plan", "Coaching Transcript"],
        personas=["pm", "engineer", "analyst"],
        guardrails=["enterprise-guardrails"],
        icon="🎯",
        requirement_area="Workflow Integration",
        core_functionality="Supports integration and export to tools commonly used in the SDLC like Notion, Google Docs, Slack, and Linear (for issue tracking).",
        opnxt_benefit="Traceability & Collaboration: Keeps requirements connected to the rest of the development workflow (e.g., issue tracking) and centralizes product context.",
    ),
]


def list_intents(persona: Optional[str] = None) -> List[ChatIntent]:
    intents: Iterable[ChatIntent] = _CHAT_INTENTS
    if persona:
        persona_lower = persona.lower()
        prioritized: List[ChatIntent] = []
        remainder: List[ChatIntent] = []
        for intent in intents:
            if any(persona_lower == p.lower() for p in intent.personas):
                prioritized.append(intent)
            else:
                remainder.append(intent)
        return prioritized + remainder
    return list(intents)


def get_intent(intent_id: str) -> Optional[ChatIntent]:
    for intent in _CHAT_INTENTS:
        if intent.intent_id == intent_id:
            return intent
    return None
