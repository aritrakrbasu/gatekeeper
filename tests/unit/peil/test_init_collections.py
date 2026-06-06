import pytest

from peil.store.init_collections import initialize_aril_collections


@pytest.mark.asyncio
async def test_initialize_aril_collections(fake_db):
    summary = await initialize_aril_collections(fake_db)
    assert "indexes" in summary
    assert "collections_present" in summary
    assert summary["gridfs_bucket"] == "peil_evidence"
    assert summary["graph_version"] >= 1
