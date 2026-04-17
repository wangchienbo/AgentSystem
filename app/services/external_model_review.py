"""Compatibility shim for external model review.

Feature was planned but canceled (2026-04-17). This module provides
stub classes to keep existing imports working until the feature is
properly re-implemented or the references are fully removed.
"""
from __future__ import annotations


class ExternalModelReviewService:
    """Stub — feature not yet implemented."""
    def __init__(self, model_router=None):
        self._model_router = model_router


class ExternalModelReviewWorker:
    """Stub — feature not yet implemented."""
    def __init__(self, service: ExternalModelReviewService):
        self._service = service
