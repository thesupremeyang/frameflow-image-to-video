import base64
import json

import httpx
import pytest

from app.providers.ark import ArkProvider
from app.providers.base import ProviderError
from app.providers.minimax import MiniMaxProvider


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://test.local", headers={"Authorization": "Bearer test-key"})


async def test_ark_create_and_poll():
    requests = []
    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"id": "cgt-test"})
        return httpx.Response(200, json={"status": "succeeded", "content": {"video_url": "https://media.volces.com/video.mp4"}})
    provider = ArkProvider("test-key", {"seedance-2.5": "model-id"}, client_for(handler))
    remote_id = await provider.create(model="seedance-2.5", prompt="镜头推进", image=b"image", image_media_type="image/png", duration=5, resolution="720p", generate_audio=True)
    assert remote_id == "cgt-test"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "model-id"
    assert payload["ratio"] == "adaptive"
    assert payload["duration"] == 5
    assert payload["content"][1]["role"] == "first_frame"
    assert base64.b64decode(payload["content"][1]["image_url"]["url"].split(",")[1]) == b"image"
    assert requests[0].headers["Authorization"] == "Bearer test-key"
    result = await provider.poll(remote_id)
    assert result.video_url.endswith("video.mp4")
    await provider.client.aclose()


async def test_ark_failure_is_normalized():
    provider = ArkProvider("test-key", {}, client_for(lambda _: httpx.Response(200, json={"status": "failed", "error": {"message": "内容未通过审核"}})))
    result = await provider.poll("cgt-test")
    assert result.status == "failed"
    assert result.error == "内容未通过审核"
    await provider.client.aclose()


async def test_minimax_create_and_poll():
    requests = []
    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "h3-test", "base_resp": {"status_code": 0}})
        return httpx.Response(200, json={"task": {"status": "succeeded", "content": {"url": "https://cdn.minimax.io/video.mp4"}}})
    provider = MiniMaxProvider("test-key", "MiniMax-H3", client_for(handler))
    remote_id = await provider.create(prompt="微风吹动", image_url="https://media.example.com/a.png", duration=8, resolution="2K")
    assert remote_id == "h3-test"
    payload = json.loads(requests[0].content)
    assert payload["content"][1]["image_url"]["url"] == "https://media.example.com/a.png"
    assert payload["resolution"] == "2K"
    result = await provider.poll(remote_id)
    assert requests[1].url.path == "/v2/query/video_generation/h3-test"
    assert result.status == "succeeded"
    await provider.client.aclose()


async def test_minimax_api_error():
    provider = MiniMaxProvider("test-key", "MiniMax-H3", client_for(lambda _: httpx.Response(200, json={"base_resp": {"status_code": 1002, "status_msg": "invalid key"}})))
    with pytest.raises(ProviderError, match="invalid key"):
        await provider.create(prompt="测试", image_url="https://media.example.com/a.png", duration=5, resolution="768P")
    await provider.client.aclose()


async def test_missing_key_never_sends_request():
    with pytest.raises(ProviderError, match="火山方舟 API Key"):
        ArkProvider("", {})
    with pytest.raises(ProviderError, match="MiniMax API Key"):
        MiniMaxProvider("", "MiniMax-H3")
