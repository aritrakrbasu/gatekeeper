"""Propose repository knowledge assertions from replay-backed copilot state."""

from __future__ import annotations

from typing import Any, List

from copilot.models.state import CopilotState
from knowledge.proposal import propose_from_copilot_state
from knowledge.store.assertion_repository import AssertionRepository


async def knowledge_proposal_node(state: CopilotState, *, db: Any = None) -> dict:
    """
    Persist proposed assertions. Status remains ``proposed`` — never auto-accepted.
    """
    proposals = propose_from_copilot_state(state)
    if not proposals:
        return {"proposed_count": 0, "assertion_ids": []}

    repo = AssertionRepository(db)
    assertion_ids: List[str] = []
    for proposal in proposals:
        assertion = await repo.propose(proposal, proposed_by_user_id=state.user_id)
        assertion_ids.append(assertion.assertion_id)

    state.proposed_assertion_ids = assertion_ids
    return {"proposed_count": len(assertion_ids), "assertion_ids": assertion_ids}
