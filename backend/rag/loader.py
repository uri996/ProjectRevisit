from backend.models import AppError


def load_text(content):
    try:
        return content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        raise AppError("原始文件无法以 UTF-8 读取。") from None
