from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import ConfigManager, Settings
from app.database import Database
from app.tasks import TaskManager

BASE = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.ensure_data_dirs()
        app.state.config = ConfigManager(settings)
        database = Database(settings.database_path)
        database.initialize()
        app.state.database = database
        app.state.tasks = TaskManager(database, settings)
        app.state.tasks.restore()
        yield
        await app.state.tasks.stop()

    app = FastAPI(title="帧流 FrameFlow", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        location = first.get("loc", ["参数"])[-1]
        message = "请检查图片和生成参数。" if first.get("type") == "missing" else f"参数 {location} 格式不正确。"
        return JSONResponse(status_code=422, content={"detail": message})

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(BASE / "templates" / "index.html")

    return app


app = create_app()
