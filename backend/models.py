import hashlib
import json
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit


class AppError(Exception):
    """A public, sanitized error safe to display."""


@dataclass(frozen=True)
class AISettings:
    provider: str = "阿里云百炼"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen3.7-flash"
    embedding_model: str = "qwen3.7-text-embedding-flash"
    dimensions: int = 1024
    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 4
    history_messages: int = 6
    history_chars: int = 6000
    max_distance: float = 0.8

    def validate(self):
        url = urlsplit(self.base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or "{" in self.base_url
        ):
            raise AppError("Base URL 必须是有效的 HTTPS 地址，不含凭据、查询参数或占位符。")
        if self.provider != "阿里云百炼":
            raise AppError("v0.1 仅支持阿里云百炼。")
        if not all(x.strip() for x in [self.llm_model, self.embedding_model]):
            raise AppError("请填写 LLM 和 Embedding 模型 ID。")
        if not 1 <= self.dimensions <= 4096:
            raise AppError("Embedding 维度应介于 1 与 4096。")
        if self.embedding_model == "qwen3.7-text-embedding-flash":
            if self.dimensions not in [256, 512, 768, 1024]:
                raise AppError("Flash Embedding 支持的维度为 256、512、768、1024。")
            if "ap-southeast-1" in url.hostname or "dashscope-intl" in url.hostname:
                raise AppError(
                    "官方新加坡列表未列出 Flash Embedding；请明确改选 text-embedding-v4 等当地可用模型，不会自动切换。"
                )
        if self.embedding_model == "text-embedding-v4" and self.dimensions not in (
            64,
            128,
            256,
            512,
            768,
            1024,
            1536,
            2048,
        ):
            raise AppError("text-embedding-v4 维度不受支持。")
        if not 200 <= self.chunk_size <= 4000 or not 0 <= self.chunk_overlap < self.chunk_size:
            raise AppError("分块大小应为 200–4000，重叠应小于分块大小。")
        if not (
            1 <= self.top_k <= 10
            and 0 <= self.history_messages <= 20
            and 0 <= self.history_chars <= 20000
            and 0 <= self.max_distance <= 2
        ):
            raise AppError("检索或历史窗口配置超出允许范围。")

    @property
    def signature(self):
        # LLM-only changes leave vector compatibility unchanged.
        fields = (
            self.provider,
            self.base_url.rstrip("/"),
            self.embedding_model,
            self.dimensions,
            self.chunk_size,
            self.chunk_overlap,
            "markdown-v1",
        )
        return hashlib.sha256(json.dumps(fields).encode()).hexdigest()

    def to_dict(self):
        return asdict(self)
