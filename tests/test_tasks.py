import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.providers.mock import MockProvider
from test_app import form, wait_for_status, settings


def test_restart_resumes_existing_remote_id(settings, monkeypatch):
    from app.tasks import TaskManager
    mock = MockProvider()
    original_init = TaskManager.__init__

    def mock_init(manager, database, configuration):
        original_init(manager, database, configuration)
        manager.provider = lambda _: mock
        manager.download = write_video

    monkeypatch.setattr(TaskManager, "__init__", mock_init)
    settings.ensure_data_dirs()
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post("/api/generations", data=form(), files=image_file())
        job_id = response.json()["id"]
        wait_for_status(client, job_id)
    app.state.database.update(job_id, status="running", local_video_path=None)
    with TestClient(app) as restarted:
        wait_for_status(restarted, job_id)
        job = app.state.database.get(job_id)
        assert job.remote_id == "mock-1"
        assert job.status == "succeeded"
        assert mock.create_calls == 1


def image_file():
    stream = io.BytesIO()
    Image.new("RGB", (640, 480), "#77876c").save(stream, format="PNG")
    return {"image": ("first-frame.png", stream.getvalue(), "image/png")}


async def write_video(url, path, _):
    Path(path).write_bytes(b"test video")
    return path
