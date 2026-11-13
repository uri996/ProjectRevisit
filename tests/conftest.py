import hashlib
import math
import socket

import pytest
from langchain_core.embeddings import Embeddings

from backend.models import AISettings
from backend.services.application import create_application


def fictional_question_output():
    return {
        "questions": [
            {"question": question, "direction": direction, "reason": reason}
            for question, direction, reason in (
                ("Catalog 如何使用 CSV 保存图书目录？", "数据存储", "了解描述中的目录存储方案。"),
                ("目录编号重复时如何处理？", "数据校验", "核对描述中的唯一性约束。"),
                ("图书分类的校验边界是什么？", "边界条件", "考察分类输入处理。"),
                ("如何测试图书关键字查找？", "测试方法", "考察检索功能的验证方式。"),
                ("如果目录文件无法读取，你会如何处理？", "异常处理", "以假设场景考察健壮性。"),
                ("如果增加多用户操作，需要考虑什么？", "扩展思考", "讨论尚未实现的假设扩展。"),
            )
        ]
    }


class MemoryKeys:
    def __init__(self):
        self.values = {}

    def get(self, account):
        return self.values.get(account)

    def set(self, account, key):
        self.values[account] = key


class FakeProvider(Embeddings):
    def __init__(self, settings, key):
        self.settings = settings
        self.embedded = []
        self.payloads = []
        self.fail_embedding = False
        self.fail_llm = False
        self.supported = True
        self.invent_citation = False

    def embed_documents(self, texts):
        if self.fail_embedding:
            raise RuntimeError("secret-from-provider must never be displayed")
        self.embedded.extend(texts)
        vectors = []
        terms = ["catalog", "csv", "图书", "task", "localstorage", "任务", "分类", "导出"]
        for text in texts:
            vector = [0.01] * self.settings.dimensions
            for i, term in enumerate(terms):
                vector[i] = float(term in text.lower()) + 0.01
            # Stable deterministic component for otherwise empty input.
            vector[-1] = (hashlib.sha256(text.encode()).digest()[0] / 255) * 0.01
            norm = math.sqrt(sum(x * x for x in vector))
            vectors.append([x / norm for x in vector])
        return vectors

    def embed_query(self, text):
        return self.embed_documents([text])[0]

    def complete(self, system, payload):
        if self.fail_llm:
            raise RuntimeError("secret-from-provider must never be displayed")
        self.payloads.append(payload)
        if "test" in payload:
            return {"ok": True}
        if "project_description" in payload:
            return fictional_question_output()
        chunk_id = "invented-path" if self.invent_citation else payload["evidence"][0]["chunk_id"]
        return dict(
            supported=self.supported,
            answer="示例回答：" + payload["evidence"][0]["text"]
            if self.supported
            else "材料没有记录选择原因。",
            used_chunk_ids=[chunk_id] if self.supported else [],
        )


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    original_connect = socket.socket.connect

    def blocked(*args, **kwargs):
        address = args[1] if len(args) > 1 else None
        # Windows asyncio uses a local socketpair even in Streamlit's in-process tests.
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(*args, **kwargs)
        raise AssertionError("Network is forbidden in offline tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


@pytest.fixture
def configured(tmp_path):
    keys = MemoryKeys()
    providers = []

    def factory(settings, key):
        provider = FakeProvider(settings, key)
        providers.append(provider)
        return provider

    app = create_application(tmp_path, keys, factory)
    app.settings.save(AISettings(), "synthetic-key-for-offline-tests")
    return app, providers, keys, factory
