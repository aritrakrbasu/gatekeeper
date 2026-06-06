"""Knowledge citation helpers for Copilot responses."""

from __future__ import annotations

from typing import List

from knowledge.resolver.models import KnowledgeContext, ResolvedAssertion


def format_citation(assertion: ResolvedAssertion) -> str:
    return f"[knowledge:{assertion.assertion_id}] {assertion.statement}"


def build_knowledge_citations(context: KnowledgeContext, *, limit: int = 5) -> List[str]:
    citations: List[str] = []
    for assertion_type in sorted(context.assertions_by_type.keys()):
        for item in context.assertions_by_type[assertion_type]:
            citations.append(format_citation(item))
            if len(citations) >= limit:
                return citations
    return citations


def format_citations_section(citations: List[str]) -> str:
    if not citations:
        return ""
    lines = ["Accepted repository knowledge cited:"]
    lines.extend(f"- {line}" for line in citations)
    return "\n".join(lines)
