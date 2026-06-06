"""Durable evidence store — inline blobs collection + GridFS for large payloads."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from peil.config import get_aril_settings
from peil.logging import log_aril_event

INLINE_PREFIX = "inline:"
GRIDFS_PREFIX = "gridfs:"


class EvidenceRepository:
    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._settings = get_aril_settings()
        self._inline_cache: Dict[str, bytes] = {}

    async def _database(self) -> Any:
        if self._db is not None:
            return self._db
        from services import mongo_client
        return await mongo_client.get_database()

    def _bucket(self, db: Any) -> AsyncIOMotorGridFSBucket:
        return AsyncIOMotorGridFSBucket(
            db, bucket_name=self._settings.evidence_gridfs_bucket
        )

    @property
    def _blobs_collection_name(self) -> str:
        return self._settings.collection_evidence_blobs

    async def store(
        self,
        *,
        execution_id: str,
        payload: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        content_hash = hashlib.sha256(payload).hexdigest()
        meta = {"execution_id": execution_id, "content_hash": content_hash}
        if metadata:
            meta.update(metadata)

        if len(payload) <= self._settings.evidence_inline_max_bytes:
            ref = f"{INLINE_PREFIX}{content_hash}"
            await self._persist_inline_blob(
                content_hash=content_hash,
                execution_id=execution_id,
                payload=payload,
                content_type=content_type,
                metadata=meta,
            )
            self._inline_cache[ref] = payload
            log_aril_event(
                "evidence_stored_inline",
                execution_id=execution_id,
                extra={"ref": ref, "bytes": len(payload)},
            )
            return ref

        db = await self._database()
        existing = await self._find_gridfs_by_hash(db, content_hash)
        if existing is not None:
            ref = f"{GRIDFS_PREFIX}{existing}"
            log_aril_event(
                "evidence_dedup_hit",
                execution_id=execution_id,
                extra={"ref": ref, "content_hash": content_hash},
            )
            return ref

        bucket = self._bucket(db)
        file_id = await bucket.upload_from_stream(
            filename=f"{execution_id}/{content_hash[:16]}",
            source=payload,
            metadata=meta,
        )
        ref = f"{GRIDFS_PREFIX}{file_id}"
        log_aril_event(
            "evidence_stored_gridfs",
            execution_id=execution_id,
            extra={"ref": ref, "bytes": len(payload)},
        )
        return ref

    async def resolve(self, ref: str, *, max_chars: Optional[int] = None) -> str:
        payload: Optional[bytes] = None

        if ref.startswith(INLINE_PREFIX):
            payload = self._inline_cache.get(ref)
            if payload is None:
                content_hash = ref[len(INLINE_PREFIX) :]
                payload = await self._load_inline_blob(content_hash)
        elif ref.startswith(GRIDFS_PREFIX):
            file_id_str = ref[len(GRIDFS_PREFIX) :]
            payload = await self._load_gridfs_blob(file_id_str)

        if payload is None:
            return ""

        text = payload.decode("utf-8", errors="replace")
        if max_chars is not None and len(text) > max_chars:
            return text[:max_chars] + "…"
        return text

    async def _persist_inline_blob(
        self,
        *,
        content_hash: str,
        execution_id: str,
        payload: bytes,
        content_type: str,
        metadata: Dict[str, Any],
    ) -> None:
        db = await self._database()
        collection = db[self._blobs_collection_name]
        await collection.update_one(
            {"content_hash": content_hash},
            {
                "$set": {
                    "content_hash": content_hash,
                    "execution_id": execution_id,
                    "payload": payload,
                    "content_type": content_type,
                    "metadata": metadata,
                    "updated_at": datetime.now(timezone.utc),
                },
                "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )

    async def _load_inline_blob(self, content_hash: str) -> Optional[bytes]:
        db = await self._database()
        doc = await db[self._blobs_collection_name].find_one(
            {"content_hash": content_hash}
        )
        if not doc:
            return None
        raw = doc.get("payload")
        if isinstance(raw, bytes):
            return raw
        if isinstance(raw, str):
            return raw.encode("utf-8")
        return None

    async def _load_gridfs_blob(self, file_id_str: str) -> Optional[bytes]:
        db = await self._database()
        files_collection = db[f"{self._settings.evidence_gridfs_bucket}.files"]
        doc = await files_collection.find_one({"_id": file_id_str})
        if doc is None:
            from bson import ObjectId

            try:
                doc = await files_collection.find_one({"_id": ObjectId(file_id_str)})
            except Exception:
                doc = None
        if doc and "payload" in doc:
            raw = doc["payload"]
            return raw if isinstance(raw, bytes) else str(raw).encode("utf-8")

        bucket = self._bucket(db)
        from bson import ObjectId

        try:
            oid = ObjectId(file_id_str)
        except Exception:
            return None
        try:
            stream = await bucket.open_download_stream(oid)
            return await stream.read()
        except Exception:
            return None

    async def _find_gridfs_by_hash(self, db: Any, content_hash: str) -> Optional[str]:
        files_collection = db[f"{self._settings.evidence_gridfs_bucket}.files"]
        doc = await files_collection.find_one({"metadata.content_hash": content_hash})
        if doc:
            return str(doc["_id"])
        return None
