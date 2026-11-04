from __future__ import annotations

from app.providers.base import ProviderResult


class MockProvider:
    """Explicit test provider. Never enabled by default in the application."""

    poll_interval = 0

    def __init__(self):
        self.jobs: dict[str, int] = {}
        self.last_request: dict = {}
        self.create_calls = 0
        self.client = self

    async def create(self, **kwargs) -> str:
        self.last_request = kwargs
        self.create_calls += 1
        remote_id = f"mock-{len(self.jobs) + 1}"
        self.jobs[remote_id] = 0
        return remote_id

    async def poll(self, remote_id: str) -> ProviderResult:
        self.jobs[remote_id] += 1
        if self.jobs[remote_id] < 2:
            return ProviderResult(status="running")
        return ProviderResult(status="succeeded", video_url="https://example.com/video.mp4")

    async def aclose(self) -> None:
        return None
