# OpenVideo Local

OpenVideo Local is a self-hosted cinematic video-generation studio that does not require a paid generation API. Its flagship renderer uses the Apache-2.0-licensed **Wan 2.2 TI2V-5B** model for text-to-video and image-guided video generation.

This project is an original interface and orchestration layer. It is not Kling, Runway, or Higgsfield, and it does not copy their branding or proprietary models.

## What is implemented

- Responsive local web studio
- Prompt, negative prompt, aspect, seed, and quality presets
- Multi-shot storyboards with last-frame visual continuity
- Resumable per-shot artifacts that skip completed renders after interruption
- Optional OpenAI-compatible local Kokoro narration
- FFmpeg 1080p mastering and motion-compensated 30 fps conversion
- Persistent SQLite render queue
- Separate GPU worker with graceful shutdown
- Wan 2.2 lazy loading and CPU-offload support
- Job progress, cancellation, status, and MP4 retrieval APIs
- Docker Compose separation between the lightweight UI/API and GPU renderer
- Hardware doctor and input-validation tests
- No paid API or credit system

## Hardware truth

The official Wan 2.2 repository documents the TI2V-5B 720p path on a GPU with at least 24 GB VRAM. The model download is approximately 34 GB. A practical quality worker should have:

- NVIDIA RTX 4090 / RTX 5090 / RTX 6000-class GPU with 24 GB+ VRAM
- 64 GB system RAM recommended
- 100 GB+ free SSD storage
- Current NVIDIA driver and Docker GPU support

The web app can run on an ordinary laptop. The current development PC (8 GB RAM, no detected NVIDIA GPU) cannot execute the flagship model. It can submit jobs to a worker on the same LAN by sharing the queue volume/database, but a production deployment should move the queue to Postgres or Redis before using separate hosts.

## Start the interface

```bash
cp .env.example .env
docker compose up --build api
```

Open <http://localhost:7860>.

## Start the local GPU worker

Install NVIDIA Container Toolkit, verify `nvidia-smi`, then run:

```bash
docker compose --profile gpu up --build
```

Download the official model once, then start the worker:

```bash
docker compose --profile setup run --rm model-setup
docker compose --profile gpu up --build
```

No provider API key is required. `OPENVIDEO_WAN_ENGINE=official` is the default and supports both text and image-guided generation. The `diffusers` alternative is text-only for this checkpoint.

## Local Python development

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e .
python -m uvicorn app.main:app --reload --port 7860
```

GPU worker dependencies:

```bash
pip install -e ".[worker]"
set OPENVIDEO_BACKEND=wan22
python -m app.worker
```

Install the official GitHub runtime and model on a non-Docker worker with:

```bash
python scripts/bootstrap_wan.py --repo-dir /opt/Wan2.2 --model-dir /models/Wan2.2-TI2V-5B
```

For narration, run a self-hosted Kokoro server that exposes the OpenAI-compatible `/v1/audio/speech` endpoint, then set:

```bash
OPENVIDEO_KOKORO_URL=http://your-kokoro-host:8880
OPENVIDEO_KOKORO_VOICE=af_heart
```

## API

- `GET /api/health`
- `GET /api/capabilities`
- `GET /api/jobs`
- `POST /api/jobs`
- `POST /api/storyboards`
- `GET /api/jobs/{id}`
- `POST /api/jobs/{id}/cancel`
- `GET /api/jobs/{id}/video`

Example:

```json
{
  "prompt": "A probe descends through the amber clouds of Venus, turbulent atmosphere rolling around the camera, cinematic scale",
  "negative_prompt": "flicker, morphing, duplicate objects",
  "aspect": "vertical",
  "preset": "cinematic",
  "seed": 42
}
```

## Quality roadmap

The next production layers are per-shot reference-image uploads in the storyboard editor, optional Real-ESRGAN enhancement, music and sound-effect lanes, caption rendering, and a Postgres/Redis queue for multiple team workers.

## Licensing

The application code will be released under Apache-2.0. Model weights are not bundled. Downloaded models and optional components retain their own licenses; review them before commercial use. Wan 2.2 is listed as Apache-2.0 by its official repository and model card.

## Sources

- [Wan 2.2 official repository](https://github.com/Wan-Video/Wan2.2)
- [Wan 2.2 TI2V-5B Diffusers model](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers)
- [Hugging Face Diffusers Wan documentation](https://huggingface.co/docs/diffusers/api/pipelines/wan)
