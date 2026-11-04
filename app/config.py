from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SECRET_FIELDS = {"ark_api_key", "minimax_api_key", "s3_access_key_id", "s3_secret_access_key"}
SETTING_FIELDS = {
    "ark_api_key", "minimax_api_key", "ark_base_url", "minimax_base_url",
    "seedance_25_model", "seedance_20_model", "minimax_model",
    "s3_endpoint_url", "s3_region", "s3_bucket", "s3_access_key_id",
    "s3_secret_access_key", "s3_public_base_url", "s3_prefix",
}


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", ROOT / "data")))
    ark_api_key: str = field(default_factory=lambda: os.getenv("ARK_API_KEY", ""))
    minimax_api_key: str = field(default_factory=lambda: os.getenv("MINIMAX_API_KEY", ""))
    ark_base_url: str = field(default_factory=lambda: os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/"))
    minimax_base_url: str = field(default_factory=lambda: os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io").rstrip("/"))
    s3_endpoint_url: str = field(default_factory=lambda: os.getenv("S3_ENDPOINT_URL", ""))
    s3_region: str = field(default_factory=lambda: os.getenv("S3_REGION", "auto"))
    s3_bucket: str = field(default_factory=lambda: os.getenv("S3_BUCKET", ""))
    s3_access_key_id: str = field(default_factory=lambda: os.getenv("S3_ACCESS_KEY_ID", ""))
    s3_secret_access_key: str = field(default_factory=lambda: os.getenv("S3_SECRET_ACCESS_KEY", ""))
    s3_public_base_url: str = field(default_factory=lambda: os.getenv("S3_PUBLIC_BASE_URL", "").rstrip("/"))
    s3_prefix: str = field(default_factory=lambda: os.getenv("S3_PREFIX", "frameflow").strip("/"))
    seedance_25_model: str = field(default_factory=lambda: os.getenv("ARK_MODEL_SEEDANCE_2_5", "doubao-seedance-2-5-260628"))
    seedance_20_model: str = field(default_factory=lambda: os.getenv("ARK_MODEL_SEEDANCE_2_0", "doubao-seedance-2-0-260128"))
    minimax_model: str = field(default_factory=lambda: os.getenv("MINIMAX_MODEL", "MiniMax-H3"))
    task_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("TASK_TIMEOUT_SECONDS", "7200")))
    max_video_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_VIDEO_BYTES", str(500 * 1024 * 1024))))
    download_host_suffixes: tuple[str, ...] = field(default_factory=lambda: tuple(
        host.strip().lower()
        for host in os.getenv(
            "DOWNLOAD_HOST_SUFFIXES", "volces.com,minimax.io,minimaxi.com,aliyuncs.com,myqcloud.com"
        ).split(",") if host.strip()
    ))

    @property
    def model_ids(self) -> dict[str, str]:
        return {
            "seedance-2.5": self.seedance_25_model,
            "seedance-2.0": self.seedance_20_model,
            "minimax-h3": self.minimax_model,
        }

    @property
    def s3_ready(self) -> bool:
        return all((self.s3_bucket, self.s3_access_key_id, self.s3_secret_access_key, self.s3_public_base_url))

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def video_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def config_path(self) -> Path:
        return self.data_dir / "settings.json"

    def ensure_data_dirs(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)


class ConfigError(ValueError):
    pass


class ConfigManager:
    """Stores user overrides locally without exposing secrets to the browser."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.overrides: dict[str, str] = {}
        self.load_error: str | None = None
        self._load()

    def _load(self) -> None:
        path = self.settings.config_path
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            self.load_error = "本地配置文件无法读取。重新保存配置会覆盖它。"
            return
        safe = {key: str(value) for key, value in payload.items() if key in SETTING_FIELDS}
        self.overrides = safe
        self._apply(safe)

    def _apply(self, values: dict[str, str]) -> None:
        for key, value in values.items():
            if key in SETTING_FIELDS:
                setattr(self.settings, key, value)

    def public(self) -> dict:
        s = self.settings
        return {
            "ark_api_key_configured": bool(s.ark_api_key),
            "minimax_api_key_configured": bool(s.minimax_api_key),
            "s3_configured": s.s3_ready,
            "config_file_error": self.load_error,
            "fields": {
                "ark_base_url": s.ark_base_url,
                "minimax_base_url": s.minimax_base_url,
                "seedance_25_model": s.seedance_25_model,
                "seedance_20_model": s.seedance_20_model,
                "minimax_model": s.minimax_model,
                "s3_endpoint_url": s.s3_endpoint_url,
                "s3_region": s.s3_region,
                "s3_bucket": s.s3_bucket,
                "s3_public_base_url": s.s3_public_base_url,
                "s3_prefix": s.s3_prefix,
                "s3_access_key_configured": bool(s.s3_access_key_id),
                "s3_secret_configured": bool(s.s3_secret_access_key),
            },
        }

    def update(self, values: dict[str, str]) -> dict:
        clean = self._validate(values)
        merged = {**self.overrides, **clean}
        self._write(merged)
        self.overrides = merged
        self.load_error = None
        self._apply(clean)
        return self.public()

    def _validate(self, values: dict[str, str]) -> dict[str, str]:
        clean: dict[str, str] = {}
        for key, raw in values.items():
            if key not in SETTING_FIELDS:
                continue
            value = str(raw or "").strip()
            if any(char in value for char in "\r\n\0"):
                raise ConfigError(f"{key} 包含无效字符。")
            if len(value) > 4096:
                raise ConfigError(f"{key} 内容过长。")
            if key in SECRET_FIELDS and not value:
                continue
            clean[key] = value
        for key in ("ark_base_url", "minimax_base_url"):
            if key in clean and not self._is_https(clean[key]):
                raise ConfigError("模型接口地址必须是有效的 HTTPS 地址。")
        for key in ("s3_endpoint_url", "s3_public_base_url"):
            if clean.get(key) and not self._is_https(clean[key]):
                raise ConfigError("S3 地址必须是有效的 HTTPS 地址。")
        for key in ("seedance_25_model", "seedance_20_model", "minimax_model"):
            if key in clean and not clean[key]:
                raise ConfigError("模型 ID 不能为空。")
        for key in ("ark_base_url", "minimax_base_url", "seedance_25_model", "seedance_20_model", "minimax_model"):
            if key in clean:
                clean[key] = clean[key].rstrip("/") if key.endswith("_url") else clean[key]
        clean["s3_prefix"] = clean.get("s3_prefix", self.settings.s3_prefix).strip("/")
        clean["s3_public_base_url"] = clean.get("s3_public_base_url", self.settings.s3_public_base_url).rstrip("/")
        clean["ark_base_url"] = clean.get("ark_base_url", self.settings.ark_base_url).rstrip("/")
        clean["minimax_base_url"] = clean.get("minimax_base_url", self.settings.minimax_base_url).rstrip("/")
        return clean

    @staticmethod
    def _is_https(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password

    def _write(self, values: dict[str, str]) -> None:
        path = self.settings.config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(values, handle, ensure_ascii=False, indent=2)
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
        except OSError as exc:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise ConfigError("无法保存本地配置，请检查 data 目录写入权限。") from exc
