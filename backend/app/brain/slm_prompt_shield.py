"""
CognAI Backend Brain: SLM Prompt Injection Shield Bridge (Node 1)
==================================================================
Bridges the fine-tuned adversarial prompt injection classifier into production runtime.
Provides < 5ms CPU Local Runtime filtering before executing LLM generation.
"""

import os
import sys
import logging
from typing import Optional, Tuple

logger = logging.getLogger("SLMPromptShieldBridge")

_SHIELD_INSTANCE = None
_SHIELD_INIT_FAILED = False

def get_slm_prompt_shield():
    """
    Returns the singleton instance of PromptShieldDetector.
    Loads trained weights from backend/training/weights/prompt_shield.
    """
    global _SHIELD_INSTANCE, _SHIELD_INIT_FAILED

    if _SHIELD_INIT_FAILED:
        return None

    if _SHIELD_INSTANCE is not None:
        return _SHIELD_INSTANCE

    try:
        import importlib
        try:
            shield_module = importlib.import_module("training.01_prompt_injection_shield")
        except ModuleNotFoundError:
            shield_module = importlib.import_module("backend.training.01_prompt_injection_shield")
        PromptShieldDetector = getattr(shield_module, "PromptShieldDetector")

        # Check weights path in /app/training/weights or backend/training/weights
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        weights_path = os.path.join(base_dir, "training", "weights", "prompt_shield")
        if not os.path.exists(weights_path):
            alt_path = os.path.join(base_dir, "backend", "training", "weights", "prompt_shield")
            if os.path.exists(alt_path):
                weights_path = alt_path

        logger.info(f"Initializing SLM Prompt Shield from {weights_path}...")
        _SHIELD_INSTANCE = PromptShieldDetector(model_path=weights_path if os.path.exists(weights_path) else None)
        logger.info("SLM Prompt Shield successfully loaded into memory.")
        return _SHIELD_INSTANCE
    except Exception as e:
        logger.warning(f"Could not initialize SLM Prompt Shield: {e}")
        _SHIELD_INIT_FAILED = True
        return None
