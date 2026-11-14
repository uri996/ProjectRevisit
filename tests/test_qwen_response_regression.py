"""Synthetic Qwen-shaped HTTP replies exercise the real SDK, parser and validator.

These fixtures reproduce strict-contract failures; they are not captured private
responses or a claim that a live model produced a particular format.
"""

import json
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_api
from backend.models import AISettings, AppError
from backend.rag.generator import generate
from backend.rag.provider import BailianProvider
from backend.services.application import create_application

EVIDENCE = [
    dict(
        chunk_id="fictional-project:document:generation:0",
        document_id="fictional-document",
        source="catalog.md",
        heading="演示资料",
        text="虚构图书目录使用 CSV 保存记录。目录编号必须唯一。",
        distance=0.1,
    )
]


def sdk(content, finish="stop", status=200):
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            status,
            json={
                "id": "synthetic",
                "object": "chat.completion",
                "created": 0,
                "model": "synthetic",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish,
                        "message": {"role": "assistant", "content": content},
                    }
                ],
            },
        )

    return (
        BailianProvider(
            AISettings(),
            "synthetic-offline-key",
            httpx.Client(transport=httpx.MockTransport(handle)),
        ),
        calls,
    )


def encode(sections, **extra):
    return json.dumps(dict(sections=sections, **extra), ensure_ascii=False)


@pytest.mark.parametrize(
    "content",
    [
        # Extra titles, casing, singleton objects and missing optional quote used
        # to reject an otherwise grounded answer after a successful HTTP request.
        encode(
            {
                "title": "设计",
                "kind": " Analysis ",
                "text": "可以考虑原子写入。",
                "sources": " `E1` ",
            },
            title="复盘",
        ),
        encode([{"kind": "fact", "text": "使用 CSV。", "sources": [{"chunk_id": "E1"}]}]),
        encode(
            [{"kind": "general", "text": "## 通用方法\n\n- **测试**\n- `评估`", "sources": None}]
        ),
        encode([{"kind": "uncertainty", "text": "没有记录真实故障。"}]),
        encode(
            [
                {"kind": "general", "text": "通用建议，不代表已采用。"},
                {
                    "kind": "analysis",
                    "text": "基于文件存储，可以评估写入可靠性。",
                    "sources": {"chunk_id": "E1"},
                },
                {
                    "kind": "fact",
                    "text": "编号唯一。",
                    "sources": [{"chunk_id": "E1", "quote": "目录编号必须唯一。", "title": "原文"}],
                },
            ]
        ),
        "\ufeff```json\n"
        + encode([{"kind": "general", "text": "中文普通说明，不代表项目实践。"}])
        + "\n```",
    ],
)
def test_reasonable_wire_variations_survive_real_sdk_and_grounding(content):
    provider, calls = sdk(content)
    try:
        answer, citations, status = generate(provider, "技术取舍", [], EVIDENCE)
    finally:
        provider.close()
    assert status in ("completed", "insufficient") and answer
    assert citations[0]["chunk_id"] == EVIDENCE[0]["chunk_id"]
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert payload["evidence"][0]["chunk_id"] == "E1"
    assert EVIDENCE[0]["chunk_id"] not in calls[0]["messages"][1]["content"]
    assert len(calls) == 1  # No hidden paid repair/retry loop.


@pytest.mark.parametrize(
    "row,code",
    [
        ({"kind": "fact", "text": "CSV", "sources": ["E99"]}, "SOURCE_UNKNOWN"),
        (
            {"kind": "fact", "text": "CSV", "sources": ["other-project:document:0"]},
            "SOURCE_UNKNOWN",
        ),
        (
            {
                "kind": "fact",
                "text": "CSV",
                "sources": [{"chunk_id": "E1", "quote": "经历线上故障"}],
            },
            "QUOTE",
        ),
        ({"kind": "analysis", "text": "项目应改进", "sources": []}, "SOURCE_REQUIRED"),
        ({"kind": "fact", "text": "已完成优化"}, "SOURCE_REQUIRED"),
        ({"kind": "general", "text": "通用技术", "sources": ["E1"]}, "SOURCE_ROLE"),
        ({"kind": "fact", "text": "CSV", "sources": [{"chunk_id": "E1", "quote": None}]}, "QUOTE"),
        ({"kind": "fact", "text": None, "sources": ["E1"]}, "SECTION"),
    ],
)
def test_invalid_claims_are_not_silently_stripped_or_downgraded(row, code, caplog):
    provider, calls = sdk(encode([row]))
    try:
        with pytest.raises(AppError, match=f"QA_{code}") as error:
            generate(provider, "synthetic private question", [], EVIDENCE)
    finally:
        provider.close()
    assert EVIDENCE[0]["text"] not in str(error.value)
    assert "other-project" not in str(error.value)
    assert "synthetic private question" not in caplog.text
    assert len(calls) == 1


@pytest.mark.parametrize(
    "content,finish,status,code",
    [
        ("plain text **not JSON**", "stop", 200, "LLM_JSON"),
        ('{"sections":[', "length", 200, "LLM_TRUNCATED"),
        ("", "stop", 200, "LLM_EMPTY"),
        ("{}", "content_filter", 200, "LLM_FINISH"),
        ("{}", "stop", 401, "LLM_REQUEST"),
        ("[]", "stop", 200, "QA_STRUCTURE"),
    ],
)
def test_diagnostics_separate_transport_json_truncation_and_structure(
    content, finish, status, code
):
    provider, calls = sdk(content, finish, status)
    try:
        with pytest.raises(AppError, match=code):
            generate(provider, "虚构问题", [], EVIDENCE)
    finally:
        provider.close()
    assert len(calls) == 1


def test_reported_questions_persist_and_restore_and_bad_reference_stays_failed(
    configured, tmp_path
):
    app, _, keys, factory = configured
    first, second = app.projects.create("示例项目 A"), app.projects.create("示例项目 B")
    doc = app.documents.upload(first, "catalog.md", EVIDENCE[0]["text"].encode())
    app.documents.index(first, doc["document_id"], confirmed=True)
    app.settings.save(replace(app.settings.load(), max_distance=2.0))
    document = app.documents.list(first)[0]
    original_ids = app.documents.vectors._open(document["collection"]).get()["ids"]
    contents = iter(
        [
            encode(
                [
                    {"kind": "uncertainty", "text": "资料没有记载未解决问题清单。"},
                    {
                        "kind": "analysis",
                        "text": "可以核查编号冲突和写入中断的处理边界，这是建议而非已发生故障。",
                        "sources": "E1",
                    },
                ],
                title="问题分析",
            ),
            encode(
                {
                    "kind": "analysis",
                    "text": "## 可讨论的取舍\n\n**CSV** 简单，但可以评估并发写入约束；无法确认当时的真实动机。",
                    "sources": {"chunk_id": "E1"},
                }
            ),
            encode(
                [
                    {
                        "kind": "fact",
                        "text": "未经证实的事件。",
                        "sources": ["other-project:private:0"],
                    }
                ]
            ),
        ]
    )
    calls = []

    def provider_factory(settings, key):
        provider = factory(settings, key)
        wire, requests = sdk(next(contents))
        provider.complete = wire.complete
        provider.close = wire.close
        calls.append(requests)
        return provider

    app.settings.provider_factory = provider_factory
    with TestClient(
        create_api(app),
        base_url="http://127.0.0.1:8765",
        headers={"Origin": "http://127.0.0.1:8765"},
    ) as client:
        for question in ("项目还有什么没有解决的问题？", "项目中最值得深入讨论的技术决策是什么？"):
            response = client.post(
                f"/api/projects/{first}/questions",
                json={"question": question, "confirmed": True, "request_id": str(uuid4())},
            )
            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "completed" and result["citations"][0]["analysis_basis"]
            assert result["citations"][0]["chunk_id"] in original_ids
        bad = client.post(
            f"/api/projects/{first}/questions",
            json={"question": "再问一个虚构问题", "confirmed": True, "request_id": str(uuid4())},
        )
        assert bad.status_code == 400 and "QA_SOURCE_UNKNOWN" in bad.json()["error"]
        saved = client.get(f"/api/projects/{first}/messages").json()
        assert len(saved) == 6 and saved[-1]["status"] == "failed"
        assert saved[-1]["citations"] == []
        assert "other-project" not in saved[-1]["content"]
        assert "**CSV**" in saved[3]["content"]
        assert client.get(f"/api/projects/{second}/messages").json() == []
    reopened = create_application(tmp_path, keys, factory)
    assert reopened.qa.history(first) == app.qa.history(first)
    assert app.documents.vectors._open(document["collection"]).get()["ids"] == original_ids
    assert all(len(requests) == 1 for requests in calls)
