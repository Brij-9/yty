from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("OPENVIDEO_DATA_DIR", "data"))
    database: Path = Path(os.getenv("OPENVIDEO_DATABASE", "data/openvideo.db"))
    output_dir: Path = Path(os.getenv("OPENVIDEO_OUTPUT_DIR", "data/outputs"))
    upload_dir: Path = Path(os.getenv("OPENVIDEO_UPLOAD_DIR", "data/uploads"))
    backend: str = os.getenv("OPENVIDEO_BACKEND", "doctor")
    worker_poll_seconds: float = float(os.getenv("OPENVIDEO_WORKER_POLL_SECONDS", "2"))
    wan_model: str = os.getenv("OPENVIDEO_WAN_MODEL", "Wan-AI/Wan2.2-TI2V-5B-Diffusers")
    wan_engine: str = os.getenv("OPENVIDEO_WAN_ENGINE", "official")
    wan_repo: Path = Path(os.getenv("OPENVIDEO_WAN_REPO", "/opt/Wan2.2"))
    wan_checkpoint: Path = Path(os.getenv("OPENVIDEO_WAN_CHECKPOINT", "/models/Wan2.2-TI2V-5B"))
    device: str = os.getenv("OPENVIDEO_DEVICE", "cuda")
    dtype: str = os.getenv("OPENVIDEO_DTYPE", "bfloat16")
    cpu_offload: bool = _bool("OPENVIDEO_CPU_OFFLOAD", True)
    ffmpeg: str = os.getenv("OPENVIDEO_FFMPEG", "ffmpeg")
    ffprobe: str = os.getenv("OPENVIDEO_FFPROBE", "ffprobe")
    realesrgan: str = os.getenv("OPENVIDEO_REALESRGAN", "")
    mastering: bool = _bool("OPENVIDEO_MASTERING", True)
    target_fps: int = int(os.getenv("OPENVIDEO_TARGET_FPS", "30"))
    kokoro_url: str = os.getenv("OPENVIDEO_KOKORO_URL", "").rstrip("/")
    kokoro_voice: str = os.getenv("OPENVIDEO_KOKORO_VOICE", "af_heart")

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.database.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
