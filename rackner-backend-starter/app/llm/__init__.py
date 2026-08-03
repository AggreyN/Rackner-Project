"""LLM gateway package.

Public surface (import from here, not the submodules):
    extract_obligations(chunk_text, *, source_text=None) -> list[Obligation-shaped dict]
    analyze(opportunity, lifecycle_profile, *, source_text=None) -> Analysis-shaped dict

The gateway routes to Amazon Bedrock (Claude) when LLM_MODE=bedrock, else to a
deterministic mock (LLM_MODE=mock, the default). Either way the backend runs the
no-hallucination check and returns objects matching /SCHEMA.md exactly.
"""

from app.llm.gateway import analyze, extract_obligations

__all__ = ["analyze", "extract_obligations"]
