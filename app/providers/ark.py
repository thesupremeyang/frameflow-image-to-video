from __future__ import annotations

import base64
import binascii

import httpx

from app.providers.base import ProviderError, ProviderResult, checked_json


class ArkProvider:
    poll_interval = 5

    def __init__(self, api_key: str, model_ids: dict[str, str], client: httpx.AsyncClient | None = None,
                 *, base_url: str = "https://ark.cn-beijing.volces.com/api/v3"):
        if not api_key:
            raise ProviderError("尚未配置火山方舟 API Key。请点击页面右上角“模型配置”填写。")
        self.model_ids = model_ids
        self.client = client or httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(60.0, connect=15.0),
        )

    async def create(self, *, model: str, prompt: str, image: bytes,
                     image_media_type: str, duration: int, resolution: str,
                     generate_audio: bool) -> str:
        try:
            encoded = base64.b64encode(image).decode("ascii")
        except (ValueError, binascii.Error) as exc:
            raise ProviderError("图片编码失败，请重新选择图片。") from exc
        payload = {
            "model": self.model_ids[model],
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{image_media_type};base64,{encoded}"}, "role": "first_frame"},
            ],
            "ratio": "adaptive",
            "duration": duration,
            "resolution": resolution,
            "generate_audio": generate_audio,
        }
        try:
            response = await self.client.post("/contents/generations/tasks", json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接火山方舟，请检查网络后重试。", transient=True) from exc
        data = await checked_json(response)
        remote_id = data.get("id")
        if not isinstance(remote_id, str) or not remote_id:
            raise ProviderError("火山方舟未返回任务 ID。")
        return remote_id

    async def poll(self, remote_id: str) -> ProviderResult:
        try:
            response = await self.client.get(f"/contents/generations/tasks/{remote_id}")
        except httpx.HTTPError as exc:
            raise ProviderError("查询火山方舟任务时网络异常，将自动重试。", transient=True) from exc
        data = await checked_json(response)
        status = data.get("status")
        if status == "succeeded":
            content = data.get("content") or {}
            url = content.get("video_url") if isinstance(content, dict) else None
            if not isinstance(url, str) or not url:
                raise ProviderError("任务已完成，但未返回视频地址。")
            return ProviderResult(status="succeeded", video_url=url)
        if status in {"failed", "expired", "cancelled"}:
            error = data.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            return ProviderResult(status="failed", error=message or f"云端任务状态：{status}。")
        if status not in {"queued", "running"}:
            raise ProviderError("火山方舟返回了未知任务状态。")
        return ProviderResult(status=status)
