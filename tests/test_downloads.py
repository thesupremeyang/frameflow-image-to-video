from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.downloads import download_video, validate_video_url
from app.providers.base import ProviderError


def test_download_url_allowlist():
    with pytest.raises(ProviderError, match="安全"):
        validate_video_url("http://media.volces.com/video.mp4", ("volces.com",))
    with pytest.raises(ProviderError, match="允许的"):
        validate_video_url("https://volces.com.example.net/video.mp4", ("volces.com",))


def test_download_rejects_private_addresses(monkeypatch):
    monkeypatch.setattr("app.downloads.socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ProviderError, match="私有网络"):
        validate_video_url("https://media.volces.com/video.mp4", ("volces.com",))


async def test_download_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("app.downloads.validate_video_url", lambda *args: None)
    async def handler(request):
        return httpx.Response(200, content=b"123456")
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr("app.downloads.httpx.AsyncClient", lambda **kwargs: original(transport=transport))
    settings = Settings(data_dir=tmp_path, max_video_bytes=5)
    with pytest.raises(ProviderError, match="大小限制"):
        await download_video("https://media.volces.com/video.mp4", tmp_path / "video.mp4", settings)
    assert not list(tmp_path.glob("*.part"))


async def test_download_refuses_redirect(tmp_path, monkeypatch):
    monkeypatch.setattr("app.downloads.validate_video_url", lambda *args: None)
    async def handler(request):
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr("app.downloads.httpx.AsyncClient", lambda **kwargs: original(transport=transport))
    with pytest.raises(ProviderError, match="下载失败"):
        await download_video("https://media.volces.com/video.mp4", tmp_path / "video.mp4", Settings(data_dir=tmp_path))
