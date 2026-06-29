from pathlib import Path


def test_relative_chroma_path_resolves_from_project_root():
    from app.rag.vector_store.client import resolve_chroma_persist_dir

    expected = Path(__file__).resolve().parents[1] / "data" / "chroma_db"

    assert resolve_chroma_persist_dir("./data/chroma_db") == expected
    assert resolve_chroma_persist_dir("data/chroma_db") == expected
