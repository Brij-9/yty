from __future__ import annotations

import uuid
import wave
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.database import JobStore
from app.domain import ASPECTS, PRESETS, GenerationSpec, StoryboardSpec, ValidationError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
settings.ensure_directories()
store = JobStore(settings.database)

app = FastAPI(title="OpenVideo Local", version="0.1.0")
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "backend": settings.backend, "worker_required": True}


@app.get("/api/capabilities")
def capabilities():
    return {
        "model": settings.wan_model,
        "engine": settings.wan_engine,
        "license": "Apache-2.0",
        "aspects": ASPECTS,
        "presets": PRESETS,
        "hardware": {"recommended_gpu_vram_gb": 24, "recommended_system_ram_gb": 64},
        "mastering": {"enabled": settings.mastering, "target_fps": settings.target_fps, "output": "1080p"},
        "paid_api_required": False,
    }


@app.get("/api/jobs")
def list_jobs():
    return store.list()


@app.post("/api/uploads", status_code=201)
async def create_upload(file: UploadFile = File(...)):
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    suffix = allowed.get(file.content_type or "")
    if not suffix:
        raise HTTPException(415, "Only JPEG, PNG, and WebP reference images are accepted.")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "Reference image exceeds 20 MB.")
    path = settings.upload_dir / f"{uuid.uuid4()}{suffix}"
    path.write_bytes(content)
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            if width < 512 or height < 512 or width > 8192 or height > 8192:
                raise HTTPException(422, "Reference image dimensions must be between 512 and 8192 pixels.")
    except (UnidentifiedImageError, OSError):
        path.unlink(missing_ok=True)
        raise HTTPException(422, "The uploaded file is not a decodable image.")
    return {"path": str(path), "width": width, "height": height}


@app.post("/api/uploads/audio", status_code=201)
async def create_audio_upload(file: UploadFile = File(...)):
    if file.content_type not in {"audio/wav", "audio/x-wav", "audio/wave"}:
        raise HTTPException(415, "Only decoded PCM WAV soundtrack uploads are accepted.")
    content = await file.read(100 * 1024 * 1024 + 1)
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(413, "Soundtrack exceeds 100 MB.")
    try:
        with wave.open(BytesIO(content), "rb") as audio:
            channels = audio.getnchannels()
            rate = audio.getframerate()
            width = audio.getsampwidth()
            duration = audio.getnframes() / max(rate, 1)
    except (wave.Error, EOFError):
        raise HTTPException(422, "The soundtrack is not a decodable PCM WAV file.")
    if channels not in {1, 2} or width not in {1, 2, 3, 4} or not 16000 <= rate <= 96000:
        raise HTTPException(422, "Soundtrack must be mono/stereo PCM WAV at 16–96 kHz.")
    if not 0.5 <= duration <= 600:
        raise HTTPException(422, "Soundtrack duration must be between 0.5 seconds and 10 minutes.")
    path = settings.upload_dir / f"{uuid.uuid4()}.wav"
    path.write_bytes(content)
    return {"path": str(path), "duration": round(duration, 3), "sample_rate": rate, "channels": channels}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/jobs", status_code=202)
def create_job(payload: dict):
    try:
        spec = GenerationSpec.from_payload(payload)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    _validate_source_image(spec.source_image)
    return store.create(spec.__dict__)


@app.post("/api/storyboards", status_code=202)
def create_storyboard(payload: dict):
    try:
        spec = StoryboardSpec.from_payload(payload)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    for shot in spec.shots:
        _validate_source_image(shot.source_image)
    _validate_audio(spec.music_path)
    return store.create(spec.to_dict())


def _validate_source_image(value: str | None) -> None:
    if not value:
        return
    source = Path(value).resolve()
    upload_root = settings.upload_dir.resolve()
    if upload_root not in source.parents or not source.is_file():
        raise HTTPException(422, "Reference image must be an existing OpenVideo upload.")


def _validate_audio(value: str | None) -> None:
    if not value:
        return
    source = Path(value).resolve()
    upload_root = settings.upload_dir.resolve()
    if upload_root not in source.parents or not source.is_file() or source.suffix.lower() != ".wav":
        raise HTTPException(422, "Soundtrack must be an existing OpenVideo WAV upload.")


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = store.cancel(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] not in {"failed", "cancelled"}:
        raise HTTPException(409, "Only failed or cancelled jobs can be retried")
    return store.retry(job_id)


@app.get("/api/jobs/{job_id}/video")
def job_video(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "completed" or not job["output_path"]:
        raise HTTPException(409, "Video is not ready")
    path = Path(job["output_path"])
    if not path.is_file():
        raise HTTPException(410, "Video artifact is missing")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
