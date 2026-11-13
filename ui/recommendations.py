import streamlit as st

from backend.models import AppError
from ui.presentation import format_message_time


def recommendation_panel(service, project_id):
    selected = None
    with st.expander("不知道问什么？试试推荐问题"):
        st.caption(
            "基础推荐不调用 API。点击问题会直接对当前项目提问，可能产生正常 RAG 问答费用。"
            "尚无兼容索引时会提示资料不足，请先在知识库管理中建立索引。"
        )
        direction = st.segmented_control(
            "提问方向",
            ["项目复盘", "面试准备"],
            default="项目复盘",
            key=f"recommendation_direction_{project_id}",
        )
        show_all = st.checkbox("显示全部基础问题", key=f"recommendation_all_{project_id}")
        questions = service.presets(direction or "项目复盘")
        for i, question in enumerate(questions if show_all else questions[:3]):
            if st.button(question, key=f"preset_question_{project_id}_{direction}_{i}"):
                selected = question
        saved = None
        try:
            saved = service.load(project_id)
        except Exception:
            st.warning("已保存的推荐问题暂时无法读取；可以重新生成，基础推荐和聊天仍可使用。")
        with st.expander("根据简历生成"):
            st.caption("只发送你填写的描述和目标岗位，不读取知识库，不生成答案。")
            with st.form(f"recommendation_form_{project_id}"):
                description = st.text_area(
                    "简历项目描述 / 简短项目介绍",
                    value=saved["description"] if saved else "",
                    max_chars=8000,
                    height=140,
                    key=f"recommendation_description_{project_id}",
                )
                role = st.text_input(
                    "目标岗位",
                    value=saved["target_role"] if saved else "通用项目面试",
                    max_chars=100,
                    key=f"recommendation_role_{project_id}",
                    help="例如通用项目面试、AI 产品经理或后端开发。",
                )
                consent = st.checkbox(
                    "我确认向 AI 设置中的 LLM API 发送上述描述和岗位，可能产生 API 费用。",
                    key=f"recommendation_consent_{project_id}",
                )
                submitted = st.form_submit_button("生成 / 重新生成问题")
            if submitted:
                try:
                    with st.spinner("正在生成个性化问题…"):
                        saved = service.generate(project_id, description, role, confirmed=consent)
                    st.success("问题已按当前项目保存；再次查看不会调用 API。")
                except AppError as exc:
                    st.warning(str(exc))
                except Exception:
                    st.warning("推荐问题生成或保存失败；请手动重试，聊天仍可使用。")
        if saved:
            with st.expander(f"已保存的个性化问题（{len(saved['questions'])} 道）"):
                st.caption(
                    f"目标岗位：{saved['target_role']} · {format_message_time(saved['updated_at'])}。"
                    "这是上次成功保存的结果，修改输入后请手动重新生成。"
                )
                for i, row in enumerate(saved["questions"]):
                    if st.button(row["question"], key=f"personal_question_{project_id}_{i}"):
                        selected = row["question"]
                    st.text(f"考察方向：{row['direction']} · 推荐理由：{row['reason']}")
    return selected
