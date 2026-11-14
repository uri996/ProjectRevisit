from backend.models import AppError
from backend.rag.generator import generate
from backend.rag.retriever import retrieve
from backend.services.locking import project_lock


class QAService:
    def __init__(self, root, db, vectors, settings):
        self.root, self.db, self.vectors, self.settings = root, db, vectors, settings

    def history(self, project_id):
        return self.db.messages(project_id)

    def clear(self, project_id, confirmed=False):
        self.db.project(project_id)
        if not confirmed:
            raise AppError("清空当前项目聊天记录需要二次确认。")
        with project_lock(self.root, project_id):
            self.db.execute("DELETE FROM messages WHERE project_id=?", (project_id,))

    def ask(self, project_id, question):
        self.db.project(project_id)
        question = question.strip()
        if not question or len(question) > 8000:
            raise AppError("问题应为 1–8000 个字符。")
        with project_lock(self.root, project_id):
            self.db.add_message(project_id, "user", question)
            try:
                settings = self.settings.load()
                documents = self.db.query(
                    "SELECT * FROM documents WHERE project_id=? AND status='completed' AND signature=?",
                    (project_id, settings.signature),
                )
                if not documents and self.settings.key_status(settings) != "已保存":
                    answer = "当前项目暂无兼容索引，无法核实项目事实。请先手动建立索引；配置可用 API Key 后，也可获取明确标注的通用知识与建议。"
                    citations, status = [], "insufficient"
                else:
                    history = self.db.messages(project_id, settings.history_messages + 1)[:-1]
                    # Bound both message count and total characters, retaining recent messages.
                    recent, remaining = [], settings.history_chars
                    for row in reversed(history):
                        if row["status"] not in ("completed", "insufficient") or remaining <= 0:
                            continue
                        content = row["content"][-remaining:]
                        recent.append(dict(role=row["role"], content=content))
                        remaining -= len(content)
                    history = recent[::-1]
                    # Retrieval uses prior USER questions only; assistant content is never embedded.
                    query = "\n".join(
                        [x["content"] for x in history if x["role"] == "user"] + [question]
                    )
                    query = query.encode("utf-8")[-6000:].decode("utf-8", errors="ignore")
                    with self.settings.provider(settings) as provider:
                        evidence = []
                        if documents:
                            query_vector = provider.embed_query(query)
                            evidence = retrieve(
                                self.vectors, documents, project_id, query_vector, settings
                            )
                        evidence_state = (
                            "no_compatible_index"
                            if not documents
                            else "matched"
                            if evidence
                            else "no_matches"
                        )
                        answer, citations, status = generate(
                            provider, question, history, evidence, evidence_state=evidence_state
                        )
                self.db.add_message(project_id, "assistant", answer, status, citations)
                return dict(answer=answer, citations=citations, status=status)
            except Exception as exc:
                message = (
                    str(exc)
                    if isinstance(exc, AppError)
                    else "问答失败；聊天历史与项目资料已保留，请稍后重试。"
                )
                self.db.add_message(project_id, "assistant", message, "failed")
                raise AppError(message) from None
