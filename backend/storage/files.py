import hashlib
from pathlib import Path
from uuid import uuid4

from backend.models import AppError
from backend.storage.database import identifier

MAX_BYTES = 10 * 1024 * 1024


def validate_upload(name, content):
    if (
        not name
        or len(name) > 180
        or any(c in name for c in '/\\:<>"|?*')
        or any(ord(c) < 32 for c in name)
        or name.endswith((" ", "."))
    ):
        raise AppError("文件名不安全；请使用不含路径的普通文件名。")
    if Path(name).suffix.lower() not in (".md", ".txt"):
        raise AppError("仅支持 Markdown (.md) 和 TXT。")
    if len(content) > MAX_BYTES:
        raise AppError("文件超过 10 MB 限制。")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AppError("文件必须使用 UTF-8 编码。") from None
    if not text.strip() or "\x00" in text:
        raise AppError("文件为空或包含二进制内容。")
    return hashlib.sha256(content).hexdigest()


class FileStore:
    def __init__(self, root):
        self.root = root.resolve()

    def save(self, project_id, document_id, content):
        folder = self.root / "originals" / identifier(project_id) / identifier(document_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{uuid4().hex}.utf8"
        path.write_bytes(content)
        return str(path.relative_to(self.root))

    def read(self, relative):
        path = (self.root / relative).resolve()
        if self.root not in path.parents:
            raise AppError("资料路径超出私人数据目录。")
        return path.read_bytes()
