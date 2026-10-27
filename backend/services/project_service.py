from uuid import uuid4

from backend.models import AppError
from backend.storage.database import now


class ProjectService:
    def __init__(self, db):
        self.db = db

    def create(self, name):
        name = name.strip()
        if not name or len(name) > 100:
            raise AppError("项目名称应为 1–100 个字符。")
        project_id = str(uuid4())
        self.db.execute("INSERT INTO projects VALUES(?,?,?)", (project_id, name, now()))
        return project_id

    def list(self):
        return self.db.query("""SELECT p.*, count(d.id) AS document_count,
            coalesce(sum(d.status='completed'),0) AS indexed_count
            FROM projects p LEFT JOIN documents d ON p.id=d.project_id
            GROUP BY p.id ORDER BY p.created_at,p.id""")
