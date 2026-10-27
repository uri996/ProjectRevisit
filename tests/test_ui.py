from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from backend.services import application as application_module


@pytest.fixture
def ui(configured, monkeypatch):
    app, *_ = configured
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
    at.radio[0].set_value("知识库管理").run()
    assert not at.exception and not at.error
    assert at.get("file_uploader")
    assert "未索引" in str(at.dataframe[0].value)
    d = app.documents.list(p)[0]["id"]
    at.multiselect[0].set_value([d]).run()
    at.checkbox[0].check().run()
    button(at, "建立索引 / 重新索引").click().run(timeout=30)
    assert not at.error
    assert app.documents.list(p)[0]["status"] == "completed"
    at.radio[0].set_value("智能问答").run()
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
    at.checkbox[0].check().run()
    button(at, "确认清空").click().run()
    assert len(at.chat_message) == 0
    assert app.documents.list(p)[0]["status"] == "completed"


def test_ui_settings_save_key_clear_and_explicit_test(ui):
    at, app = ui
    at.radio[0].set_value("AI 设置").run()
    assert not at.error
    inputs = {x.label: x for x in at.text_input}
    inputs["LLM 模型 ID"].set_value("synthetic-llm")
    inputs["新的 API Key（留空保留当前目标地址的密钥）"].set_value("new-synthetic-key")
    at.checkbox[0].check()
    button(at, "保存设置").click().run()
    assert not at.exception and not at.error
    assert app.settings.load().llm_model == "synthetic-llm"
    assert at.text_input(key="new_api_key").value == ""
    assert button(at, "测试已保存配置的 API 连接").disabled
    at.checkbox[1].check().run()
    button(at, "测试已保存配置的 API 连接").click().run()
    assert any("连接测试均成功" in x.value for x in at.success)


def test_ui_history_survives_invalid_settings(ui):
    at, app = ui
    p = app.projects.create("Offline")
    app.qa.ask(p, "离线问题")
    app.settings.path.write_text("invalid-json", encoding="utf-8")
    at.run()
    at.radio[0].set_value("智能问答").run()
    assert not at.exception and not at.error
    assert len(at.chat_message) == 2
    assert at.warning
