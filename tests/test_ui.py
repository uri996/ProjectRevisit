from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from backend.services import application as application_module


@pytest.fixture
def ui(configured, monkeypatch):
    app, *_ = configured
    monkeypatch.setenv("PROJECT_RAG_DATA_DIR", app.data_path)
    st.cache_resource.clear()
    monkeypatch.setattr(application_module, "create_application", lambda: app)
    at = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "ui" / "app.py", default_timeout=20
    ).run()
    yield at, app
    st.cache_resource.clear()


def button(at, label):
    return next(x for x in at.button if x.label == label)


def test_ui_create_switch_index_chat_and_restore(ui):
    at, app = ui
    assert not at.exception and not at.error
    assert at.sidebar.title[0].value == "ProjectRevisit"
    at.text_input[0].set_value("示例项目 A")
    button(at, "创建项目").click().run()
    p = app.projects.list()[0]["id"]
    at.text_input[0].set_value("示例项目 B")
    button(at, "创建项目").click().run()
    q = app.projects.list()[1]["id"]
    assert len(at.selectbox[0].options) == 2
    app.documents.upload(p, "notes.md", "# 虚构图书目录\nCatalog 使用 CSV 保存图书条目。".encode())
    at.selectbox[0].set_value(p).run()
    at.switch_page("views/knowledge.py").run()
    assert not at.exception and not at.error
    assert at.get("file_uploader")
    assert "未索引" in str(at.dataframe[0].value)
    d = app.documents.list(p)[0]["id"]
    at.multiselect[0].set_value([d]).run()
    at.checkbox(key=f"index_consent_{p}").check().run()
    button(at, "建立索引 / 重新索引").click().run(timeout=30)
    assert not at.error
    assert app.documents.list(p)[0]["status"] == "completed"
    at.switch_page("views/chat.py").run()
    at.chat_input[0].set_value("Catalog 如何保存图书条目？").run(timeout=30)
    assert len(at.chat_message) == 2
    assert not at.exception and not at.error
    assert any("来源证据" in x.label for x in at.expander)
    at.selectbox[0].set_value(q).run()
    assert len(at.chat_message) == 0
    at.selectbox[0].set_value(p).run()
    assert len(at.chat_message) == 2
    # Actual second confirmation required by UI before clear.
    assert button(at, "确认清空").disabled
    at.checkbox(key=f"clear_{p}").check().run()
    button(at, "确认清空").click().run()
    assert len(at.chat_message) == 0
    assert app.documents.list(p)[0]["status"] == "completed"


def test_ui_settings_save_key_clear_and_explicit_test(ui):
    at, app = ui
    at.switch_page("views/settings.py").run()
    assert not at.error
    inputs = {x.label: x for x in at.text_input}
    inputs["LLM 模型 ID"].set_value("synthetic-llm")
    inputs["新的 API Key（留空保留当前目标地址的密钥）"].set_value("new-synthetic-key")
    next(c for c in at.checkbox if c.label.startswith("我已核对")).check()
    button(at, "保存设置").click().run()
    assert not at.exception and not at.error
    assert app.settings.load().llm_model == "synthetic-llm"
    assert at.text_input(key="new_api_key").value == ""
    assert button(at, "测试已保存配置的 API 连接").disabled
    next(c for c in at.checkbox if c.label.startswith("连接测试将")).check().run()
    button(at, "测试已保存配置的 API 连接").click().run()
    assert any("连接测试均成功" in x.value for x in at.success)


def test_ui_history_survives_invalid_settings(ui):
    at, app = ui
    p = app.projects.create("Offline")
    app.qa.ask(p, "离线问题")
    app.settings.path.write_text("invalid-json", encoding="utf-8")
    at.run()
    at.switch_page("views/chat.py").run()
    assert not at.exception and not at.error
    assert len(at.chat_message) == 2
    assert at.warning


def test_ui_private_path_requires_explicit_opt_in(ui):
    at, app = ui
    assert not at.exception and not at.error
    original_path = app.data_path
    assert not any(x.label == "本机数据与隐私" for x in at.sidebar.expander)
    assert not any(x.key == "show_full_data_path" for x in at.checkbox)
    assert not any(original_path in x.value for x in at.get("text"))
    assert not any(original_path in x.value for x in at.code)
    at.switch_page("views/settings.py").run()
    assert not any(original_path in x.value for x in at.code)
    assert not any("%LOCALAPPDATA%" in x.value for x in at.get("text"))
    at.checkbox(key="show_full_data_path").check().run()
    assert any(x.value == original_path for x in at.code)
    at.checkbox(key="show_full_data_path").uncheck().run()
    assert not any(original_path in x.value for x in at.code)
    assert app.data_path == original_path


def test_ui_switches_project_documents_retrieval_and_history(ui):
    at, app = ui
    first = app.projects.create("示例项目 A")
    second = app.projects.create("示例项目 B")
    for project_id, filename, content in (
        (first, "catalog.md", "# 虚构目录\nCatalog 使用 CSV 保存图书。"),
        (second, "tasks.md", "# 虚构清单\nTask 使用 localStorage 保存任务。"),
    ):
        uploaded = app.documents.upload(project_id, filename, content.encode())
        app.documents.index(project_id, uploaded["document_id"], confirmed=True)
    at.run()
    at.switch_page("views/knowledge.py").run()
    assert "catalog.md" in str(at.dataframe[0].value)
    assert "tasks.md" not in str(at.dataframe[0].value)
    at.switch_page("views/chat.py").run()
    at.chat_input[0].set_value("Catalog CSV 图书如何保存？").run()
    first_history = app.qa.history(first)
    assert all(c["source"] == "catalog.md" for c in first_history[-1]["citations"])
    at.selectbox[0].set_value(second).run()
    assert not at.chat_message
    at.switch_page("views/knowledge.py").run()
    assert "tasks.md" in str(at.dataframe[0].value)
    assert "catalog.md" not in str(at.dataframe[0].value)
    at.switch_page("views/chat.py").run()
    at.chat_input[0].set_value("Task localStorage 任务如何保存？").run()
    assert all(c["source"] == "tasks.md" for c in app.qa.history(second)[-1]["citations"])
    at.selectbox[0].set_value(first).run()
    assert len(at.chat_message) == 2
    assert app.qa.history(first) == first_history
    assert any("Catalog" in x.value for x in at.markdown)
    assert not any("localStorage" in x.value for x in at.markdown)


def test_ui_fresh_sessions_reset_selection_without_sharing_temporary_state(ui):
    at, app = ui
    first = app.projects.create("示例项目 A")
    second = app.projects.create("示例项目 B")
    at.run()
    assert at.selectbox[0].value == first
    at.selectbox[0].set_value(second).run()
    at.switch_page("views/settings.py").run()
    at.checkbox(key="show_full_data_path").check().run()
    other = AppTest.from_file(at._script_path, default_timeout=20).run()
    assert other.selectbox[0].value == first
    other.switch_page("views/settings.py").run()
    assert other.text_input(key="new_api_key").value == ""
    assert not other.checkbox(key="show_full_data_path").value
    assert at.selectbox[0].value == second
    assert at.checkbox(key="show_full_data_path").value
    at.run()
    assert at.selectbox[0].value == second


def test_ui_navigation_retains_project_and_evidence(ui):
    at, app = ui
    project_id = app.projects.create("示例项目 A")
    uploaded = app.documents.upload(
        project_id, "catalog.md", "# 图书目录\nCatalog 使用 CSV 保存图书条目。".encode()
    )
    app.documents.index(project_id, uploaded["document_id"], confirmed=True)
    app.qa.ask(project_id, "Catalog 图书如何保存？")
    before = app.qa.history(project_id)
    at.run()
    assert not at.radio
    for page in ("knowledge", "settings", "overview", "chat"):
        at.switch_page(f"views/{page}.py").run()
        assert not at.exception and not at.error
        assert at.selectbox[0].value == project_id
    assert len(at.chat_message) == 2
    answer = before[-1]
    for citation in answer["citations"]:
        assert any(citation["source"] in x.value for x in at.get("text"))
        assert any(citation["text"] == x.value for x in at.get("text"))
        assert not any(citation["chunk_id"] in x.value for x in at.caption)
    assert not any(answer["created_at"] in x.value for x in at.caption)
    at.checkbox(key=f"citation_ids_{answer['id']}").check().run()
    for citation in answer["citations"]:
        assert any(citation["chunk_id"] == x.value for x in at.code)
    assert app.qa.history(project_id) == before


def test_ui_empty_project_pages_are_guarded(ui):
    at, app = ui
    for page in ("overview", "knowledge", "chat"):
        at.switch_page(f"views/{page}.py").run()
        assert not at.exception and not at.error
        assert not at.chat_input and not at.get("file_uploader")
        assert any("先在左侧创建项目" in x.value for x in at.info)
    at.switch_page("views/settings.py").run()
    assert not at.exception and not at.error
    assert button(at, "保存设置")
    assert app.projects.list() == []


def test_ui_presets_work_without_key_and_click_uses_normal_insufficient_history(ui):
    at, app = ui
    app.settings.keys.values.clear()
    project = app.projects.create("示例项目 A")
    at.run().switch_page("views/chat.py").run()
    question = app.recommendations.presets("项目复盘")[0]
    assert button(at, question)
    assert not at.exception and not at.error
    assert app.recommendations.load(project) is None
    button(at, question).click().run()
    history = app.qa.history(project)
    assert history[0]["content"] == question
    assert history[-1]["status"] == "insufficient"
    assert "先手动建立" in history[-1]["content"]
    at.run()
    assert app.qa.history(project) == history
    at.chat_input[0].set_value("继续复盘虚构项目").run()
    assert len(app.qa.history(project)) == 4


def generate_ui_questions(at, project, description="虚构图书目录：Catalog 使用 CSV 保存图书。"):
    at.text_area(key=f"recommendation_description_{project}").set_value(description)
    at.text_input(key=f"recommendation_role_{project}").set_value("后端开发")
    at.checkbox(key=f"recommendation_consent_{project}").check()
    button(at, "生成 / 重新生成问题").click().run()


def test_ui_generated_questions_persist_without_repeat_calls_and_use_real_rag(ui):
    at, app = ui
    project = app.projects.create("示例项目 A")
    uploaded = app.documents.upload(project, "catalog.md", b"# Fictional Catalog\nCatalog CSV")
    app.documents.index(project, uploaded["document_id"], confirmed=True)
    calls = []
    original_factory = app.settings.provider_factory

    def factory(settings, key):
        provider = original_factory(settings, key)
        calls.append(provider)
        return provider

    app.settings.provider_factory = factory
    at.run().switch_page("views/chat.py").run()
    generate_ui_questions(at, project)
    saved = app.recommendations.load(project)
    assert not at.exception and not at.error
    assert len(calls) == 1 and calls[0].embedded == []
    assert app.qa.history(project) == []
    for page in ("knowledge", "overview", "chat"):
        at.switch_page(f"views/{page}.py").run()
    at.run()
    assert len(calls) == 1
    assert at.text_area(key=f"recommendation_description_{project}").value == saved["description"]
    fresh = AppTest.from_file(at._script_path, default_timeout=20).run()
    fresh.switch_page("views/chat.py").run()
    assert (
        fresh.text_area(key=f"recommendation_description_{project}").value == saved["description"]
    )
    assert len(calls) == 1
    question = saved["questions"][0]["question"]
    button(at, question).click().run()
    assert not at.exception and not at.error
    assert len(calls) == 2
    history = app.qa.history(project)
    assert len(history) == 2 and history[0]["content"] == question
    assert history[-1]["status"] == "completed"
    assert history[-1]["citations"]
    assert all(c["source"] == "catalog.md" for c in history[-1]["citations"])
    assert any("来源证据" in x.label for x in at.expander)
    at.chat_input[0].set_value("Catalog CSV 的后续问题").run()
    assert len(app.qa.history(project)) == 4


def test_ui_recommendations_and_description_follow_selected_project(ui):
    at, app = ui
    first, second = app.projects.create("示例项目 A"), app.projects.create("示例项目 B")
    at.run().switch_page("views/chat.py").run()
    generate_ui_questions(at, first)
    first_saved = app.recommendations.load(first)
    at.selectbox[0].set_value(second).run()
    assert at.text_area(key=f"recommendation_description_{second}").value == ""
    assert not any("已保存的个性化问题" in e.label for e in at.expander)
    generate_ui_questions(at, second, "虚构任务清单：Task 使用 localStorage 保存任务。")
    second_saved = app.recommendations.load(second)
    assert second_saved["description"] != first_saved["description"]
    button(at, app.recommendations.presets("项目复盘")[0]).click().run()
    assert len(app.qa.history(second)) == 2
    assert app.qa.history(first) == []
    at.selectbox[0].set_value(first).run()
    assert (
        at.text_area(key=f"recommendation_description_{first}").value == first_saved["description"]
    )
    assert not at.chat_message
    assert app.recommendations.load(first) == first_saved
    assert app.recommendations.load(second) == second_saved


def test_ui_recommendation_failure_and_corruption_do_not_break_chat(ui, monkeypatch):
    at, app = ui
    project = app.projects.create("示例项目 A")
    at.run().switch_page("views/chat.py").run()
    # Explicit consent is required even when the generation button is clicked.
    button(at, "生成 / 重新生成问题").click().run()
    assert any("确认发送" in w.value for w in at.warning)
    generate_ui_questions(at, project)
    saved = app.recommendations.load(project)
    app.settings.keys.values.clear()
    button(at, "生成 / 重新生成问题").click().run()
    assert any("API Key" in w.value for w in at.warning)
    assert app.recommendations.load(project) == saved
    app.qa.db.execute(
        "UPDATE question_recommendations SET questions=? WHERE project_id=?",
        ("invalid synthetic JSON", project),
    )
    at.run()
    assert any("无法读取" in w.value for w in at.warning)
    assert not at.exception and not at.error
    at.chat_input[0].set_value("离线复盘问题").run()
    assert len(app.qa.history(project)) == 2


def test_ui_switching_preset_direction_is_free_and_compact(ui):
    at, app = ui
    app.projects.create("示例项目 A")
    at.run().switch_page("views/chat.py").run()
    # Streamlit exposes segmented controls through button_group in AppTest.
    control = at.get("button_group")[0]
    control.set_value("面试准备").run()
    assert button(at, app.recommendations.presets("面试准备")[0])
    assert not any(b.label == app.recommendations.presets("面试准备")[-1] for b in at.button)
    project = app.projects.list()[0]["id"]
    at.checkbox(key=f"recommendation_all_{project}").check().run()
    assert button(at, app.recommendations.presets("面试准备")[-1])
    assert not at.chat_message
