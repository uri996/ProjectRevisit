import os
from pathlib import Path

from platformdirs import user_data_path

from backend.models import AppError

REPO_ROOT = Path(__file__).resolve().parents[1]


def data_directory():
    override = os.environ.get("PROJECT_RAG_DATA_DIR")
    path = Path(override) if override else user_data_path("ProjectRAGAssistant", appauthor=False)
    path = path.expanduser().resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise AppError("私人数据目录必须位于项目仓库之外。")
    return path
