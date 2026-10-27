import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from backend.models import AISettings, AppError
from ui.context import application
from ui.presentation import format_message_time, short_chunk_id

STATUS = {
    "unindexed": "未索引",
    "processing": "处理中",
    "completed": "已完成",
    "failed": "失败",
    "needs_reindex": "需要重新索引",
    "insufficient": "资料不足",
}


def settings_page(app):
    st.header("AI 设置")
    try:
        current = app.settings.load()
    except AppError as exc:
        st.warning(str(exc))
        current = AISettings()
    st.caption("当前密钥状态：" + app.settings.key_status(current))
    st.info(
        "默认模型使用北京接口。新加坡的 Flash Embedding 可用性未获官方列表确认，请手动改用 text-embedding-v4 等当地可用模型。地域、业务空间与 Key 必须匹配。"
    )
    st.markdown(
        "[百炼模型与地域说明](https://help.aliyun.com/zh/model-studio/embedding) · "
        "[获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)"
    )
    with st.form("ai_settings", clear_on_submit=False):
        st.text_input("服务商", value="阿里云百炼", disabled=True)
        base = st.text_input("API Base URL（HTTPS）", current.base_url)
        st.caption(
            "北京传统地址：https://dashscope.aliyuncs.com/compatible-mode/v1；新加坡传统地址：https://dashscope-intl.aliyuncs.com/compatible-mode/v1。新业务空间请复制控制台提供的地域专属地址，替换其中 WorkspaceId。"
        )
        key = st.text_input(
            "新的 API Key（留空保留当前目标地址的密钥）", type="password", key="new_api_key"
        )
        llm = st.text_input("LLM 模型 ID", current.llm_model)
        embedding = st.text_input("Embedding 模型 ID", current.embedding_model)
        dimensions = st.number_input("Embedding 维度", 1, 4096, current.dimensions)
        with st.expander("检索与分块设置"):
            size = st.number_input("Chunk Size（字符）", 200, 4000, current.chunk_size)
            overlap = st.number_input("Chunk Overlap（字符）", 0, 3999, current.chunk_overlap)
            top_k = st.number_input("Top-K", 1, 10, current.top_k)
            history = st.number_input("最近历史消息数", 0, 20, current.history_messages)
            history_chars = st.number_input("历史字符总上限", 0, 20000, current.history_chars)
            distance = st.slider("最大余弦距离（越小越严格）", 0.0, 2.0, current.max_distance)
        confirmed = st.checkbox(
            "我已核对上方实际 API 目标地址、地域和模型；更换 Embedding / 分块配置后需要手动重建索引。"
        )
        if st.form_submit_button("保存设置", type="primary"):
            if not confirmed:
                st.error("请先核对并确认 API 目标地址。")
            else:
                updated = AISettings(
                    base_url=base.strip().rstrip("/"),
                    llm_model=llm.strip(),
                    embedding_model=embedding.strip(),
                    dimensions=int(dimensions),
                    chunk_size=int(size),
                    chunk_overlap=int(overlap),
                    top_k=int(top_k),
                    history_messages=int(history),
                    history_chars=int(history_chars),
                    max_distance=distance,
                )
                app.settings.save(updated, key.strip())
                st.session_state["clear_key_next_run"] = True
                st.session_state["settings_saved"] = True
                st.rerun()
    if st.session_state.pop("settings_saved", False):
        st.success("非秘密设置已保存，密钥仅由操作系统安全凭据管理。")
    st.write("已保存的 API 目标地址：", current.base_url)
    consent = st.checkbox("连接测试将发送两条合成测试请求（Embedding + LLM），可能产生 API 费用。")
    if st.button("测试已保存配置的 API 连接", disabled=not consent):
        with st.spinner("正在测试 Embedding 与 LLM…"):
            st.success(app.settings.test_connection(confirmed=consent))
    st.caption("连接测试只使用合成文本，不会读取项目资料。修改表单后请先保存。")
    with st.expander("高级选项"):
        st.caption("仅用于本机排查；不会更改或迁移数据目录。完整路径可能包含用户名。")
        if st.checkbox("显示完整数据路径（可能包含用户名）", key="show_full_data_path"):
            st.code(app.data_path, language=None)


def knowledge_page(app, project_id):
    st.header("知识库管理")
    st.caption("导入只保存到本机，不会调用外部 API。同名文件的新内容作为更新；相同内容自动去重。")
    uploads = st.file_uploader(
        "选择 Markdown / TXT（UTF-8，每份不超过 10 MB）",
        type=["md", "txt"],
        accept_multiple_files=True,
        key=f"uploads_{project_id}",
    )
    if st.button("保存上传文件", disabled=not uploads):
        for upload in uploads:
            try:
                result = app.documents.upload(project_id, upload.name, upload.getvalue())
                st.success(
                    f"{upload.name}："
                    + {
                        "created": "已保存，尚未索引",
                        "updated": "已更新，需要重新索引",
                        "duplicate": "内容已存在，未重复导入",
                    }[result["action"]]
                )
            except AppError as exc:
                st.error(f"{upload.name}：{exc}")
    documents = app.documents.list(project_id)
    if not documents:
        st.info("当前项目尚无资料，请先导入文件。")
        return
    st.dataframe(
        [
            {
                "文件名": d["name"],
                "状态": STATUS[d["status"]],
                "Chunk 数": d["chunk_count"],
                "说明": d["error"],
            }
            for d in documents
        ],
        hide_index=True,
        width="stretch",
    )
    selected = st.multiselect(
        "选择需要建立或重新建立索引的文件",
        [d["id"] for d in documents],
        format_func=lambda x: next(d["name"] for d in documents if d["id"] == x),
        key=f"index_docs_{project_id}",
    )
    with st.expander("已有索引配置（检查模型和维度）"):
        for d in documents:
            st.write(d["name"], d["index_config"] or "尚无索引")
    settings = app.settings.load()
    st.warning(
        f"建立索引会把所选资料的文本分块发送至 {settings.base_url}，模型：{settings.embedding_model}，维度：{settings.dimensions}。可能产生 API 费用。"
    )
    confirmed = st.checkbox(
        "我确认向上述外部 API 发送所选文件文本并建立索引。", key=f"index_consent_{project_id}"
    )
    if st.button("建立索引 / 重新索引", disabled=not (confirmed and selected), type="primary"):
        progress = st.progress(0)
        for i, doc_id in enumerate(selected):
            name = next(d["name"] for d in documents if d["id"] == doc_id)
            try:
                with st.spinner(f"正在索引 {name}…"):
                    result = app.documents.index(project_id, doc_id, confirmed=confirmed)
                st.success(f"{name}：已完成，{result['chunk_count']} 个 Chunk。")
            except AppError as exc:
                st.error(f"{name}：{exc}")
            progress.progress((i + 1) / len(selected))
        st.info("索引处理结束，点击刷新查看最新状态。")
    if st.button("刷新索引状态"):
        st.rerun()


def chat_page(app, project_id):
    st.header("项目智能问答")
    st.caption("消息时间按运行本应用电脑的本地时区显示。")
    try:
        settings = app.settings.load()
        st.caption(
            f"提问时会向 {settings.base_url} 发送问题、必要历史上下文及本项目检索证据，可能产生 API 费用。历史回答不会写入知识库。"
        )
    except AppError as exc:
        st.warning(str(exc))
        st.caption("历史记录仍可浏览。请先修复 AI 设置，再继续问答。")
    with st.expander("清空当前项目的聊天记录"):
        confirm = st.checkbox(
            "确认永久清空当前项目对话（不删除文件与索引）", key=f"clear_{project_id}"
        )
        if st.button("确认清空", disabled=not confirm, key=f"clear_button_{project_id}"):
            app.qa.clear(project_id, confirmed=confirm)
            st.rerun()
    history = app.qa.history(project_id)
    if not history:
        st.info("对话尚未开始。请先建立索引，再询问项目技术细节或个人职责。")
    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            st.caption(
                f"{format_message_time(message['created_at'])} · {STATUS.get(message['status'], message['status'])}"
            )
            if message["citations"]:
                with st.expander(f"查看本次提供给模型的来源证据（{len(message['citations'])} 条）"):
                    full_ids = st.checkbox("显示完整 Chunk ID", key=f"citation_ids_{message['id']}")
                    for i, citation in enumerate(message["citations"]):
                        if i:
                            st.divider()
                        st.text(f"来源：{citation['source']}")
                        st.caption(
                            (
                                "章节：" + citation["heading"]
                                if citation.get("heading")
                                else "无章节标题"
                            )
                            + (" · 模型标记支持" if citation.get("cited") else " · 检索上下文")
                        )
                        if full_ids:
                            st.code(citation["chunk_id"], language=None)
                        else:
                            st.caption("片段：" + short_chunk_id(citation["chunk_id"]))
                        st.text(citation["text"])
    question = st.chat_input("询问当前项目…", key=f"question_{project_id}")
    if question:
        try:
            with st.spinner("正在检索本项目证据并生成回答…"):
                app.qa.ask(project_id, question)
        except AppError:
            pass  # Sanitized failure is persisted and rendered after rerun.
        st.rerun()


def render_page(page):
    app = application()
    if page == "AI 设置":
        settings_page(app)
        return
    projects = app.projects.list()
    project_id = st.session_state.get("project_selection")
    project = next((p for p in projects if p["id"] == project_id), None)
    if project is None:
        st.title("欢迎使用 ProjectRevisit")
        st.info(
            "先在左侧创建项目，再导入资料、手动建立索引并开始问答。未配置 API 也可以管理项目和文件。"
        )
        return
    st.title(project["name"])
    if page == "项目概况":
        docs = app.documents.list(project_id)
        st.metric("已导入文档", len(docs))
        st.metric("已完成且兼容的索引", sum(d["status"] == "completed" for d in docs))
        st.caption("项目 ID：" + project_id)
        st.info("通过左侧「知识库管理」导入和索引，通过「智能问答」回顾项目。")
    elif page == "知识库管理":
        knowledge_page(app, project_id)
    else:
        chat_page(app, project_id)


def main():
    st.set_page_config(page_title="ProjectRevisit", page_icon="📚", layout="wide")
    if st.session_state.pop("clear_key_next_run", False):
        st.session_state["new_api_key"] = ""
    app = application()
    st.sidebar.title("ProjectRevisit")
    st.sidebar.caption("v0.1 · 本地项目知识库")
    with st.sidebar.form("create_project", clear_on_submit=True):
        name = st.text_input("新项目名称")
        if st.form_submit_button("创建项目"):
            project_id = app.projects.create(name)
            st.session_state["project_selection"] = project_id
            st.rerun()
    projects = app.projects.list()
    if projects:
        st.sidebar.selectbox(
            "当前项目",
            [p["id"] for p in projects],
            format_func=lambda x: next(p["name"] for p in projects if p["id"] == x),
            key="project_selection",
        )
    page = st.navigation(
        [
            st.Page("views/overview.py", title="项目概况", icon="🏠", default=True),
            st.Page("views/knowledge.py", title="知识库管理", icon="📂"),
            st.Page("views/chat.py", title="智能问答", icon="💬"),
            st.Page("views/settings.py", title="AI 设置", icon="⚙️"),
        ]
    )
    page.run()


if __name__ == "__main__":
    try:
        main()
    except AppError as exc:
        st.error(str(exc))
    except Exception:
        st.error("当前操作失败。请检查本机数据目录权限或依赖安装；应用未输出原始异常以保护隐私。")
