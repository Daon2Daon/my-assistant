import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.services.youtube.llm_client import LiteLLMClient, LiteLLMError
from app.services.youtube.settings_manager import AIGatewaySettings


def _make_client(handler, ttl: float = 60.0) -> LiteLLMClient:
    settings = AIGatewaySettings(
        base_url="http://litellm:4000",
        api_key="master-key",
        primary_model="gemini/gemini-2.5-flash",
        fallback_model="gemini/gemini-2.5-flash",
        tagging_model="gemini/gemini-2.5-flash",
        temperature=0.3,
        max_tokens=8192,
        daily_budget_usd=2.0,
    )
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, timeout=5.0)
    return LiteLLMClient(settings=settings, client=http, models_cache_ttl_sec=ttl)


@pytest.mark.asyncio
async def test_get_models_caches_by_ttl():
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        p = urlparse(str(request.url))
        if p.path.endswith("/v1/models"):
            calls["n"] += 1
            return httpx.Response(
                200,
                json={"data": [{"id": "gemini/gemini-2.5-flash"}, {"id": "claude-3-5-sonnet"}]},
            )
        return httpx.Response(404, text="unexpected")

    c = _make_client(handler, ttl=60.0)
    try:
        a = await c.get_models()
        b = await c.get_models()
        assert calls["n"] == 1
        assert [m.id for m in a.models] == [m.id for m in b.models]
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_chat_openai_compatible_success():
    async def handler(request: httpx.Request) -> httpx.Response:
        p = urlparse(str(request.url))
        if p.path.endswith("/v1/chat/completions"):
            body = json.loads(request.content.decode("utf-8"))
            assert body["model"] == "gemini/gemini-2.5-flash"
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )
        return httpx.Response(404, text="unexpected")

    c = _make_client(handler)
    try:
        r = await c.chat(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert r.content == "ok"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_analyze_video_native_parses_structured_json_text():
    async def handler(request: httpx.Request) -> httpx.Response:
        p = urlparse(str(request.url))
        qs = parse_qs(p.query)
        if "/gemini/v1beta/models/" in p.path:
            assert qs["key"][0] == "master-key"
            payload = {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps({"one_line": "x", "tags": []})}]
                        }
                    }
                ]
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(404, text="unexpected")

    c = _make_client(handler)
    try:
        r = await c.analyze_video_native(
            model="gemini-2.5-flash",
            video_url="https://www.youtube.com/watch?v=abc",
            prompt="p",
            response_schema={"type": "object"},
        )
        assert r.data["one_line"] == "x"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_analyze_video_native_raises_when_no_text():
    async def handler(request: httpx.Request) -> httpx.Response:
        p = urlparse(str(request.url))
        if "/gemini/v1beta/models/" in p.path:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": []}}]})
        return httpx.Response(404, text="unexpected")

    c = _make_client(handler)
    try:
        with pytest.raises(LiteLLMError):
            await c.analyze_video_native(
                model="gemini-2.5-flash",
                video_url="https://www.youtube.com/watch?v=abc",
                prompt="p",
            )
    finally:
        await c.aclose()

