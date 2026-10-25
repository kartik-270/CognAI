"""
CognAI Backend Brain: SLM Rephrase Detector Bridge (Node 3)
============================================================
Bridges the cross-encoder semantic paraphrase detector into production runtime.
Provides < 5ms CPU Local Runtime cross-attention evaluation across user turns.
"""

import os
import sys
import logging
from typing import Optional, Tuple

logger = logging.getLogger("SLMRephraseBridge")

_REPHRASE_INSTANCE = None
_REPHRASE_INIT_FAILED = False

def get_slm_rephrase_detector():
    """
    Returns the singleton instance of RephraseDetector.
    Loads trained weights from backend/training/weights/rephrase_detector.
    """
    global _REPHRASE_INSTANCE, _REPHRASE_INIT_FAILED

    if _REPHRASE_INIT_FAILED:
        return None

    if _REPHRASE_INSTANCE is not None:
        return _REPHRASE_INSTANCE

    try:
        import importlib
        try:
            rephrase_module = importlib.import_module("training.03_rephrase_detector")
        except ModuleNotFoundError:
            rephrase_module = importlib.import_module("backend.training.03_rephrase_detector")
        RephraseDetector = getattr(rephrase_module, "RephraseDetector")

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        weights_path = os.path.join(base_dir, "training", "weights", "rephrase_detector")
        if not os.path.exists(weights_path):
            alt_path = os.path.join(base_dir, "backend", "training", "weights", "rephrase_detector")
            if os.path.exists(alt_path):
                weights_path = alt_path

        logger.info(f"Initializing SLM Rephrase Detector from {weights_path}...")
        _REPHRASE_INSTANCE = RephraseDetector(model_path=weights_path if os.path.exists(weights_path) else None)
        logger.info("SLM Rephrase Detector successfully loaded into memory.")
        return _REPHRASE_INSTANCE
    except Exception as e:
        logger.warning(f"Could not initialize SLM Rephrase Detector: {e}")
        _REPHRASE_INIT_FAILED = True
        return None
