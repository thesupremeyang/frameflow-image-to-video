from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings
from app.providers.base import ProviderError


class S3ImageStorage:
    def __init__(self, settings: Settings):
        if not settings.s3_ready:
            raise ProviderError("MiniMax 需要在“模型配置”中填写完整的 S3 图片存储信息。")
        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_prefix.strip("/")
        self.public_base_url = settings.s3_public_base_url.rstrip("/")
        parsed = urlparse(self.public_base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ProviderError("S3 公开访问地址必须是 HTTPS 地址。")
        self.client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region or "auto",
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                          connect_timeout=15, read_timeout=45, retries={"max_attempts": 2}),
        )

    def upload(self, path: Path, media_type: str) -> str:
        key = f"{self.prefix}/{uuid4().hex}{path.suffix.lower()}"
        try:
            self.client.upload_file(str(path), self.bucket, key, ExtraArgs={"ContentType": media_type})
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ProviderError("图片上传到 S3 失败，请检查存储配置、权限和网络。") from exc
        return f"{self.public_base_url}/{quote(key)}"
