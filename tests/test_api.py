import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_api


@pytest.fixture
def client(configured):
    app, *_ = configured
    with TestClient(
        create_api(app),
        base_url="http://127.0.0.1:8765",
        headers={"Origin": "http://127.0.0.1:8765"},
    ) as client:
        yield client, app


def operation(**fields):
    return {"request_id": str(uuid4()), "confirmed": True, **fields}


def create(client, name="示例项目 A"):
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def upload(client, project):
    response = client.post(
        f"/api/projects/{project}/documents",
        files={"file": ("catalog.md", b"# Fictional Catalog\nCatalog CSV", "text/markdown")},
    )
    assert response.status_code == 200
    return response.json()["document_id"]


def test_api_complete_workflow_isolation_and_persistence(client, configured, tmp_path):
    client, app = client
    first, second = create(client), create(client, "示例项目 B")
    doc = upload(client, first)
    assert client.get(f"/api/projects/{first}/documents").json()[0]["status"] == "unindexed"
    assert client.get(f"/api/projects/{second}/documents").json() == []
    assert (
        client.post(f"/api/projects/{second}/documents/{doc}/index", json=operation()).status_code
        == 400
    )
    result = client.post(f"/api/projects/{first}/documents/{doc}/index", json=operation())
    assert result.status_code == 200 and result.json()["status"] == "completed"
    assert "path" not in client.get(f"/api/projects/{first}/documents").json()[0]
    question = operation(question="Catalog CSV 如何保存？")
    result = client.post(f"/api/projects/{first}/questions", json=question)
    assert result.status_code == 200
    assert result.json()["citations"][0]["source"] == "catalog.md"
    assert result.json()["citations"][0]["reference"] == 1
    assert result.json()["citations"][0]["supporting_quotes"]
    assert client.post(f"/api/projects/{first}/questions", json=question).status_code == 409
    assert len(client.get(f"/api/projects/{first}/messages").json()) == 2
    assert client.get(f"/api/projects/{second}/messages").json() == []
    generated = client.post(
        f"/api/projects/{first}/recommendations",
        json=operation(description="虚构图书目录，Catalog 使用 CSV。", target_role="后端开发"),
    )
    assert generated.status_code == 200
    assert len(generated.json()["questions"]) == 6
    assert client.get(f"/api/projects/{second}/recommendations").json() is None
    assert client.get(f"/api/projects/{first}/recommendations").json() == generated.json()
    assert len(app.qa.history(first)) == 2
    # Reopening the same synthetic data space preserves old IDs, chats, and recommendations.
    from backend.services.application import create_application

    _, _, keys, factory = configured
    reopened = create_application(tmp_path, keys, factory)
    assert reopened.recommendations.load(first)["questions"] == generated.json()["questions"]
    assert len(reopened.qa.history(first)) == 2
    assert (
        reopened.documents.list(first)[0]["collection"]
        == app.documents.list(first)[0]["collection"]
    )
    assert (
        client.request(
            "DELETE", f"/api/projects/{first}/messages", json=operation(confirmed=False)
        ).status_code
        == 400
    )


def test_api_validation_consent_and_offline_presets(client, configured):
    client, app = client
    _, providers, keys, _ = configured
    project = create(client)
    keys.values.clear()
    assert len(client.get("/api/recommendations/presets").json()["项目复盘"]) == 6
    assert (
        client.post(
            f"/api/projects/{project}/questions",
            json=operation(question="离线问题", confirmed=False),
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/projects/{project}/questions", json=operation(question="离线问题")
        ).json()["status"]
        == "insufficient"
    )
    assert (
        client.post(
            f"/api/projects/{project}/recommendations",
            json=operation(description="虚构目录", target_role="后端"),
        ).status_code
        == 400
    )
    assert client.post("/api/projects", json={"name": " "}).status_code == 422
    assert client.get("/api/projects/not-a-uuid/messages").status_code == 422
    assert (
        client.post(f"/api/projects/{project}/questions", json=operation(question="")).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/projects/{project}/documents", files={"file": ("../notes.md", b"hello")}
        ).status_code
        == 400
    )
    assert not providers
    assert len(app.qa.history(project)) == 2


def test_api_settings_never_return_or_echo_keys(client):
    client, app = client
    settings = client.get("/api/settings").json()
    assert "api_key" not in settings
    response = client.put(
        "/api/settings",
        json={
            "settings": settings["settings"],
            "api_key": "synthetic-api-secret",
            "confirmed": True,
        },
    )
    assert response.status_code == 200 and "synthetic-api-secret" not in response.text
    bad = client.put(
        "/api/settings", json={"settings": {}, "api_key": "synthetic-api-secret", "confirmed": True}
    )
    assert bad.status_code == 422 and "synthetic-api-secret" not in bad.text
    assert client.post("/api/settings/test", json=operation()).status_code == 200
    assert app.data_path not in client.get("/api/settings").text
    assert client.get("/api/settings/data-location").json() == {"path": app.data_path}


def test_api_rejects_foreign_hosts_origins_and_large_requests(client):
    client, _ = client
    assert client.get("/api/projects", headers={"host": "evil.example"}).status_code == 400
    assert (
        client.get("/api/projects", headers={"origin": "https://evil.example"}).status_code == 403
    )
    assert client.get("/api/projects", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert (
        client.post("/api/projects", json={"name": "Test"}, headers={"origin": "null"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/projects", content=b"{}", headers={"content-length": str(13 * 1024 * 1024)}
        ).status_code
        == 413
    )
    response = client.options(
        "/api/projects",
        headers={"origin": "https://evil.example", "access-control-request-method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers
    streamed = client.post(
        "/api/projects",
        content=iter([b'{"name":"', b"x" * (13 * 1024 * 1024), b'"}']),
        headers={"content-type": "application/json"},
    )
    assert streamed.status_code == 413


def test_api_concurrent_project_operations_are_rejected_and_failures_sanitized(client, monkeypatch):
    client, app = client
    project = create(client)
    started, release = threading.Event(), threading.Event()
    original = app.qa.ask

    def slow(*args):
        started.set()
        assert release.wait(10)
        return original(*args)

    monkeypatch.setattr(app.qa, "ask", slow)
    request = operation(question="离线问题")
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(client.post, f"/api/projects/{project}/questions", json=request)
        assert started.wait(5)
        try:
            assert (
                client.post(f"/api/projects/{project}/questions", json=request).status_code == 409
            )
            assert (
                client.post(
                    f"/api/projects/{project}/questions", json=operation(question="另一个问题")
                ).status_code
                == 409
            )
        finally:
            release.set()
        assert pending.result().status_code == 200

    def fail(*args):
        raise RuntimeError("synthetic-private-key-and-content")

    monkeypatch.setattr(app.qa, "ask", fail)
    failed = client.post(f"/api/projects/{project}/questions", json=operation(question="失败问题"))
    assert failed.status_code == 500 and "synthetic-private" not in failed.text


def test_spa_history_fallback_and_missing_assets(configured, tmp_path):
    app, *_ = configured
    dist = tmp_path / "synthetic-dist"
    dist.mkdir()
    (dist / "index.html").write_text("<title>ProjectRevisit</title>", encoding="utf-8")
    with TestClient(create_api(app, frontend=dist), base_url="http://127.0.0.1:8765") as client:
        assert "ProjectRevisit" in client.get("/chat").text
        assert client.get("/missing.js").status_code == 404
        assert client.get("/api/unknown").status_code == 404


def test_settings_can_be_repaired_without_implicitly_overwriting_invalid_config(client):
    client, app = client
    app.settings.path.write_text("invalid synthetic JSON", encoding="utf-8")
    view = client.get("/api/settings")
    assert view.status_code == 200 and view.json()["warning"]
    assert app.settings.path.read_text(encoding="utf-8") == "invalid synthetic JSON"
    assert (
        client.put(
            "/api/settings", json={"settings": view.json()["settings"], "confirmed": True}
        ).status_code
        == 200
    )
    assert client.get("/api/settings").json()["warning"] is None

def test_optional_recommendations_and_bad_settings_do_not_block_history(client, configured):
    client, app = client
    _, _, keys, _ = configured
    project = create(client)
    keys.values.clear()
    asked = client.post(
        f"/api/projects/{project}/questions", json=operation(question="虚构离线复盘问题")
    )
    assert asked.status_code == 200
    saved = client.get(f"/api/projects/{project}/messages").json()
    app.qa.db.save_recommendations(project, "虚构目录", "后端开发", [])
    app.qa.db.execute(
        "UPDATE question_recommendations SET questions=? WHERE project_id=?",
        ("synthetic invalid JSON", project),
    )
    app.settings.path.write_text("synthetic invalid JSON", encoding="utf-8")
    assert client.get(f"/api/projects/{project}/recommendations").status_code == 400
    assert client.get(f"/api/projects/{project}/messages").json() == saved
    assert client.get(f"/api/projects/{project}/documents").status_code == 200
    assert client.get("/api/settings").json()["warning"]
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/recommendations/presets").status_code == 200
