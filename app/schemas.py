from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()

from app.models import MODEL_SPECS

MAX_IMAGE_BYTES = 30 * 1024 * 1024
MEDIA_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp",
               "BMP": "image/bmp", "TIFF": "image/tiff", "GIF": "image/gif",
               "HEIC": "image/heic", "HEIF": "image/heif"}
EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp",
              "TIFF": ".tiff", "GIF": ".gif", "HEIC": ".heic", "HEIF": ".heif"}


class InputError(ValueError):
    pass


def validate_parameters(model: str, prompt: str, duration: int, resolution: str) -> None:
    if model not in MODEL_SPECS:
        raise InputError("请选择支持的视频模型。")
    if not prompt.strip():
        raise InputError("请填写视频生成提示词。")
    if len(prompt) > 10000:
        raise InputError("提示词不能超过 10000 个字符。")
    spec = MODEL_SPECS[model]
    low, high = spec["durations"]
    if not low <= duration <= high:
        raise InputError(f"{spec['name']} 的视频时长应为 {low}-{high} 秒。")
    if resolution not in spec["resolutions"]:
        raise InputError("当前模型不支持所选清晰度。")


def inspect_image(content: bytes, model: str) -> tuple[str, str, int, int]:
    if not content:
        raise InputError("请选择一张图片。")
    if len(content) > MAX_IMAGE_BYTES:
        raise InputError("图片不能超过 30 MB。")
    spec = MODEL_SPECS[model]
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            image_format = image.format or ""
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise InputError("无法读取图片，请选择有效的图片文件。") from exc
    if image_format not in spec["formats"]:
        raise InputError(f"{spec['name']} 不支持这种图片格式。")
    minimum, maximum = spec["minimum_dimension"], spec["maximum_dimension"]
    if not minimum <= width <= maximum or not minimum <= height <= maximum:
        raise InputError(f"{spec['name']} 要求图片宽、高均在 {minimum}-{maximum} 像素之间，当前为 {width} × {height}。")
    low, high = spec["ratio"]
    if not low <= width / height <= high:
        raise InputError(f"{spec['name']} 要求图片宽高比在 0.4 到 2.5 之间。")
    return MEDIA_TYPES[image_format], EXTENSIONS[image_format], width, height
