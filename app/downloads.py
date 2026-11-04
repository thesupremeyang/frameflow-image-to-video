from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.config import Settings
from app.providers.base import ProviderError


def validate_video_url(url: str, allowed_suffixes: tuple[str, ...]) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ProviderError("云端返回的视频地址不符合安全要求。")
    if not any(host == suffix or host.endswith(f".{suffix}") for suffix in allowed_suffixes):
        raise ProviderError("视频地址不在允许的云端域名列表中，可在配置中显式添加。")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ProviderError("无法解析视频下载地址。") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ProviderError("视频下载地址不能指向本地或私有网络。")


async def download_video(url: str, destination: Path, settings: Settings) -> Path:
    validate_video_url(url, settings.download_host_suffixes)
    temp = destination.with_name(f".{uuid4().hex}.part")
    size = 0
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0), follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and int(length) > settings.max_video_bytes:
                    raise ProviderError("视频超过本地下载大小限制。")
                with temp.open("wb") as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > settings.max_video_bytes:
                            raise ProviderError("视频超过本地下载大小限制。")
                        output.write(chunk)
        if not size:
            raise ProviderError("下载的视频为空。")
        temp.replace(destination)
        return destination
    except (httpx.HTTPError, OSError, ValueError) as exc:
        temp.unlink(missing_ok=True)
        raise ProviderError("视频下载失败，请稍后点击下载重试。") from exc
    except Exception:
        temp.unlink(missing_ok=True)
        raise
