import asyncio
import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.providers.base import ProviderError
from app.providers.mock import MockProvider


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", ark_api_key="test", minimax_api_key="test",
                    download_host_suffixes=("example.com",))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def image_file(width=640, height=480):
    stream = io.BytesIO()
    Image.new("RGB", (width, height), "#77876c").save(stream, format="PNG")
    return {"image": ("first-frame.png", stream.getvalue(), "image/png")}


def form(model="seedance-2.5", duration="5", resolution="720p"):
    return {"model": model, "prompt": "镜头缓慢向前推进，微风拂过。", "duration": duration,
            "resolution": resolution, "generate_audio": "true"}


def wait_for_status(client, job_id, expected="succeeded"):
    for _ in range(200):
        job = client.get(f"/api/generations/{job_id}").json()
        if job["status"] == expected:
            return job
        if job["status"] == "failed" and expected != "failed":
            raise AssertionError(job["error"])
        time.sleep(0.01)
    raise AssertionError("Task did not finish in time")


async def write_video(url, path, _):
    Path(path).write_bytes(b"test video")
    return path


def test_home_and_safe_config(client):
    assert client.get("/").status_code == 200
    config = client.get("/api/config").json()
    assert len(config["models"]) == 3
    assert "test" not in str(config)
    assert config["ready"]["ark"] is True
    assert config["ready"]["minimax"] is False
    assert "fields" in config["configuration"]
    assert "ark_api_key_configured" in config["configuration"]


def test_config_save_applies_immediately_and_never_echoes_secrets(settings):
    settings.ensure_data_dirs()
    app = create_app(settings)
    with TestClient(app) as client:
        payload = {
            "ark_api_key": "ark-secret-value",
            "minimax_api_key": "minimax-secret-value",
            "ark_base_url": "https://ark.example.com/api/v3",
            "minimax_base_url": "https://minimax.example.com",
            "seedance_25_model": "seedance-new-25",
            "seedance_20_model": "seedance-new-20",
            "minimax_model": "h3-new",
            "s3_endpoint_url": "https://s3.example.com",
            "s3_region": "auto",
            "s3_bucket": "studio-images",
            "s3_access_key_id": "storage-access-secret",
            "s3_secret_access_key": "storage-private-secret",
            "s3_public_base_url": "https://media.example.com",
            "s3_prefix": "frameflow",
        }
        response = client.post("/api/config", json=payload)
        assert response.status_code == 200
        assert response.json()["ready"] == {"ark": True, "minimax": True}
        assert all(secret not in response.text for secret in (
            "ark-secret-value", "minimax-secret-value", "storage-access-secret", "storage-private-secret"
        ))
        assert app.state.settings.seedance_25_model == "seedance-new-25"
        assert app.state.settings.s3_ready is True
        assert app.state.tasks.provider("seedance-2.5").model_ids["seedance-2.5"] == "seedance-new-25"
        assert (settings.data_dir / "settings.json").is_file()
        # Blank secret inputs preserve the existing credentials.
        response = client.post("/api/config", json={
            "ark_api_key": "", "minimax_api_key": "",
            "ark_base_url": "https://ark.example.com/api/v3",
            "minimax_base_url": "https://minimax.example.com",
            "seedance_25_model": "seedance-new-25", "seedance_20_model": "seedance-new-20",
            "minimax_model": "h3-new", "s3_endpoint_url": "https://s3.example.com",
            "s3_region": "auto", "s3_bucket": "studio-images", "s3_access_key_id": "",
            "s3_secret_access_key": "", "s3_public_base_url": "https://media.example.com",
            "s3_prefix": "frameflow",
        })
        assert response.status_code == 200
        assert app.state.settings.minimax_api_key == "minimax-secret-value"
        assert app.state.settings.s3_secret_access_key == "storage-private-secret"
    # Configuration survives a server restart and is loaded without exposing secrets.
    with TestClient(create_app(settings)) as restarted:
        config = restarted.get("/api/config").json()
        assert config["ready"] == {"ark": True, "minimax": True}
        assert config["configuration"]["fields"]["seedance_25_model"] == "seedance-new-25"
        assert "storage-private-secret" not in str(config)


def test_config_rejects_invalid_url_and_foreign_origin(settings):
    settings.ensure_data_dirs()
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/config", json={
            "ark_base_url": "http://insecure.example.com", "seedance_25_model": "x"
        })
        assert response.status_code == 422
        assert "HTTPS" in response.json()["detail"]
        response = client.post("/api/config", json={"ark_api_key": "secret"},
                               headers={"Origin": "https://evil.example.com"})
        assert response.status_code == 403


def test_reject_invalid_image_and_duration(client):
    response = client.post("/api/generations", data=form(duration="40"), files=image_file())
    assert response.status_code == 422
    response = client.post("/api/generations", data=form(), files={"image": ("fake.png", b"bad", "image/png")})
    assert response.status_code == 422


def test_task_success_and_files(settings):
    settings.ensure_data_dirs()
    app = create_app(settings)
    with TestClient(app) as client:
        mock = MockProvider()
        app.state.tasks.provider = lambda _: mock
        app.state.tasks.download = write_video
        response = client.post("/api/generations", data=form(), files=image_file())
        assert response.status_code == 202
        job_id = response.json()["id"]
        job = wait_for_status(client, job_id)
        assert job["status"] == "succeeded"
        assert job["video_url"].startswith("/api/")
        assert "remote_id" not in job
        assert Path(app.state.database.get(job_id).local_video_path).read_bytes() == b"test video"
        assert client.get(job["image_url"]).status_code == 200
        assert client.get(job["video_url"]).content == b"test video"
        assert client.get(job["download_url"]).headers["content-disposition"].endswith('.mp4"')
        assert len(client.get("/api/generations").json()) == 1


def test_minimax_uses_storage(settings, monkeypatch):
    settings.ensure_data_dirs()
    app = create_app(settings)
    uploaded = []
    class Storage:
        def __init__(self, _settings):
            pass
        def upload(self, path, media_type):
            uploaded.append((Path(path).name, media_type))
            return "https://media.example.com/input.png"
    monkeypatch.setattr("app.tasks.S3ImageStorage", Storage)
    with TestClient(app) as client:
        mock = MockProvider()
        app.state.tasks.provider = lambda _: mock
        app.state.tasks.download = write_video
        response = client.post("/api/generations", data=form("minimax-h3", "8", "2K"), files=image_file())
        wait_for_status(client, response.json()["id"])
        assert mock.last_request["image_url"] == "https://media.example.com/input.png"
        assert "image" not in mock.last_request
        assert uploaded[0][1] == "image/png"


def test_provider_failure_is_reported(settings):
    settings.ensure_data_dirs()
    app = create_app(settings)
    with TestClient(app) as client:
        class Failure:
            poll_interval = 0
            async def create(self, **kwargs):
                raise ProviderError("尚未配置 API Key")
        app.state.tasks.provider = lambda _: Failure()
        response = client.post("/api/generations", data=form(), files=image_file())
        wait_for_status(client, response.json()["id"], "failed")
        saved = app.state.database.get(response.json()["id"])
        assert saved.error == "尚未配置 API Key"


def test_clear_history_deletes_files(settings):
    settings.ensure_data_dirs()
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.tasks.provider = lambda _: MockProvider()
        app.state.tasks.download = write_video
        response = client.post("/api/generations", data=form(), files=image_file())
        job_id = response.json()["id"]
        wait_for_status(client, job_id)
        job = app.state.database.get(job_id)
        assert client.delete("/api/generations").json() == {"cleared": 1}
        assert app.state.database.list() == []
        assert not Path(job.image_path).exists()
        assert not Path(job.local_video_path).exists()
