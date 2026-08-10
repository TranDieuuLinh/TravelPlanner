"""Controlled, provenance-aware place tagging."""

from app.modules.knowledge_graph.tagging.classifier import TagEvidence, classify_place
from app.modules.knowledge_graph.tagging.service import PlaceTaggingService

__all__ = ["PlaceTaggingService", "TagEvidence", "classify_place"]
