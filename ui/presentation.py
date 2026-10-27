import os
from datetime import UTC, datetime
from pathlib import PureWindowsPath


def format_message_time(value, timezone=None):
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(timezone).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, AttributeError, OverflowError, OSError):
        return "时间未知"


def private_path_label(value, local_app_data=None):
    base = local_app_data if local_app_data is not None else os.environ.get("LOCALAPPDATA")
    if base:
        try:
            relative = PureWindowsPath(value).relative_to(PureWindowsPath(base))
            if str(relative) == "ProjectRAGAssistant":
                return "%LOCALAPPDATA%\\ProjectRAGAssistant\\"
        except ValueError:
            pass
    return "自定义本机数据目录（完整路径已隐藏）"


def short_chunk_id(value):
    return value if len(value) <= 24 else f"{value[:8]}…{value[-8:]}"
