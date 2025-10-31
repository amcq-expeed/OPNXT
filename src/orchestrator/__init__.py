# Orchestrator package init
# --- opnxt-stream ---
import logging
import os


# --- opnxt-stream ---
def _configure_logging() -> None:
    level_name = (os.getenv("OPNXT_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger = logging.getLogger("opnxt")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[OPNXT][%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)

    llm_level_name = (os.getenv("OPNXT_LLM_LOG_LEVEL") or level_name).upper()
    llm_level = getattr(logging, llm_level_name, level)
    logging.getLogger("opnxt.llm").setLevel(llm_level)


# --- opnxt-stream ---
_configure_logging()
