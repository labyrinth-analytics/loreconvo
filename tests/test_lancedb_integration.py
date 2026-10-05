"""Exercise the hybrid index against the installed LanceDB engine."""

import datetime
import os
from uuid import UUID

import numpy as np
import pytest

from loreconvo.core.hybrid_search import LanceIndex


IDS = [str(UUID(int=value)) for value in range(1, 5)]
PROJECT = "team's workspace"


class LocalEmbedding:
    """Keep API tests offline with deterministic 384-dimensional vectors."""

    def embed(self, texts, batch_size=64):
        for text in texts:
            vector = np.zeros(384, dtype=np.float32)
            for word in text.lower().split():
                vector[sum(word.encode()) % len(vector)] += 1
            vector[0] = 1
            yield vector / np.linalg.norm(vector)


@pytest.fixture
def index(tmp_path):
    result = LanceIndex(tmp_path / "sessions.lance")
    result._model = LocalEmbedding()
    return result


def write(index, session_id=IDS[0], title="Database", summary="quartz storage", project=PROJECT):
    return index.index_session(
        session_id, title, summary, project, "code",
        datetime.datetime.now(datetime.timezone.utc).isoformat(), ["agent:builder"],
    )


def test_write_replace_reopen_and_delete(index):
    assert write(index)
    assert write(index, summary="opal replacement")
    table = index._open_table()
    assert table.count_rows() == 1
    row = table.search().to_list()[0]
    assert row["summary"] == "opal replacement"
    assert row["agent"] == "builder"
    assert len(row["vector"]) == 384
    assert index._lance_dir.stat().st_mode & 0o777 == 0o700

    reopened = LanceIndex(index._lance_dir)
    reopened._model = LocalEmbedding()
    assert reopened.is_available()
    assert reopened.search("opal", project=PROJECT) == [IDS[0]]
    reopened._open_table().delete(f"session_id = '{IDS[0]}'")
    assert not reopened.is_available()


def test_vector_and_full_text_retrieval_are_project_scoped(index):
    assert write(index)
    assert write(index, IDS[1], project="another workspace")
    table = index._open_table()
    rows = table.search("quartz", query_type="fts").where(
        "project = 'team''s workspace'"
    ).limit(20).to_list()
    assert [row["session_id"] for row in rows] == [IDS[0]]
    assert index.search("quartz", project=PROJECT) == [IDS[0]]
    assert index.search("quartz", project="absent' OR '1'='1") == []
    nearest = table.search(
        index._embed_one("Database quartz storage"),
        vector_column_name="vector", query_type="vector",
    ).limit(2).to_list()
    assert {row["session_id"] for row in nearest} == {IDS[0], IDS[1]}
    assert all(row["_distance"] == pytest.approx(0, abs=1e-6) for row in nearest)


def test_vector_lookup_enforces_ids_project_and_surface(index):
    assert write(index)
    assert write(index, IDS[1], project="another workspace")
    vectors = index.get_vectors_by_session_ids(IDS, project=PROJECT, surface="code")
    assert set(vectors) == {IDS[0]}
    assert len(vectors[IDS[0]]) == 384
    assert index.get_vectors_by_session_ids(IDS, surface="chat") == {}
    assert index.get_vectors_by_session_ids(["absent' OR '1'='1"]) == {}


def test_invalid_update_id_cannot_delete_existing_sessions(index):
    assert write(index)
    assert write(index, "absent' OR '1'='1")
    assert index._open_table().count_rows() == 1
    assert index.get_vectors_by_session_ids([IDS[0]])


def test_rebuild_replaces_rows_and_retains_scope_and_full_text(index):
    assert write(index)
    sessions = [
        {"id": session_id, "title": "Rebuild", "summary": "sapphire corpus",
         "project": PROJECT, "surface": "code", "start_date": "2026-01-01",
         "tags": ["agent:builder"], "source": source}
        for session_id, source in zip(IDS[1:], [None, "periodic", "file_memory"])
    ]
    assert index.rebuild(sessions) == 1
    assert index._open_table().count_rows() == 1
    assert index.search("sapphire", project=PROJECT) == [IDS[1]]
    assert [row["session_id"] for row in index._open_table().search(
        "sapphire", query_type="fts"
    ).to_list()] == [IDS[1]]
    assert set(index.get_vectors_by_session_ids(IDS)) == {IDS[1]}


@pytest.mark.skipif(
    not os.environ.get("LORECONVO_TEST_EMBEDDING_CACHE"),
    reason="set LORECONVO_TEST_EMBEDDING_CACHE to a predownloaded fastembed cache",
)
def test_fastembed_roundtrip(tmp_path):
    from fastembed import TextEmbedding

    index = LanceIndex(tmp_path / "sessions.lance")
    index._model = TextEmbedding(
        "BAAI/bge-small-en-v1.5",
        cache_dir=os.environ["LORECONVO_TEST_EMBEDDING_CACHE"],
        local_files_only=True,
    )
    assert write(index, summary="The database stores persistent conversation memories")
    assert index.search("persistent conversation memories", project=PROJECT) == [IDS[0]]
    vector = index.get_vectors_by_session_ids([IDS[0]])[IDS[0]]
    assert len(vector) == 384
    assert np.linalg.norm(vector) == pytest.approx(1, abs=1e-5)
