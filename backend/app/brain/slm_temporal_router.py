"""
CognAI Backend Brain: SLM Temporal Router Bridge (Node 2)
==========================================================
Bridges the fine-tuned Seq2Seq SLM (google/flan-t5-small + LoRA)
into the production runtime with singleton memory management.
"""

import os
import sys
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger("SLMTemporalRouterBridge")

_ROUTER_INSTANCE = None
_ROUTER_INIT_FAILED = False


def get_slm_temporal_router():
    """
    Returns the singleton instance of TemporalIntentRouter.
    Loads trained weights from backend/training/weights/temporal_router.
    """
    global _ROUTER_INSTANCE, _ROUTER_INIT_FAILED

    if _ROUTER_INIT_FAILED:
        return None

    if _ROUTER_INSTANCE is not None:
        return _ROUTER_INSTANCE

    try:
        import importlib
        router_module = importlib.import_module("backend.training.02_temporal_intent_router")
        TemporalIntentRouter = getattr(router_module, "TemporalIntentRouter")
        
        weights_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "training",
            "weights",
            "temporal_router"
        )
        
        logger.info(f"Initializing SLM Temporal Router from {weights_path}...")
        _ROUTER_INSTANCE = TemporalIntentRouter(model_path=weights_path)
        logger.info("SLM Temporal Router successfully loaded into memory.")
        return _ROUTER_INSTANCE
    except Exception as e:
        logger.warning(f"Could not initialize SLM Temporal Router: {e}")
        _ROUTER_INIT_FAILED = True
        return None
