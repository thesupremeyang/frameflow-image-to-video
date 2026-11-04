from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class ProviderError(RuntimeError):
    """A safe, actionable error that can be shown in the local UI."""

    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


@dataclass(frozen=True)
class ProviderResult:
    status: str
    video_url: str | None = None
    error: str | None = None


class VideoProvider(Protocol):
    poll_interval: int

    async def create(self, *, model: str, prompt: str, image: bytes,
                     image_media_type: str, duration: int, resolution: str,
                     generate_audio: bool) -> str: ...

    async def poll(self, remote_id: str) -> ProviderResult: ...


async def checked_json(response: httpx.Response) -> dict[str, Any]:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            payload = response.json()
            detail = payload.get("error") or payload.get("base_resp") or payload
            message = detail.get("message") or detail.get("status_msg") if isinstance(detail, dict) else None
        except (ValueError, AttributeError):
            message = None
        suffix = f"：{str(message)[:240]}" if message else ""
        raise ProviderError(f"云端接口返回 HTTP {response.status_code}{suffix}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError("云端接口返回了无法解析的响应。") from exc
    if not isinstance(payload, dict):
        raise ProviderError("云端接口响应格式不正确。")
    return payload
