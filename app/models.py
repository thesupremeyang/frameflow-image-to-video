from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModelName = Literal["seedance-2.5", "seedance-2.0", "minimax-h3"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]

MODEL_SPECS = {
    "seedance-2.5": {
        "name": "Seedance 2.5", "provider": "火山方舟", "durations": (4, 30),
        "resolutions": ("480p", "720p", "1080p"), "default_resolution": "720p",
        "audio": True, "minimum_dimension": 300, "maximum_dimension": 6000,
        "ratio": (0.4, 2.5), "formats": ("JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF", "HEIC", "HEIF"),
    },
    "seedance-2.0": {
        "name": "Seedance 2.0", "provider": "火山方舟", "durations": (4, 15),
        "resolutions": ("480p", "720p", "1080p", "4k"), "default_resolution": "720p",
        "audio": True, "minimum_dimension": 300, "maximum_dimension": 6000,
        "ratio": (0.4, 2.5), "formats": ("JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF", "HEIC", "HEIF"),
    },
    "minimax-h3": {
        "name": "MiniMax H3", "provider": "MiniMax", "durations": (4, 15),
        "resolutions": ("768P", "2K"), "default_resolution": "768P",
        "audio": False, "minimum_dimension": 256, "maximum_dimension": 5760,
        "ratio": (0.4, 2.5), "formats": ("JPEG", "PNG", "WEBP", "HEIC", "HEIF"),
    },
}


@dataclass
class Generation:
    id: str
    model: str
    prompt: str
    duration: int
    resolution: str
    generate_audio: bool
    image_path: str
    image_media_type: str
    status: str
    created_at: str
    updated_at: str
    remote_id: str | None = None
    video_url: str | None = None
    local_video_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "model": self.model, "model_name": MODEL_SPECS[self.model]["name"],
            "prompt": self.prompt, "duration": self.duration, "resolution": self.resolution,
            "generate_audio": self.generate_audio, "status": self.status,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "image_url": f"/api/generations/{self.id}/image",
            "video_url": f"/api/generations/{self.id}/video" if self.local_video_path else None,
            "download_url": f"/api/generations/{self.id}/download" if self.status == "succeeded" else None,
            "error": self.error,
        }
