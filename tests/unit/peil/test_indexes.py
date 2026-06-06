from peil.config import get_aril_settings
from peil.store.indexes import ensure_aril_indexes, get_aril_index_specs


def test_index_specs_include_subjects_and_graph_versions():
    settings = get_aril_settings()
    specs = get_aril_index_specs()
    collections = {s[0] for s in specs}
    assert settings.collection_subjects in collections
    assert settings.collection_decision_graphs in collections

    graph_specs = [s for s in specs if s[0] == settings.collection_decision_graphs]
    names = {s[3].get("name") for s in graph_specs}
    assert "uniq_execution_graph_revision" in names
    assert "idx_graph_outcome_nodes" in names


async def test_ensure_aril_indexes_on_fake_db(fake_db):
    summary = await ensure_aril_indexes(fake_db)
    settings = get_aril_settings()
    assert settings.collection_capture_events in summary
    assert summary[settings.collection_capture_events] >= 4
    assert settings.collection_evidence_blobs in summary
