import io

import pytest
from PIL import Image

from app.schemas import InputError, inspect_image, validate_parameters


def png(width=640, height=480):
    stream = io.BytesIO()
    Image.new("RGB", (width, height), "#8d9d74").save(stream, format="PNG")
    return stream.getvalue()


def test_valid_image():
    media_type, extension, width, height = inspect_image(png(), "seedance-2.5")
    assert (media_type, extension, width, height) == ("image/png", ".png", 640, 480)


@pytest.mark.parametrize("width,height", [(200, 480), (7000, 480), (2000, 300)])
def test_invalid_dimensions(width, height):
    with pytest.raises(InputError):
        inspect_image(png(width, height), "seedance-2.5")


def test_image_content_not_filename():
    with pytest.raises(InputError, match="无法读取图片"):
        inspect_image(b"not a png", "minimax-h3")


def test_empty_and_too_large():
    with pytest.raises(InputError, match="请选择"):
        inspect_image(b"", "seedance-2.5")
    with pytest.raises(InputError, match="30 MB"):
        inspect_image(b"x" * (30 * 1024 * 1024 + 1), "seedance-2.5")


@pytest.mark.parametrize("model,duration,resolution", [
    ("seedance-2.5", 31, "720p"),
    ("seedance-2.0", 16, "720p"),
    ("seedance-2.0", 10, "2K"),
    ("minimax-h3", 5, "1080p"),
    ("minimax-h3", 3, "768P"),
    ("unknown", 5, "720p"),
])
def test_invalid_parameters(model, duration, resolution):
    with pytest.raises(InputError):
        validate_parameters(model, "镜头推进", duration, resolution)


def test_prompt_required():
    with pytest.raises(InputError, match="提示词"):
        validate_parameters("seedance-2.5", "  ", 5, "720p")
