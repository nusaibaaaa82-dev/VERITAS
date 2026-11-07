"""VERITAS pipeline services: verification, evidence retrieval, and verdict engine."""

from backend.services.evidence_retrieval import EvidenceRetrievalService
from backend.services.verdict_engine import VerdictEngine
from backend.services.verification import VerificationPipeline

__all__ = [
    "EvidenceRetrievalService",
    "VerdictEngine",
    "VerificationPipeline",
]

