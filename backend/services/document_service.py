import json
from uuid import uuid4

from backend.models import AppError
from backend.rag.chunker import split_document
from backend.rag.loader import load_text
from backend.services.locking import project_lock
from backend.storage.database import now
from backend.storage.files import validate_upload


class DocumentService:
    def __init__(self, root, db, files, vectors, settings):
        self.root, self.db, self.files = root, db, files
        self.vectors, self.settings = vectors, settings

    def list(self, project_id):
        self.db.project(project_id)
        # A released OS lock plus 'processing' means the previous worker stopped unexpectedly.
        try:
            with project_lock(self.root, project_id):
                self.db.execute(
                    "UPDATE documents SET status='failed',error=? WHERE project_id=? AND status='processing'",
                    ("上次索引中断，请手动重试；原始文件已保留。", project_id),
                )
        except AppError:
            pass
        rows = self.db.query(
            "SELECT * FROM documents WHERE project_id=? ORDER BY created_at,id", (project_id,)
        )
        try:
            signature = self.settings.load().signature
        except AppError:
            signature = None
        for row in rows:
            if row["status"] == "completed" and row["signature"] != signature:
                row["status"] = "needs_reindex"
        return rows

    def upload(self, project_id, name, content):
        self.db.project(project_id)
        digest = validate_upload(name, content)
        with project_lock(self.root, project_id):
            duplicates = self.db.query(
                "SELECT * FROM documents WHERE project_id=? AND digest=?", (project_id, digest)
            )
            if duplicates:
                return dict(document_id=duplicates[0]["id"], action="duplicate")
            existing = self.db.query(
                "SELECT * FROM documents WHERE project_id=? AND name=? COLLATE NOCASE",
                (project_id, name),
            )
            document_id = existing[0]["id"] if existing else str(uuid4())
            relative = self.files.save(project_id, document_id, content)
            if existing:
                self.db.execute(
                    "UPDATE documents SET digest=?,path=?,status='needs_reindex',error='' WHERE id=? AND project_id=?",
                    (digest, relative, document_id, project_id),
                )
            else:
                self.db.execute(
                    "INSERT INTO documents(id,project_id,name,digest,path,status,created_at) VALUES(?,?,?,?,?,'unindexed',?)",
                    (document_id, project_id, name, digest, relative, now()),
                )
            return dict(document_id=document_id, action="updated" if existing else "created")

    def index(self, project_id, document_id, confirmed=False):
        if not confirmed:
            raise AppError("请先确认将文档文本发送至已配置的外部 Embedding API。")
        with project_lock(self.root, project_id):
            document = self.db.document(project_id, document_id)
            settings = self.settings.load()
            settings.validate()
            self.db.execute(
                "UPDATE documents SET status='processing',error='' WHERE id=?", (document_id,)
            )
            staged = None
            try:
                text = load_text(self.files.read(document["path"]))
                chunks = split_document(
                    text, project_id, document_id, document["name"], settings, uuid4().hex
                )
                if not chunks:
                    raise AppError("没有可以索引的文本。")
                with self.settings.provider(settings) as provider:
                    staged = self.vectors.stage(project_id, chunks, provider)
                self.db.execute(
                    """UPDATE documents SET status='completed',error='',collection=?,
                    signature=?,index_config=?,chunk_count=? WHERE id=? AND project_id=?""",
                    (
                        staged,
                        settings.signature,
                        json.dumps(settings.to_dict()),
                        len(chunks),
                        document_id,
                        project_id,
                    ),
                )
            except Exception as exc:
                if staged:
                    try:
                        self.vectors.delete(staged)
                    except Exception:
                        pass
                message = (
                    str(exc)
                    if isinstance(exc, AppError)
                    else "索引失败；原始文件与其他项目未受影响，请检查配置后重试。"
                )
                self.db.execute(
                    "UPDATE documents SET status='failed',error=? WHERE id=?",
                    (message, document_id),
                )
                raise AppError(message) from None
            # Explicit reindex replaces only this document's previous vector generation.
            if document["collection"] and document["collection"] != staged:
                try:
                    self.vectors.delete(document["collection"])
                except Exception:
                    pass  # Orphaned old generation is never queried.
            return dict(document_id=document_id, chunk_count=len(chunks), status="completed")
