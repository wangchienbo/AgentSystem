"""Temporary compatibility shim for external model review.

Kept only because runtime bootstrap still imports it.
Do not extend this module or add new callers.
"""
from __future__ import annotations


class ExternalModelReviewService:
    def __init__(self, model_router=None):
        self._model_router = model_router


class ExternalModelReviewWorker:
    def __init__(self, service: ExternalModelReviewService):
        self._service = service
