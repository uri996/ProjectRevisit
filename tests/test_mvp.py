import json
import subprocess
import sys
from dataclasses import replace
from uuid import uuid4

import pytest

from backend.models import AISettings, AppError
from backend.rag.chunker import split_document
from backend.services.application import create_application
from backend.services.locking import project_lock
from backend.services.settings_service import SecureKeys
from backend.storage.files import MAX_BYTES


def upload_index(
    app, project, name="notes.md", text="# 虚构图书目录\nCatalog 使用 CSV 保存图书条目。"
):
    result = app.documents.upload(project, name, text.encode())
    app.documents.index(project, result["document_id"], confirmed=True)
    return result["document_id"]


def test_projects_unique_restart_and_no_api(configured, tmp_path):
    app, providers, keys, factory = configured
    a, b = app.projects.create("示例项目 A"), app.projects.create("示例项目 A")
    assert a != b
    restarted = create_application(tmp_path, keys, factory)
    assert [p["id"] for p in restarted.projects.list()] == [a, b]
    assert providers == []


def test_upload_manual_consent_and_duplicate(configured):
    app, providers, *_ = configured
    p = app.projects.create("示例项目 A")
    doc = app.documents.upload(p, "中文.md", "# 中文\r\n项目说明".encode())
    assert app.documents.list(p)[0]["status"] == "unindexed"
    assert providers == []
    assert (
        app.documents.upload(p, "重复.txt", "# 中文\r\n项目说明".encode())["action"] == "duplicate"
    )
    with pytest.raises(AppError):
        app.documents.index(p, doc["document_id"])
    assert providers == []
    app.documents.index(p, doc["document_id"], confirmed=True)
    assert app.documents.list(p)[0]["status"] == "completed"


@pytest.mark.parametrize(
    "name,data",
    [
        ("../evil.md", b"hi"),
        ("C:\\evil.md", b"hi"),
        ("a.pdf", b"hi"),
        ("empty.txt", b" \n"),
        ("invalid.txt", b"\xff"),
        ("binary.md", b"a\x00b"),
        ("large.md", b"x" * (MAX_BYTES + 1)),
        ("bad\n.md", b"hi"),
    ],
    ids=[
        "traversal",
        "absolute",
        "extension",
        "empty",
        "encoding",
        "binary",
        "oversized",
        "control",
    ],
)
def test_invalid_upload(configured, name, data):
    app, providers, *_ = configured
    p = app.projects.create("Test")
    with pytest.raises(AppError):
        app.documents.upload(p, name, data)
    assert app.documents.list(p) == []
    assert providers == []


def test_chunk_metadata_chinese_headers():
    p, d = str(uuid4()), str(uuid4())
    chunks = split_document(
        "# 目录说明\n## 编号检查\n" + "目录编号必须唯一。" * 200,
        p,
        d,
        "中文.md",
        AISettings(chunk_size=200, chunk_overlap=30),
        "generation",
    )
    assert len(chunks) > 1
    assert all(len(c.page_content) <= 200 for c in chunks)
    for chunk in chunks:
        assert chunk.metadata["project_id"] == p
        assert chunk.metadata["document_id"] == d
        assert chunk.metadata["source"] == "中文.md"
        assert "编号检查" in chunk.metadata["heading"]
        assert chunk.metadata["chunk_id"].startswith(d)


def test_real_chroma_isolation_citations_and_restart(configured, tmp_path):
    app, providers, keys, factory = configured
    p, q = app.projects.create("示例项目 A"), app.projects.create("示例项目 B")
    d = upload_index(app, p)
    upload_index(app, q, "task_notes.md", "# 虚构任务清单\nTask 使用 localStorage 保存任务。")
    before = len(providers)
    answer = app.qa.ask(p, "Catalog 使用什么保存图书？")
    assert len(providers) == before + 1
    assert answer["status"] == "completed"
    assert all(c["document_id"] == d and c["source"] == "notes.md" for c in answer["citations"])
    assert all("虚构任务清单" not in c["text"] for c in answer["citations"])
    original = app.qa.history(p)
    restarted = create_application(tmp_path, keys, factory)
    assert restarted.qa.history(p) == original
    assert restarted.qa.history(q) == []
    assert restarted.documents.list(p)[0]["status"] == "completed"
    assert restarted.qa.ask(p, "Catalog？")["citations"]
    assert not restarted.qa.history(q)
    # Separate interpreter confirms on-disk Chroma persistence, not just client caching.
    collection = restarted.documents.list(p)[0]["collection"]
    code = (
        "import chromadb,sys; from chromadb.config import Settings; "
        "c=chromadb.PersistentClient(path=sys.argv[1],settings=Settings(anonymized_telemetry=False)); "
        "assert c.get_collection(sys.argv[2]).count()>0; print('persistent')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "chroma"), collection],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "persistent" in result.stdout


def test_update_replaces_generation_and_no_old_chunks(configured):
    app, *_ = configured
    p = app.projects.create("Test")
    d = upload_index(app, p, text="# 虚构目录\nCatalog old_marker")
    old = app.documents.list(p)[0]["collection"]
    result = app.documents.upload(p, "notes.md", b"# Fictional catalog\nCatalog new_marker")
    assert result == dict(document_id=d, action="updated")
    assert app.documents.list(p)[0]["status"] == "needs_reindex"
    assert app.qa.ask(p, "catalog")["status"] == "insufficient"
    app.documents.index(p, d, confirmed=True)
    assert app.documents.list(p)[0]["collection"] != old
    answer = app.qa.ask(p, "catalog")
    assert all("old_marker" not in c["text"] for c in answer["citations"])
    assert any("new_marker" in c["text"] for c in answer["citations"])


def test_failed_index_preserves_files_and_other_project(configured, monkeypatch):
    app, providers, *_ = configured
    p, q = app.projects.create("A"), app.projects.create("B")
    d = upload_index(app, p)
    upload_index(app, q)
    original_stage = app.documents.vectors.stage

    def fail(*args):
        raise RuntimeError("private-data-must-not-leak")

    monkeypatch.setattr(app.documents.vectors, "stage", fail)
    with pytest.raises(AppError) as error:
        app.documents.index(p, d, confirmed=True)
    assert "private-data" not in str(error.value)
    row = app.documents.list(p)[0]
    assert row["status"] == "failed"
    assert app.documents.files.read(row["path"])
    monkeypatch.setattr(app.documents.vectors, "stage", original_stage)
    assert app.qa.ask(q, "Catalog")["status"] == "completed"
    assert app.qa.ask(p, "Catalog")["status"] == "insufficient"


def test_partial_stage_never_becomes_active(configured, monkeypatch):
    app, providers, *_ = configured
    p = app.projects.create("A")
    d = upload_index(app, p)
    old = app.documents.list(p)[0]["collection"]
    from langchain_chroma import Chroma

    real_add = Chroma.add_documents
    calls = []

    def partial(self, documents, **kwargs):
        real_add(self, documents[:1], ids=kwargs["ids"][:1])
        calls.append(True)
        raise RuntimeError("simulated interrupted batch")

    monkeypatch.setattr(Chroma, "add_documents", partial)
    with pytest.raises(AppError):
        app.documents.index(p, d, confirmed=True)
    row = app.documents.list(p)[0]
    assert calls and row["collection"] == old and row["status"] == "failed"
    assert app.documents.vectors._open(old).get()["ids"]


def test_configuration_compatibility_and_no_silent_switch(configured):
    app, providers, *_ = configured
    p = app.projects.create("A")
    upload_index(app, p)
    original = app.settings.load()
    app.settings.save(replace(original, llm_model="another-llm"))
    assert app.documents.list(p)[0]["status"] == "completed"
    app.settings.save(replace(original, dimensions=512))
    row = app.documents.list(p)[0]
    assert row["status"] == "needs_reindex"
    assert json.loads(row["index_config"])["dimensions"] == 1024
    assert app.documents.vectors._open(row["collection"]).get()["ids"]
    count = len(providers)
    assert app.qa.ask(p, "Catalog")["status"] == "insufficient"
    assert len(providers) == count
    app.documents.index(p, row["id"], confirmed=True)
    assert app.qa.ask(p, "Catalog")["status"] == "completed"
    with pytest.raises(AppError, match="新加坡"):
        app.settings.save(
            replace(original, base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        )
    assert app.settings.load().dimensions == 512


def test_history_bounded_isolated_clear_and_not_embedded(configured, monkeypatch):
    app, providers, *_ = configured
    p, q = app.projects.create("A"), app.projects.create("B")
    upload_index(app, p)
    upload_index(app, q)
    app.settings.save(replace(app.settings.load(), history_messages=2, history_chars=100))
    app.qa.ask(q, "beta-context-marker Catalog")
    app.qa.ask(p, "Catalog 是什么？")
    app.qa.ask(p, "那里面的编号检查呢？")
    latest = providers[-1]
    payload = latest.payloads[-1]
    assert len(payload["history"]) <= 2
    assert sum(len(x["content"]) for x in payload["history"]) <= 100
    assert "Catalog" in latest.embedded[0]
    assert "示例回答" not in latest.embedded[0]
    assert "beta-context-marker" not in json.dumps(payload, ensure_ascii=False)
    before_count = app.documents.list(p)[0]["chunk_count"]
    assert before_count > 0
    with pytest.raises(AppError):
        app.qa.clear(p)
    app.qa.clear(p, confirmed=True)
    assert app.qa.history(p) == []
    assert len(app.qa.history(q)) == 2
    assert app.documents.list(p)[0]["chunk_count"] == before_count


def test_llm_fault_and_insufficient_and_invented_citations(configured):
    app, providers, keys, factory = configured
    p = app.projects.create("A")
    upload_index(app, p)
    for flag in ("supported", "fail_llm", "invent_citation"):

        def custom(settings, key, mode=flag):
            provider = factory(settings, key)
            setattr(provider, mode, mode != "supported")
            return provider

        app.settings.provider_factory = custom
        if flag == "supported":
            result = app.qa.ask(p, "为何选择 CSV？")
            assert result["status"] == "insufficient"
            assert "资料不足" in result["answer"]
            assert result["citations"]
        else:
            with pytest.raises(AppError):
                app.qa.ask(p, "Catalog")
            last = app.qa.history(p)[-1]
            assert last["status"] == "failed"
            assert "secret-from-provider" not in last["content"]
        assert app.projects.list()


def test_no_results_skips_llm(configured):
    app, providers, *_ = configured
    p = app.projects.create("A")
    upload_index(app, p)
    app.settings.save(replace(app.settings.load(), max_distance=0.0))
    answer = app.qa.ask(p, "completely unrelated topic")
    assert answer["status"] == "insufficient"
    assert answer["citations"] == []
    assert providers[-1].payloads == []


def test_no_settings_key_or_optional_api_at_start(tmp_path):
    app = create_application(tmp_path)
    p = app.projects.create("Offline")
    app.documents.upload(p, "offline.txt", b"No API required.")
    assert app.projects.list()
    assert app.qa.history(p) == []
    assert app.qa.ask(p, "Question")["status"] == "insufficient"


def test_key_not_in_config_and_os_failure(configured, monkeypatch):
    app, *_ = configured
    text = app.settings.path.read_text(encoding="utf-8")
    assert "synthetic-key-for-offline-tests" not in text
    assert "api_key" not in text.lower()
    secure = SecureKeys()
    import keyring

    monkeypatch.setattr(keyring, "get_keyring", lambda: object())
    with pytest.raises(AppError):
        secure.set("synthetic", "must-not-be-written")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "https://user:secret@example.com/v1",
        "https://example.com/v1?key=secret",
        "https://{WorkspaceId}.example.com/v1",
    ],
)
def test_invalid_endpoints(url):
    with pytest.raises(AppError):
        replace(AISettings(), base_url=url).validate()


def test_data_path_guard_and_backend_architecture(monkeypatch):
    from backend.config import REPO_ROOT, data_directory

    monkeypatch.setenv("PROJECT_RAG_DATA_DIR", str(REPO_ROOT / "private"))
    with pytest.raises(AppError):
        data_directory()
    monkeypatch.delenv("PROJECT_RAG_DATA_DIR")
    assert REPO_ROOT not in data_directory().parents
    for path in (REPO_ROOT / "backend").rglob("*.py"):
        assert "import streamlit" not in path.read_text(encoding="utf-8")


def test_scope_validation_interrupted_state_and_lock(configured):
    app, *_ = configured
    p, q = app.projects.create("A"), app.projects.create("B")
    d = upload_index(app, p)
    with pytest.raises(AppError):
        app.documents.index(q, d, confirmed=True)
    with pytest.raises(AppError):
        app.documents.upload("../escape", "a.txt", b"text")
    with project_lock(app.documents.root, p):
        with pytest.raises(AppError, match="正在处理"):
            app.documents.upload(p, "a.txt", b"text")
    app.documents.db.execute("UPDATE documents SET status='processing' WHERE id=?", (d,))
    assert app.documents.list(p)[0]["status"] == "failed"


def test_explicit_connection_test_synthetic_only(configured):
    app, providers, *_ = configured
    with pytest.raises(AppError):
        app.settings.test_connection()
    assert not providers
    assert "成功" in app.settings.test_connection(confirmed=True)
    assert len(providers[-1].embedded) == 1
    assert providers[-1].payloads == [{"test": "Synthetic connection test"}]
