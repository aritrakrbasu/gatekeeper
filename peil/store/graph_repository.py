"""peil_decision_graphs repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from peil.config import get_aril_settings
from peil.graph.hashing import compute_graph_hash as _compute_graph_hash
from peil.logging import log_aril_event
from peil.models.enums import GraphEdgeRelation, GraphNodeType
from peil.models.graph import DecisionGraph, DecisionGraphCreate


class GraphRepository:
    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._settings = get_aril_settings()

    async def _database(self) -> Any:
        if self._db is not None:
            return self._db
        from services import mongo_client
        return await mongo_client.get_database()

    @property
    def _collection_name(self) -> str:
        return self._settings.collection_decision_graphs

    async def insert(self, data: DecisionGraphCreate) -> DecisionGraph:
        now = datetime.now(timezone.utc)
        metadata = data.metadata
        metadata.node_count = len(data.nodes)
        metadata.edge_count = len(data.edges)
        graph_hash = _compute_graph_hash(data)
        graph = DecisionGraph(
            graph_id=data.graph_id,
            execution_id=data.execution_id,
            task_id=data.task_id,
            repository_id=data.repository_id,
            nodes=data.nodes,
            edges=data.edges,
            metadata=metadata,
            graph_version=data.graph_version or self._settings.graph_version,
            builder_version=data.builder_version or self._settings.builder_version,
            schema_version=data.schema_version,
            graph_revision=metadata.graph_revision,
            status=data.status,
            graph_hash=graph_hash,
            created_at=now,
        )
        db = await self._database()
        await db[self._collection_name].insert_one(graph.to_mongo())
        log_aril_event(
            "graph_inserted",
            execution_id=graph.execution_id,
            task_id=graph.task_id,
            extra={
                "graph_id": graph.graph_id,
                "graph_revision": graph.graph_revision,
                "node_count": metadata.node_count,
            },
        )
        return graph

    async def get_by_graph_id(self, graph_id: str) -> Optional[DecisionGraph]:
        db = await self._database()
        doc = await db[self._collection_name].find_one({"graph_id": graph_id})
        if not doc:
            return None
        return _graph_from_mongo(doc)

    async def get_by_execution_id(
        self,
        execution_id: str,
        *,
        graph_revision: Optional[int] = None,
    ) -> Optional[DecisionGraph]:
        db = await self._database()
        collection = db[self._collection_name]
        if graph_revision is not None:
            doc = await collection.find_one(
                {"execution_id": execution_id, "graph_revision": graph_revision}
            )
        else:
            doc = await (
                collection.find({"execution_id": execution_id})
                .sort("graph_revision", -1)
                .limit(1)
                .to_list(length=1)
            )
            doc = doc[0] if doc else None
        if not doc:
            return None
        return _graph_from_mongo(doc)


def _graph_from_mongo(doc: dict) -> DecisionGraph:
    data = dict(doc)
    data.pop("_id", None)
    if isinstance(data.get("nodes"), list):
        nodes = []
        for node in data["nodes"]:
            if isinstance(node.get("type"), str):
                node = dict(node)
                node["type"] = GraphNodeType(node["type"])
            nodes.append(node)
        data["nodes"] = nodes
    if isinstance(data.get("edges"), list):
        edges = []
        for edge in data["edges"]:
            if isinstance(edge.get("relation"), str):
                edge = dict(edge)
                edge["relation"] = GraphEdgeRelation(edge["relation"])
            edges.append(edge)
        data["edges"] = edges
    return DecisionGraph.model_validate(data)
