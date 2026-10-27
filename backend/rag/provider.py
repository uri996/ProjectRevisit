"""Replaceable provider boundary; no network activity during construction elsewhere."""

import json
import math

import httpx
from langchain_core.embeddings import Embeddings
from openai import OpenAI

from backend.models import AppError


class BailianProvider(Embeddings):
    def __init__(self, settings, key, http_client=None):
        settings.validate()
        self.settings = settings
        self.client = OpenAI(
            api_key=key,
            base_url=settings.base_url.rstrip("/"),
            timeout=45,
            max_retries=0,
            http_client=http_client or httpx.Client(follow_redirects=False, timeout=45),
        )

    def embed_documents(self, texts):
        vectors = []
        try:
            # v4 supports 10 rows; disable tokenization and send original UTF-8 strings.
            batches, batch, batch_bytes = [], [], 0
            for text in texts:
                size = len(text.encode("utf-8"))
                if size > 8000:
                    raise AppError("单个文本超过保守请求上限，请降低 Chunk Size 或缩短问题。")
                if batch and (len(batch) >= 10 or batch_bytes + size > 8000):
                    batches.append(batch)
                    batch, batch_bytes = [], 0
                batch.append(text)
                batch_bytes += size
            if batch:
                batches.append(batch)
            for batch in batches:
                response = self.client.embeddings.create(
                    model=self.settings.embedding_model,
                    input=batch,
                    dimensions=self.settings.dimensions,
                    encoding_format="float",
                )
                rows = sorted(response.data, key=lambda item: item.index)
                if [r.index for r in rows] != list(range(len(batch))):
                    raise ValueError("incomplete embedding batch")
                for row in rows:
                    vector = row.embedding
                    if len(vector) != self.settings.dimensions or not all(
                        math.isfinite(x) for x in vector
                    ):
                        raise ValueError("invalid vector")
                    vectors.append(vector)
        except AppError:
            raise
        except Exception:
            raise AppError(
                "Embedding 请求失败：请检查地域、模型权限、维度、额度及网络；原始文件已保留。"
            ) from None
        return vectors

    def embed_query(self, text):
        return self.embed_documents([text])[0]

    def complete(self, system, payload):
        try:
            response = self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.1,
                max_tokens=2200,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            raise AppError(
                "LLM 请求失败或返回格式无效：请检查模型、地域、权限、额度及网络。"
            ) from None

    def close(self):
        self.client.close()
