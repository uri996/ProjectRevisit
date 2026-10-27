from contextlib import contextmanager

from filelock import FileLock, Timeout

from backend.models import AppError
from backend.storage.database import identifier


@contextmanager
def project_lock(root, project_id):
    folder = root / "locks"
    folder.mkdir(parents=True, exist_ok=True)
    lock = FileLock(folder / f"{identifier(project_id)}.lock", timeout=0)
    try:
        with lock:
            yield
    except Timeout:
        raise AppError("此项目正在处理其他操作，请稍后重试。") from None
