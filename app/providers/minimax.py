from __future__ import annotations

import httpx

from app.providers.base import ProviderError, ProviderResult, checked_json


class MiniMaxProvider:
    poll_interval = 10

    def __init__(self, api_key: str, model_id: str, client: httpx.AsyncClient | None = None,
                 *, base_url: str = "https://api.minimax.io"):
        if not api_key:
            raise ProviderError("尚未配置 MiniMax API Key。请点击页面右上角“模型配置”填写。")
        self.model_id = model_id
        self.client = client or httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(60.0, connect=15.0),
        )

    async def create(self, *, prompt: str, image_url: str, duration: int,
                     resolution: str) -> str:
        payload = {
            "model": self.model_id,
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}, "role": "first_frame"},
            ],
            "duration": duration,
            "resolution": resolution,
        }
        try:
            response = await self.client.post("/v2/video_generation", json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接 MiniMax，请检查网络后重试。", transient=True) from exc
        data = await checked_json(response)
        base_resp = data.get("base_resp")
        if isinstance(base_resp, dict) and base_resp.get("status_code", 0) not in {0, 1000}:
            raise ProviderError(f"MiniMax 创建任务失败：{str(base_resp.get('status_msg', '未知错误'))[:240]}")
        remote_id = data.get("task_id")
        if not isinstance(remote_id, str) or not remote_id:
            raise ProviderError("MiniMax 未返回任务 ID。")
        return remote_id

    async def poll(self, remote_id: str) -> ProviderResult:
        try:
            response = await self.client.get(f"/v2/query/video_generation/{remote_id}")
        except httpx.HTTPError as exc:
            raise ProviderError("查询 MiniMax 任务时网络异常，将自动重试。", transient=True) from exc
        data = await checked_json(response)
        task = data.get("task")
        if not isinstance(task, dict):
            raise ProviderError("MiniMax 任务响应格式不正确。")
        status = task.get("status")
        if status == "succeeded":
            content = task.get("content") or {}
            url = content.get("url") if isinstance(content, dict) else None
            if not isinstance(url, str) or not url:
                raise ProviderError("任务已完成，但未返回视频地址。")
            return ProviderResult(status="succeeded", video_url=url)
        if status in {"failed", "cancelled"}:
            error = task.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            return ProviderResult(status="failed", error=message or f"云端任务状态：{status}。")
        if status not in {"queued", "running", "processing", "pending", "preparing"}:
            raise ProviderError("MiniMax 返回了未知任务状态。")
        return ProviderResult(status="queued" if status in {"queued", "pending"} else "running")
