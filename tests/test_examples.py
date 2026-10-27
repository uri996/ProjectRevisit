from pathlib import Path


def test_fictional_examples_index_retrieve_and_chat_independently(configured):
    app, *_ = configured
    root = Path(__file__).resolve().parents[1]
    cases = [
        ("示例项目 A", "demo_project_alpha.md", "CSV 图书如何保存？"),
        ("示例项目 B", "demo_project_beta.md", "localStorage 任务如何保存？"),
    ]
    project_ids = []
    for name, filename, question in cases:
        project_id = app.projects.create(name)
        project_ids.append(project_id)
        uploaded = app.documents.upload(
            project_id, filename, (root / "examples" / filename).read_bytes()
        )
        assert app.documents.list(project_id)[0]["status"] == "unindexed"
        app.documents.index(project_id, uploaded["document_id"], confirmed=True)
        answer = app.qa.ask(project_id, question)
        assert answer["status"] == "completed"
        assert answer["citations"]
        assert all(c["source"] == filename for c in answer["citations"])
        assert all(c["document_id"] == uploaded["document_id"] for c in answer["citations"])
    for project_id in project_ids:
        assert len(app.qa.history(project_id)) == 2
