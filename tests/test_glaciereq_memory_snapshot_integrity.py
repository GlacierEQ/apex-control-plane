import copy
import pytest
from src.glaciereq_memory_snapshot_integrity import graph_digest, verify_graph_digest


def test_canonical_digest_ignores_key_order():
    a = [{'metadata': {'node_key': 'APEX', 'parent_key': 'ROOT'}, 'source_id': 'x'}]
    b = [{'source_id': 'x', 'metadata': {'parent_key': 'ROOT', 'node_key': 'APEX'}}]
    assert graph_digest(a) == graph_digest(b)
    assert verify_graph_digest(b, graph_digest(a)) == graph_digest(a)


def test_reject_modified_cursor():
    a = [{'metadata': {'next_transition': 'safe'}}]
    b = copy.deepcopy(a)
    b[0]['metadata']['next_transition'] = 'unsafe'
    with pytest.raises(ValueError, match='mismatch'):
        verify_graph_digest(b, graph_digest(a))


def test_reject_modified_source_id():
    a = [{'source_id': 'source-a'}]
    with pytest.raises(ValueError, match='mismatch'):
        verify_graph_digest([{'source_id': 'source-b'}], graph_digest(a))


@pytest.mark.parametrize('bad', ['', '0'*63, 'G'*64, None, '0'*65])
def test_bad_digest_fails_closed(bad):
    with pytest.raises(ValueError, match='SHA-256'):
        verify_graph_digest([], bad)


def test_reject_non_list_and_nonfinite():
    with pytest.raises(ValueError):
        graph_digest({'rows': []})
    with pytest.raises(ValueError):
        graph_digest([float('nan')])
