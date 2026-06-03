import datetime
import re
import math
import hashlib
import random
import asyncio
from typing import Dict, Any, List, Optional
from services import mongo_client

class MemoryStore:
    """
    Manages in-memory log caching and trace persistence to MongoDB 'agent_execution_traces',
    and provides semantic memory storage and retrieval using hybrid similarity/recency scoring.
    """
    def __init__(self, task_id: Optional[str] = None, objective: Optional[str] = None):
        self.task_id = task_id
        self.objective = objective
        self.status = "running"
        self.steps: List[Dict[str, Any]] = []
        self.messages: List[Dict[str, Any]] = []
        self.created_at = datetime.datetime.utcnow().isoformat()
        
    def add_step(self, step_id: str, tool_name: str, arguments: Dict[str, Any], status: str = "pending", result: Any = None, error: Optional[str] = None):
        """Record or update planning/execution step details."""
        # Find if step already exists, if so update it, else append
        for step in self.steps:
            if step["step_id"] == step_id:
                step.update({
                    "status": status,
                    "result": str(result) if result is not None else None,
                    "error": error,
                    "updated_at": datetime.datetime.utcnow().isoformat()
                })
                return
                
        self.steps.append({
            "step_id": step_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "status": status,
            "result": str(result) if result is not None else None,
            "error": error,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat()
        })
        
    def log_message(self, role: str, content: str):
        """Log LLM developer messages or planning interactions."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        
    async def persist_to_mongodb(self):
        """Flushes execution trace and log state to 'agent_execution_traces'."""
        if not self.task_id:
            return
            
        trace_doc = {
            "task_id": self.task_id,
            "objective": self.objective,
            "status": self.status,
            "steps": self.steps,
            "messages": self.messages,
            "created_at": self.created_at,
            "last_updated_at": datetime.datetime.utcnow().isoformat()
        }
        
        try:
            # Check if trace already exists
            existing = await mongo_client.find_one("agent_execution_traces", {"task_id": self.task_id})
            if existing:
                db = await mongo_client.get_database()
                await db["agent_execution_traces"].update_one(
                    {"task_id": self.task_id},
                    {"$set": trace_doc}
                )
                print(f"[OK] Persisted updated trace logs to DB for {self.task_id}")
            else:
                await mongo_client.insert_one("agent_execution_traces", trace_doc)
                print(f"[OK] Persisted new trace logs to DB for {self.task_id}")
        except Exception as e:
            print(f"[WARN] Failed to persist trace to MongoDB: {e}")

    # =========================================================================
    # Semantic Memory API Implementation
    # =========================================================================

    def sanitize_text(self, text: str) -> str:
        """Sanitizes text by masking sensitive credentials, API keys, and secrets."""
        if not text:
            return ""
        # Mask gitlab tokens
        text = re.sub(r'glpat-[a-zA-Z0-9_\-]{20,}', '[MASKED_GITLAB_TOKEN]', text)
        # Mask gemini api keys
        text = re.sub(r'AIzaSy[a-zA-Z0-9_\-]{33}', '[MASKED_GEMINI_KEY]', text)
        # Mask passwords in key-value pairs
        text = re.sub(r'(password|pass|passwd|secret|token|key|credential|jwt)(?:\s*[:=]\s*|\s*=\s*)(["\'])[^\'\n]+?\2', r'\1: "[MASKED]"', text, flags=re.IGNORECASE)
        # Mask mongodb connection strings
        text = re.sub(r'mongodb(?:\+srv)?://[^\s\n]+', 'mongodb+srv://[MASKED_USER]:[MASKED_PWD]@[MASKED_HOST]', text)
        # Mask Bearer tokens
        text = re.sub(r'bearer\s+[a-zA-Z0-9_\-\.]+', 'Bearer [MASKED_BEARER_TOKEN]', text, flags=re.IGNORECASE)
        return text

    def _generate_deterministic_embedding(self, text: str, dimension: int = 768) -> List[float]:
        """Generates a unit-normalized deterministic embedding vector based on hash of text."""
        seed_hash = hashlib.sha256(text.encode('utf-8')).digest()
        seed = int.from_bytes(seed_hash[:4], byteorder='big')
        rng = random.Random(seed)
        
        vec = [rng.gauss(0, 1) for _ in range(dimension)]
        magnitude = math.sqrt(sum(x*x for x in vec))
        if magnitude > 0:
            vec = [x / magnitude for x in vec]
        return vec

    async def _get_embedding(self, text: str) -> List[float]:
        """Requests real Gemini embeddings with automatic fallback to deterministic dummy."""
        try:
            from services.gemini_service import ai_client
            # Wrap the sync SDK call in asyncio.to_thread
            response = await asyncio.to_thread(
                ai_client.models.embed_content,
                model="models/gemini-embedding-2",
                contents=text
            )
            return response.embeddings[0].values
        except Exception as e:
            # Fallback to deterministic vector if Gemini call fails (e.g. 403 Permission Denied)
            return self._generate_deterministic_embedding(text)

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Calculates cosine similarity between two float vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(v1, v2))
        mag1 = math.sqrt(sum(a * a for a in v1))
        mag2 = math.sqrt(sum(b * b for b in v2))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot_product / (mag1 * mag2)

    async def add_memory(self, collection_name: str, text: str, metadata: dict) -> str:
        """Sanitizes, generates embedding for, and stores a document in agent_memory_collections."""
        sanitized_text = self.sanitize_text(text)
        embedding = await self._get_embedding(sanitized_text)
        
        doc = {
            "collection_name": collection_name,
            "text": sanitized_text,
            "embedding": embedding,
            "metadata": metadata or {},
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        inserted_id = await mongo_client.insert_one("agent_memory_collections", doc)
        return inserted_id

    async def search_memories(
        self,
        collection_name: str,
        query: str,
        metadata_filter: Optional[dict] = None,
        limit: int = 5,
        recency_weight: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Performs hybrid vector/metadata search over cached agent memory with time decay."""
        # 1. Fetch matching documents from MongoDB applying metadata filters
        mongo_filter = {"collection_name": collection_name}
        if metadata_filter:
            for k, v in metadata_filter.items():
                mongo_filter[f"metadata.{k}"] = v
                
        docs = await mongo_client.find("agent_memory_collections", mongo_filter)
        if not docs:
            return []
            
        # 2. Embed the query
        query_embedding = await self._get_embedding(query)
        
        # 3. Calculate cosine similarity and decay time scoring
        scored_docs = []
        now = datetime.datetime.utcnow()
        
        for doc in docs:
            doc_embedding = doc.get("embedding")
            if not doc_embedding:
                doc_embedding = await self._get_embedding(doc.get("text", ""))
                
            similarity = self._cosine_similarity(query_embedding, doc_embedding)
            
            created_at_str = doc.get("created_at")
            if created_at_str:
                try:
                    # Parse ISO format, replacing trailing Z for compatibility
                    clean_date = created_at_str.replace("Z", "+00:00")
                    created_at = datetime.datetime.fromisoformat(clean_date).replace(tzinfo=None)
                except Exception:
                    created_at = now
            else:
                created_at = now
                
            age_days = (now - created_at).total_seconds() / 86400.0
            # Recency scoring with exponential decay lambda = 0.05
            recency = math.exp(-0.05 * age_days)
            
            # Hybrid combined score
            combined = (1.0 - recency_weight) * similarity + recency_weight * recency
            
            scored_docs.append({
                "document": doc,
                "similarity": similarity,
                "recency_score": recency,
                "confidence_score": similarity,
                "combined_score": combined
            })
            
        # 4. Sort descending and apply limit
        scored_docs.sort(key=lambda x: x["combined_score"], reverse=True)
        
        results = []
        for item in scored_docs[:limit]:
            doc_data = item["document"]
            doc_id = str(doc_data.get("_id", ""))
            
            results.append({
                "id": doc_id,
                "text": doc_data.get("text"),
                "metadata": doc_data.get("metadata"),
                "created_at": doc_data.get("created_at"),
                "similarity": item["similarity"],
                "recency_score": item["recency_score"],
                "confidence_score": item["confidence_score"],
                "combined_score": item["combined_score"]
            })
            
        return results

    async def find_similar_incidents(self, query: str, metadata_filter: Optional[dict] = None, limit: int = 5, recency_weight: float = 0.3) -> List[dict]:
        return await self.search_memories("incidents", query, metadata_filter, limit, recency_weight)

    async def find_similar_reviews(self, query: str, metadata_filter: Optional[dict] = None, limit: int = 5, recency_weight: float = 0.3) -> List[dict]:
        return await self.search_memories("reviews", query, metadata_filter, limit, recency_weight)

    async def find_similar_fixes(self, query: str, metadata_filter: Optional[dict] = None, limit: int = 5, recency_weight: float = 0.3) -> List[dict]:
        return await self.search_memories("remediations", query, metadata_filter, limit, recency_weight)

    async def find_related_deployments(self, query: str, metadata_filter: Optional[dict] = None, limit: int = 5, recency_weight: float = 0.3) -> List[dict]:
        return await self.search_memories("deployments", query, metadata_filter, limit, recency_weight)
