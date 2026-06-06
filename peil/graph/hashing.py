"""Canonical graph hashing for idempotent rebuilds."""

from __future__ import annotations

import hashlib
import json

from peil.models.graph import DecisionGraphCreate


def compute_graph_hash(data: DecisionGraphCreate) -> str:
    canonical = {
        "execution_id": data.execution_id,
        "graph_version": data.graph_version,
        "builder_version": data.builder_version,
        "graph_revision": data.metadata.graph_revision,
        "nodes": [n.model_dump(mode="json") for n in data.nodes],
        "edges": [e.model_dump(mode="json") for e in data.edges],
        "metadata": {
            "root_node_ids": data.metadata.root_node_ids,
            "terminal_node_ids": data.metadata.terminal_node_ids,
            "outcome_node_ids": data.metadata.outcome_node_ids,
        },
    }
    raw = json.dumps(canonical, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
