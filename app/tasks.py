from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.database import Database
from app.downloads import download_video
from app.models import Generation
from app.providers import ProviderError
from app.providers.ark import ArkProvider
from app.providers.minimax import MiniMaxProvider
from app.storage import S3ImageStorage

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings
        self.running: dict[str, asyncio.Task] = {}
        self.download = download_video

    def provider(self, model: str):
        if model == "minimax-h3":
            return MiniMaxProvider(self.settings.minimax_api_key, self.settings.model_ids[model],
                                   base_url=self.settings.minimax_base_url)
        return ArkProvider(self.settings.ark_api_key, self.settings.model_ids,
                           base_url=self.settings.ark_base_url)

    def start(self, job_id: str) -> None:
        existing = self.running.get(job_id)
        if existing and not existing.done():
            return
        self.running[job_id] = asyncio.create_task(self.run(job_id))

    def restore(self) -> None:
        for job in self.database.unfinished():
            self.start(job.id)

    async def stop(self) -> None:
        tasks = list(self.running.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, job_id: str) -> None:
        try:
            await self._run(job_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Local generation task failed: %s", job_id)
            self.database.update(job_id, status="failed", error="本地任务处理异常，请重新提交。云端任务可能仍在运行。")

    async def _run(self, job_id: str) -> None:
        job = self.database.get(job_id)
        if not job or job.status not in {"queued", "running"}:
            return
        provider = None
        try:
            provider = self.provider(job.model)
            if not job.remote_id:
                image_path = Path(job.image_path)
                if not image_path.is_file():
                    raise ProviderError("找不到本地图片，请重新提交。")
                if job.model == "minimax-h3":
                    image_url = await asyncio.to_thread(S3ImageStorage(self.settings).upload, image_path, job.image_media_type)
                    job.remote_id = await provider.create(
                        prompt=job.prompt, image_url=image_url,
                        duration=job.duration, resolution=job.resolution,
                    )
                else:
                    job.remote_id = await provider.create(
                        model=job.model, prompt=job.prompt, image=image_path.read_bytes(),
                        image_media_type=job.image_media_type, duration=job.duration,
                        resolution=job.resolution, generate_audio=job.generate_audio,
                    )
                self.database.update(job_id, remote_id=job.remote_id, status="queued")
            if job.video_url:
                await self._save_video(job, job.video_url)
                return
            started = datetime.now(timezone.utc)
            failures = 0
            while True:
                if (datetime.now(timezone.utc) - started).total_seconds() > self.settings.task_timeout_seconds:
                    raise ProviderError("任务等待超过时限，已停止本地轮询。请前往云端控制台检查任务。")
                try:
                    result = await provider.poll(job.remote_id)
                    failures = 0
                except ProviderError as exc:
                    if not exc.transient:
                        raise
                    failures += 1
                    if failures >= 3:
                        raise ProviderError("连续三次查询云端任务失败。云端任务可能仍在运行，请检查控制台后重试。") from exc
                    await asyncio.sleep(provider.poll_interval)
                    continue
                if result.status == "succeeded":
                    if not result.video_url:
                        raise ProviderError("任务已完成，但未返回视频地址。")
                    self.database.update(job_id, video_url=result.video_url)
                    await self._save_video(job, result.video_url)
                    return
                if result.status == "failed":
                    self.database.update(job_id, status="failed", error=result.error or "云端生成失败。")
                    return
                self.database.update(job_id, status=result.status)
                await asyncio.sleep(provider.poll_interval)
        except ProviderError as exc:
            self.database.update(job_id, status="failed", error=str(exc))
        finally:
            if provider is not None and hasattr(provider, "client"):
                await provider.client.aclose()

    async def _save_video(self, job: Generation, url: str) -> None:
        destination = self.settings.video_dir / f"{job.id}.mp4"
        try:
            await self.download(url, destination, self.settings)
        except ProviderError as exc:
            self.database.update(job.id, status="failed", error=f"云端视频已生成，但保存到本地失败：{exc} 可点击下载重试。")
            return
        self.database.update(job.id, status="succeeded", local_video_path=str(destination), error=None)


async def remove_local_file(path: str | None) -> None:
    if path:
        await asyncio.to_thread(Path(path).unlink, missing_ok=True)
