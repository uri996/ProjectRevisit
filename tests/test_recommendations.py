import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from backend.models import AppError
from backend.services.application import create_application
from backend.services.locking import project_lock
from backend.services.recommendation_service import validate_questions

DESCRIPTION = "示例项目 A：虚构图书目录，使用 Python 和 CSV 保存图书，目录编号必须唯一。"


def generate(app, project_id, description=DESCRIPTION, role="后端开发"):
    return app.recommendations.generate(project_id, description, role, confirmed=True)


def mock_output(app, factory, output=None, error=None):
    def replacement(settings, key):
        provider = factory(settings, key)

        def complete(system, payload):
            if error:
                raise error
            return copy.deepcopy(output)

        provider.complete = complete
        return provider

    app.settings.provider_factory = replacement


def test_presets_need_no_key_no_provider_and_no_saved_data(configured):
    app, providers, keys, _ = configured
    keys.values.clear()
    project = app.projects.create("示例项目 A")
    assert len(app.recommendations.presets("项目复盘")) == 6
    assert len(app.recommendations.presets("面试准备")) == 5
    assert app.recommendations.load(project) is None
    assert app.qa.history(project) == []
    assert not providers


def test_generation_uses_only_visible_input_current_llm_and_no_embeddings(configured):
    app, providers, *_ = configured
    project = app.projects.create("示例项目 A")
    app.settings.save(replace(app.settings.load(), llm_model="synthetic-current-llm"))
    saved = generate(app, project)
    assert 5 <= len(saved["questions"]) <= 10
    assert saved["description"] == DESCRIPTION
    assert saved["target_role"] == "后端开发"
    assert saved["updated_at"].endswith("+00:00")
    assert providers[-1].settings.llm_model == "synthetic-current-llm"
    assert providers[-1].payloads == [
        {"project_description": DESCRIPTION, "target_role": "后端开发"}
    ]
    assert providers[-1].embedded == []
    assert app.qa.history(project) == []
    assert app.documents.list(project) == []


def test_persistence_regeneration_and_project_isolation(configured, tmp_path):
    app, providers, keys, factory = configured
    first, second = app.projects.create("示例项目 A"), app.projects.create("示例项目 B")
    saved = generate(app, first)
    second_saved = generate(
        app, second, "虚构任务清单，使用 JavaScript 保存演示任务。", "AI 产品经理"
    )
    restarted = create_application(tmp_path, keys, factory)
    assert restarted.recommendations.load(first) == saved
    assert restarted.recommendations.load(second) == second_saved
    assert len(providers) == 2
    updated = generate(restarted, first, DESCRIPTION + "新增虚构的分类校验。")
    assert updated["description"] != saved["description"]
    assert restarted.recommendations.load(second) == second_saved
    assert restarted.qa.history(first) == restarted.qa.history(second) == []


def test_generation_failure_is_redacted_and_keeps_previous_result(configured):
    app, providers, _, factory = configured
    project = app.projects.create("示例项目 A")
    previous = generate(app, project)
    mock_output(app, factory, error=RuntimeError("synthetic-sensitive-provider-content"))
    with pytest.raises(AppError) as error:
        generate(app, project, "新的虚构描述")
    assert "synthetic-sensitive" not in str(error.value)
    assert "上次结果已保留" in str(error.value)
    assert app.recommendations.load(project) == previous
    assert not providers[-1].embedded


@pytest.mark.parametrize(
    "case",
    ["wrong_root", "short", "long", "extra", "answer", "empty", "type", "oversize", "duplicate"],
)
def test_invalid_structured_results_never_replace_saved_questions(configured, case):
    app, providers, _, factory = configured
    project = app.projects.create("示例项目 A")
    previous = generate(app, project)
    output = {"questions": copy.deepcopy(previous["questions"])}
    if case == "wrong_root":
        output = []
    elif case == "short":
        output["questions"] = output["questions"][:4]
    elif case == "long":
        output["questions"] *= 2
    elif case == "extra":
        output["answers"] = []
    elif case == "answer":
        output["questions"][0]["answer"] = "不允许生成答案"
    elif case == "empty":
        output["questions"][0]["reason"] = " "
    elif case == "type":
        output["questions"][0]["direction"] = 42
    elif case == "oversize":
        output["questions"][0]["question"] = "字" * 301
    elif case == "duplicate":
        output["questions"][1]["question"] = output["questions"][0]["question"] + "？ "
    mock_output(app, factory, output)
    with pytest.raises(AppError, match="格式无效"):
        generate(app, project)
    assert app.recommendations.load(project) == previous
    assert not providers[-1].embedded


@pytest.mark.parametrize(
    "description,role",
    [
        ("", "后端"),
        ("字" * 8001, "后端"),
        (None, "后端"),
        (DESCRIPTION, ""),
        (DESCRIPTION, "字" * 101),
    ],
    ids=["empty-description", "long-description", "invalid-description", "empty-role", "long-role"],
)
def test_invalid_input_never_calls_provider(configured, description, role):
    app, providers, *_ = configured
    project = app.projects.create("示例项目 A")
    with pytest.raises(AppError):
        generate(app, project, description, role)
    assert not providers


def test_consent_key_project_validation_and_lock(configured):
    app, providers, keys, _ = configured
    project = app.projects.create("示例项目 A")
    with pytest.raises(AppError, match="确认"):
        app.recommendations.generate(project, DESCRIPTION, "后端开发")
    with pytest.raises(AppError, match="标识"):
        generate(app, "../invalid")
    with pytest.raises(AppError, match="标识"):
        app.recommendations.load("../invalid")
    with project_lock(Path(app.data_path), project):
        with pytest.raises(AppError, match="正在处理"):
            generate(app, project)
    keys.values.clear()
    with pytest.raises(AppError, match="API Key"):
        generate(app, project)
    assert not providers


def test_additive_schema_upgrade_preserves_history_documents_and_vectors(configured, tmp_path):
    app, _, keys, factory = configured
    project = app.projects.create("示例项目 A")
    uploaded = app.documents.upload(project, "catalog.md", b"# Fictional catalog\nCatalog CSV")
    app.documents.index(project, uploaded["document_id"], confirmed=True)
    app.qa.ask(project, "Catalog CSV")
    db = app.qa.db
    snapshots = {
        table: db.query(f"SELECT * FROM {table}") for table in ("projects", "documents", "messages")
    }
    document = app.documents.list(project)[0]
    original_bytes = app.documents.files.read(document["path"])
    vector_ids = app.documents.vectors._open(document["collection"]).get()["ids"]
    # Simulate the pre-feature schema in this synthetic temporary database only.
    db.execute("DROP TABLE question_recommendations")
    upgraded = create_application(tmp_path, keys, factory)
    assert upgraded.recommendations.load(project) is None
    for table, rows in snapshots.items():
        assert upgraded.qa.db.query(f"SELECT * FROM {table}") == rows
    generate(upgraded, project)
    assert upgraded.documents.files.read(document["path"]) == original_bytes
    assert upgraded.documents.vectors._open(document["collection"]).get()["ids"] == vector_ids
    for table, rows in snapshots.items():
        assert upgraded.qa.db.query(f"SELECT * FROM {table}") == rows


def test_corrupt_saved_questions_raise_safe_error_without_touching_chat(configured):
    app, *_ = configured
    project = app.projects.create("示例项目 A")
    generate(app, project)
    app.qa.db.execute(
        "UPDATE question_recommendations SET questions=? WHERE project_id=?",
        ("invalid synthetic JSON", project),
    )
    with pytest.raises(AppError, match="无法读取"):
        app.recommendations.load(project)
    assert app.qa.history(project) == []
    assert generate(app, project)["questions"]


def test_question_schema_accepts_only_structured_questions():
    rows = [
        {"question": f"虚构问题 {i}？", "direction": "验证", "reason": "虚构说明"} for i in range(5)
    ]
    assert (
        json.loads(json.dumps(validate_questions({"questions": rows}), ensure_ascii=False)) == rows
    )
