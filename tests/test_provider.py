import json
from dataclasses import replace

import httpx
import pytest

from backend.models import AISettings, AppError
from backend.rag.provider import BailianProvider


def test_real_sdk_request_shapes_batching_and_generation():
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append((str(request.url), body))
        assert request.headers["authorization"] == "Bearer synthetic-test-key"
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "model": body["model"],
                    "data": [
                        {"object": "embedding", "index": i, "embedding": [1.0] * 256}
                        for i, _ in enumerate(body["input"])
                    ],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"ok":true}'},
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=False)
    provider = BailianProvider(replace(AISettings(), dimensions=256), "synthetic-test-key", client)
    try:
        assert len(provider.embed_documents(["中文"] * 23)) == 23
        assert len(provider.embed_query("问题")) == 256
        assert provider.complete("Return JSON", {"test": "synthetic"}) == {"ok": True}
    finally:
        provider.close()
    assert [len(body["input"]) for _, body in requests[:-1]] == [10, 10, 3, 1]
    assert requests[0][1]["dimensions"] == 256
    assert requests[-1][0].endswith("/chat/completions")
    assert requests[-1][1]["enable_thinking"] is False
    assert requests[-1][1]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("mode", ["auth", "dimension", "partial", "redirect", "json"])
def test_provider_errors_redacted(mode):
    def handle(request):
        if mode == "auth":
            return httpx.Response(401, json={"error": {"message": "synthetic-secret-and-content"}})
        if mode == "redirect":
            return httpx.Response(
                307, headers={"Location": "https://unapproved.example/embeddings"}
            )
        if mode == "json":
            return httpx.Response(200, content=b"bad-json synthetic-secret-and-content")
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "synthetic",
                "data": []
                if mode == "partial"
                else [{"object": "embedding", "index": 0, "embedding": [1.0]}],
            },
        )

    provider = BailianProvider(
        AISettings(),
        "synthetic",
        httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=False),
    )
    try:
        with pytest.raises(AppError) as error:
            provider.embed_query("synthetic-private-content")
        assert "synthetic-secret" not in str(error.value)
        assert "synthetic-private" not in str(error.value)
    finally:
        provider.close()
