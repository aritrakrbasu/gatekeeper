from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.graph.builder import GraphBuilder
from peil.graph.hashing import compute_graph_hash


def test_hash_changes_with_graph_version():
    execution = mr_review_execution("exec-hash-1")
    events = mr_review_capture_events("exec-hash-1")
    base = GraphBuilder().build_from_events(events, execution)

    bumped = GraphBuilder(graph_version=99).build_from_events(events, execution)
    assert compute_graph_hash(base) != compute_graph_hash(bumped)


def test_hash_stable_for_same_input():
    execution = mr_review_execution("exec-hash-2")
    events = mr_review_capture_events("exec-hash-2")
    g = GraphBuilder().build_from_events(events, execution)
    assert compute_graph_hash(g) == compute_graph_hash(g)
