from __future__ import annotations

from typing import Iterable, List, Optional

from ..domain.chat_intents import ChatIntent


# NOTE: Keep catalog simple and configuration-light for now. Future iterations can
# load from persistence once product-market fit for these intents is validated.
_CHAT_INTENTS: List[ChatIntent] = [
    # TILE 1: FROM CONCEPT TO REQUIREMENTS (SDLC: Analysis)
    ChatIntent(
        intent_id="requirements-baseline",  # Updated ID for clarity
        title="From Concept to Requirements",
        group="End-to-End",
        description="Turn your idea into a scoped project with defined goals, requirements, and delivery plan.",
        prefill_prompt="Welcome! I'm ready to turn your idea into a full engineering plan. As a **Senior Solutions Architect**, I need just a few details. In a sentence or two, please tell me: **What is the core problem your application solves, and who is the target user?** I will use this to automatically populate the entire **`SDLC_PLAN.md`** with requirements, success metrics, and a basic technology stack.",
        deliverables=[
            "Project Charter",
            "Requirements Baseline",
            "Architecture Blueprint",
            "Test Strategy",
        ],
        personas=["pm", "engineer", "analyst", "architect"],
        guardrails=["enterprise-guardrails", "quality-gate"],
        icon="🧭",
        requirement_area="Collaboration",
        core_functionality="Supports real-time collaborative editing, document sharing, and version control (in paid plans).",
        opnxt_benefit="Team Alignment: Ensures all artifacts are traceable to the core requirement.",
    ),

    # TILE 2: AUTO-GENERATE SDLC DOCS (SDLC: Design)
    ChatIntent(
        intent_id="generate-sdlc-doc",
        title="Auto-Generate SDLC Docs",
        group="SDLC Phase",
        description="Instantly create SRS, test plans, or architecture docs from project context or a short chat.",
        prefill_prompt="Let's formalize your project's blueprint. I can generate any core SDLC document (e.g., **Software Architecture Document, Data Schema, or Detailed Test Plan**). Which specific document do you need me to generate right now, and what existing project file (like your plan or requirements) should I reference to ensure it's accurate?",
        deliverables=["Architecture Document", "Test Plan", "Data Schema"],
        personas=["engineer", "architect", "analyst"],
        guardrails=["enterprise-guardrails"],
        icon="📄",
        requirement_area="Documentation",
        core_functionality="Generates high-quality, structured documents based on the existing project context and plans.",
        opnxt_benefit="Accelerated Design: Reduces time spent on documentation by generating artifacts from the plan.",
    ),

    # TILE 3: DESIGN & BUILD GUIDANCE (SDLC: Implementation)
    ChatIntent(
        intent_id="design-build-guidance",
        title="Design & Build Guidance",
        group="SDLC Phase",
        description="Get coding suggestions, design patterns, and test scaffolding tailored to your project.",
        prefill_prompt="Time to build! As your **Pair Programmer**, I can accelerate a specific coding task. What specific feature (e.g., 'the user login component' or 'the API to save data') are you working on right now? Please mention the file name or component you need help with so I can provide the exact code or test scaffolding based on the approved design.",
        deliverables=["Code Block", "Unit Test File", "Refactoring Suggestions"],
        personas=["engineer"],
        guardrails=["quality-gate"],
        icon="🧑‍💻",
        requirement_area="Code Generation",
        core_functionality="Provides real-time, context-aware coding assistance and suggests best practices.",
        opnxt_benefit="Engineering Efficiency: Increases developer output while maintaining code quality.",
    ),

    # TILE 4: ENHANCE EXISTING DOCUMENTATION (SDLC: Maintenance)
    ChatIntent(
        intent_id="enhance-documentation",
        title="Enhance Existing Documentation",
        group="Maintenance",
        description="Review and refine your current documents without starting over.",
        prefill_prompt="Documentation is key to project health. I'm ready to review, refine, or update any existing document or code comment in your project. **Which file needs enhancement, and what is the specific change or improvement you want me to make (e.g., 'Add a risk analysis section,' or 'Simplify the explanation of the database schema')?**",
        deliverables=["File Refinement", "New Comments", "Section Addition"],
        personas=["pm", "engineer", "analyst"],
        guardrails=["enterprise-guardrails"],
        icon="📝",
        requirement_area="Quality Assurance",
        core_functionality="Analyzes existing files for clarity, completeness, and adherence to documentation standards.",
        opnxt_benefit="Process Consistency: Keeps all project documentation up-to-date and compliant with evolving standards.",
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
