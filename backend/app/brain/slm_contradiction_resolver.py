"""
CognAI Backend Brain: SLM Contradiction Resolver Bridge (Node 8)
================================================================
Bridges the NLI sequence classification SLM into production memory consolidation.
Provides < 5ms CPU Local Runtime memory conflict resolution before permanent store commits.
"""

import os
import sys
import logging
from typing import Optional, Tuple

logger = logging.getLogger("SLMContradictionBridge")

_CONTRADICTION_INSTANCE = None
_CONTRADICTION_INIT_FAILED = False

def get_slm_contradiction_resolver():
    """
    Returns the singleton instance of ContradictionResolverSLM.
    Loads trained weights from backend/training/weights/contradiction_resolver.
    """
    global _CONTRADICTION_INSTANCE, _CONTRADICTION_INIT_FAILED

    if _CONTRADICTION_INIT_FAILED:
        return None

    if _CONTRADICTION_INSTANCE is not None:
        return _CONTRADICTION_INSTANCE

    try:
        import importlib
        try:
            resolver_module = importlib.import_module("training.08_contradiction_resolver")
        except ModuleNotFoundError:
            resolver_module = importlib.import_module("backend.training.08_contradiction_resolver")
        ContradictionResolverSLM = getattr(resolver_module, "ContradictionResolverSLM")

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        weights_path = os.path.join(base_dir, "training", "weights", "contradiction_resolver")
        if not os.path.exists(weights_path):
            alt_path = os.path.join(base_dir, "backend", "training", "weights", "contradiction_resolver")
            if os.path.exists(alt_path):
                weights_path = alt_path

        logger.info(f"Initializing SLM Contradiction Resolver from {weights_path}...")
        _CONTRADICTION_INSTANCE = ContradictionResolverSLM(model_path=weights_path if os.path.exists(weights_path) else None)
        logger.info("SLM Contradiction Resolver successfully loaded into memory.")
        return _CONTRADICTION_INSTANCE
    except Exception as e:
        logger.warning(f"Could not initialize SLM Contradiction Resolver: {e}")
        _CONTRADICTION_INIT_FAILED = True
        return None
