"""Shared pytest fixtures for ARIL unit tests."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pytest

from knowledge.config import get_knowledge_settings
from peil.config import get_aril_settings


@dataclass
class _UpdateResult:
    matched_count: int = 0
    modified_count: int = 0
    acknowledged: bool = True


@dataclass
class _InsertManyResult:
    inserted_ids: List[Any] = field(default_factory=list)


@dataclass
class _InsertOneResult:
    inserted_id: Any = "fake-id"


class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        self._docs = docs
        self._sort_key: Optional[Tuple[str, int]] = None
        self._limit: Optional[int] = None
        self._skip: int = 0

    def sort(self, key: str, direction: int) -> "FakeCursor":
        self._sort_key = (key, direction)
        return self

    def limit(self, n: int) -> "FakeCursor":
        self._limit = n
        return self

    def skip(self, n: int) -> "FakeCursor":
        self._skip = max(0, n)
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        docs = list(self._docs)
        if self._sort_key:
            key, direction = self._sort_key
            docs.sort(key=lambda d: d.get(key), reverse=direction < 0)
        if self._skip:
            docs = docs[self._skip :]
        if self._limit is not None:
            docs = docs[: self._limit]
        if length is not None:
            docs = docs[:length]
        return [copy.deepcopy(d) for d in docs]


class FakeCollection:
    def __init__(self) -> None:
        self.docs: List[Dict[str, Any]] = []
        self.indexes: List[Dict[str, Any]] = []

    async def insert_one(self, document: Dict[str, Any]) -> _InsertOneResult:
        self.docs.append(copy.deepcopy(document))
        return _InsertOneResult(inserted_id=len(self.docs))

    async def insert_many(
        self, documents: List[Dict[str, Any]], ordered: bool = True
    ) -> _InsertManyResult:
        ids = []
        for doc in documents:
            self.docs.append(copy.deepcopy(doc))
            ids.append(len(self.docs))
        return _InsertManyResult(inserted_ids=ids)

    async def find_one(
        self,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        for doc in self.docs:
            if _matches(doc, filter):
                return copy.deepcopy(doc)
        return None

    def find(self, filter: Dict[str, Any]) -> FakeCursor:
        matched = [d for d in self.docs if _matches(d, filter)]
        return FakeCursor(matched)

    async def count_documents(self, filter: Dict[str, Any]) -> int:
        return sum(1 for d in self.docs if _matches(d, filter))

    async def update_one(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> _UpdateResult:
        for i, doc in enumerate(self.docs):
            if _matches(doc, filter):
                _apply_update(doc, update)
                return _UpdateResult(matched_count=1, modified_count=1)
        if upsert:
            new_doc = copy.deepcopy(filter)
            _apply_update(new_doc, update)
            self.docs.append(new_doc)
            return _UpdateResult(matched_count=0, modified_count=1)
        return _UpdateResult(matched_count=0, modified_count=0)

    async def update_many(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
    ) -> _UpdateResult:
        matched = 0
        for doc in self.docs:
            if _matches(doc, filter):
                _apply_update(doc, update)
                matched += 1
        return _UpdateResult(matched_count=matched, modified_count=matched)

    async def find_one_and_update(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        return_document: Any = None,
    ) -> Optional[Dict[str, Any]]:
        for doc in self.docs:
            if _matches(doc, filter):
                _apply_update(doc, update)
                return copy.deepcopy(doc)
        return None

    async def create_index(
        self, keys: List[Tuple[str, int]], unique: bool = False, name: str = ""
    ) -> str:
        self.indexes.append({"keys": keys, "unique": unique, "name": name})
        return name or "index"


class FakeDatabase:
    def __init__(self) -> None:
        self._collections: Dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]

    async def list_collection_names(self) -> List[str]:
        return list(self._collections.keys())


def _get_nested(doc: Dict[str, Any], dotted: str) -> Any:
    parts = dotted.split(".")
    value: Any = doc
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _matches(doc: Dict[str, Any], filter: Dict[str, Any]) -> bool:
    for key, expected in filter.items():
        actual = _get_nested(doc, key) if "." in key else doc.get(key)
        if isinstance(expected, dict) and "$ne" in expected:
            if actual == expected["$ne"]:
                return False
            if isinstance(actual, list) and expected["$ne"] in actual:
                return False
            continue
        if isinstance(expected, dict) and "$gt" in expected:
            if actual is None or not (actual > expected["$gt"]):
                return False
            continue
        if actual != expected:
            return False
    return True


def _apply_update(doc: Dict[str, Any], update: Dict[str, Any]) -> None:
    if "$setOnInsert" in update:
        for key, value in update["$setOnInsert"].items():
            if key not in doc:
                doc[key] = value
    if "$set" in update:
        for key, value in update["$set"].items():
            if "." in key:
                parts = key.split(".")
                target = doc
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = value
            else:
                doc[key] = value
    if "$addToSet" in update:
        for key, value in update["$addToSet"].items():
            existing = doc.setdefault(key, [])
            if value not in existing:
                existing.append(value)
    if "$inc" in update:
        for key, delta in update["$inc"].items():
            doc[key] = doc.get(key, 0) + delta
    if "$push" in update:
        for key, value in update["$push"].items():
            doc.setdefault(key, []).append(value)


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture(autouse=True)
def _clear_aril_settings_cache() -> None:
    get_aril_settings.cache_clear()
    get_knowledge_settings.cache_clear()
    yield
    get_aril_settings.cache_clear()
    get_knowledge_settings.cache_clear()
