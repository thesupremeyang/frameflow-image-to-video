from __future__ import annotations

from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import ConfigError
from app.database import utc_now
from app.downloads import download_video
from app.models import MODEL_SPECS, Generation
from app.providers import ProviderError
from app.schemas import MAX_IMAGE_BYTES, InputError, inspect_image, validate_parameters
from app.tasks import remove_local_file

router = APIRouter(prefix="/api")

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ConfigUpdate(BaseModel):
    ark_api_key: str | None = Field(default=None, max_length=4096)
    minimax_api_key: str | None = Field(default=None, max_length=4096)
    ark_base_url: str | None = Field(default=None, max_length=4096)
    minimax_base_url: str | None = Field(default=None, max_length=4096)
    seedance_25_model: str | None = Field(default=None, max_length=200)
    seedance_20_model: str | None = Field(default=None, max_length=200)
    minimax_model: str | None = Field(default=None, max_length=200)
    s3_endpoint_url: str | None = Field(default=None, max_length=4096)
    s3_region: str | None = Field(default=None, max_length=200)
    s3_bucket: str | None = Field(default=None, max_length=500)
    s3_access_key_id: str | None = Field(default=None, max_length=4096)
    s3_secret_access_key: str | None = Field(default=None, max_length=4096)
    s3_public_base_url: str | None = Field(default=None, max_length=4096)
    s3_prefix: str | None = Field(default=None, max_length=500)


def config_payload(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "models": MODEL_SPECS,
        "ready": {
            "ark": bool(settings.ark_api_key),
            "minimax": bool(settings.minimax_api_key) and settings.s3_ready,
        },
        "configuration": request.app.state.config.public(),
    }


def require_local_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        return
    if urlparse(origin).hostname not in LOCAL_HOSTS:
        raise HTTPException(403, "只允许从本地工作台修改配置。")


def get_job(request: Request, job_id: str) -> Generation:
    job = request.app.state.database.get(job_id)
    if not job:
        raise HTTPException(404, "找不到这条生成记录。")
    return job


@router.get("/config")
async def configuration(request: Request):
    return config_payload(request)


@router.post("/config")
async def update_configuration(request: Request, payload: ConfigUpdate):
    require_local_origin(request)
    try:
        request.app.state.config.update(payload.model_dump(exclude_none=True))
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    return config_payload(request)


@router.post("/generations", status_code=202)
async def create_generation(
    request: Request,
    image: UploadFile,
    model: str = Form(...),
    prompt: str = Form(...),
    duration: int = Form(...),
    resolution: str = Form(...),
    generate_audio: bool = Form(False),
):
    try:
        validate_parameters(model, prompt, duration, resolution)
        content = await image.read(MAX_IMAGE_BYTES + 1)
        media_type, extension, _, _ = inspect_image(content, model)
    except InputError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await image.close()
    settings = request.app.state.settings
    job_id = uuid4().hex
    image_path = settings.upload_dir / f"{job_id}{extension}"
    try:
        image_path.write_bytes(content)
    except OSError as exc:
        raise HTTPException(500, "图片保存失败，请检查本地磁盘空间。") from exc
    now = utc_now()
    job = Generation(
        id=job_id, model=model, prompt=prompt.strip(), duration=duration,
        resolution=resolution, generate_audio=generate_audio and MODEL_SPECS[model]["audio"],
        image_path=str(image_path), image_media_type=media_type,
        status="queued", created_at=now, updated_at=now,
    )
    request.app.state.database.insert(job)
    request.app.state.tasks.start(job_id)
    return job.to_dict()


@router.get("/generations")
async def generations(request: Request):
    return [job.to_dict() for job in request.app.state.database.list()]


@router.get("/generations/{job_id}")
async def generation(request: Request, job_id: str):
    return get_job(request, job_id).to_dict()


@router.get("/generations/{job_id}/image")
async def generation_image(request: Request, job_id: str):
    job = get_job(request, job_id)
    try:
        return FileResponse(job.image_path, media_type=job.image_media_type)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(404, "找不到本地图片。") from exc


@router.get("/generations/{job_id}/video")
async def generation_video(request: Request, job_id: str):
    job = get_job(request, job_id)
    if not job.local_video_path:
        raise HTTPException(409, "视频尚未准备完成，请稍后重试。")
    try:
        return FileResponse(job.local_video_path, media_type="video/mp4")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(404, "找不到本地视频，请使用下载按钮重试。") from exc


@router.get("/generations/{job_id}/download")
async def generation_download(request: Request, job_id: str):
    job = get_job(request, job_id)
    if job.status != "succeeded" or not job.video_url:
        raise HTTPException(409, "视频尚未生成完成。")
    path = request.app.state.settings.video_dir / f"{job.id}.mp4"
    if not path.is_file():
        try:
            await download_video(job.video_url, path, request.app.state.settings)
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc
    if not job.local_video_path:
        request.app.state.database.update(job_id, local_video_path=str(path))
    return FileResponse(path, media_type="video/mp4", filename=f"{job.model}-{job.id[:8]}.mp4")


@router.delete("/generations")
async def clear_generations(request: Request):
    await request.app.state.tasks.stop()
    request.app.state.tasks.running.clear()
    paths = request.app.state.database.clear()
    for image_path, video_path in paths:
        await remove_local_file(image_path)
        await remove_local_file(video_path)
    return {"cleared": len(paths)}
