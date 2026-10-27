import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from backend.models import AppError


def now():
    return datetime.now(UTC).isoformat(timespec="microseconds")


def identifier(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise AppError("无效的项目或文档标识。") from None
    return value


class Database:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "metadata.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    name TEXT NOT NULL, digest TEXT NOT NULL, path TEXT NOT NULL,
                    status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
                    collection TEXT, signature TEXT, index_config TEXT,
                    chunk_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                    UNIQUE(project_id, name));
                CREATE TABLE IF NOT EXISTS messages (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                    created_at TEXT NOT NULL, status TEXT NOT NULL, citations TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS messages_project ON messages(project_id, seq);
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def query(self, sql, params=()):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params)]

    def execute(self, sql, params=()):
        with self.connect() as conn:
            conn.execute(sql, params)

    def project(self, project_id):
        identifier(project_id)
        rows = self.query("SELECT * FROM projects WHERE id=?", (project_id,))
        if not rows:
            raise AppError("项目不存在。")
        return rows[0]

    def document(self, project_id, document_id):
        self.project(project_id)
        identifier(document_id)
        rows = self.query(
            "SELECT * FROM documents WHERE project_id=? AND id=?", (project_id, document_id)
        )
        if not rows:
            raise AppError("当前项目中没有该文档。")
        return rows[0]

    def messages(self, project_id, limit=None):
        self.project(project_id)
        if limit is not None:
            if limit <= 0:
                return []
            rows = self.query(
                "SELECT * FROM messages WHERE project_id=? ORDER BY seq DESC LIMIT ?",
                (project_id, limit),
            )[::-1]
        else:
            rows = self.query(
                "SELECT * FROM messages WHERE project_id=? ORDER BY seq", (project_id,)
            )
        for row in rows:
            row["citations"] = json.loads(row["citations"])
        return rows

    def add_message(self, project_id, role, content, status="completed", citations=()):
        self.project(project_id)
        self.execute(
            "INSERT INTO messages(id,project_id,conversation_id,role,content,created_at,status,citations) VALUES(?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                project_id,
                project_id,
                role,
                content,
                now(),
                status,
                json.dumps(list(citations), ensure_ascii=False),
            ),
        )
