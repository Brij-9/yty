import io
import os
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

from PIL import Image

_root = Path(tempfile.mkdtemp())
os.environ["OPENVIDEO_DATA_DIR"] = str(_root)
os.environ["OPENVIDEO_DATABASE"] = str(_root / "openvideo.db")
os.environ["OPENVIDEO_OUTPUT_DIR"] = str(_root / "outputs")
os.environ["OPENVIDEO_UPLOAD_DIR"] = str(_root / "uploads")

from fastapi.testclient import TestClient
from app.main import app, store


def tearDownModule():
    shutil.rmtree(_root, ignore_errors=True)


class ApiTests(unittest.TestCase):
    client = TestClient(app)

    def test_health_and_capabilities(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        capabilities = self.client.get("/api/capabilities").json()
        self.assertFalse(capabilities["paid_api_required"])
        self.assertEqual(capabilities["license"], "Apache-2.0")

    def test_create_and_fetch_job(self):
        response = self.client.post("/api/jobs", json={
            "prompt": "A cinematic probe descends through the turbulent clouds of Venus",
            "aspect": "vertical",
            "preset": "preview",
            "seed": 42,
        })
        self.assertEqual(response.status_code, 202)
        job = response.json()
        fetched = self.client.get(f"/api/jobs/{job['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["status"], "queued")

    def test_upload_and_image_guided_job(self):
        buffer = io.BytesIO()
        Image.new("RGB", (768, 768), "#c96f32").save(buffer, "PNG")
        upload = self.client.post(
            "/api/uploads",
            files={"file": ("venus.png", buffer.getvalue(), "image/png")},
        )
        self.assertEqual(upload.status_code, 201)
        source = upload.json()["path"]
        response = self.client.post("/api/jobs", json={
            "prompt": "Animate this Venus probe with coherent atmospheric motion",
            "source_image": source,
        })
        self.assertEqual(response.status_code, 202)

    def test_rejects_arbitrary_source_path(self):
        response = self.client.post("/api/jobs", json={
            "prompt": "Animate this untrusted source image with cinematic motion",
            "source_image": str(_root.parent / "outside.png"),
        })
        self.assertEqual(response.status_code, 422)

    def test_create_storyboard(self):
        response = self.client.post("/api/storyboards", json={
            "title": "Venus descent",
            "aspect": "vertical",
            "preset": "balanced",
            "seed": 99,
            "continuity": True,
            "shots": [
                {"prompt": "A spacecraft approaches Venus in a wide orbital shot"},
                {"prompt": "The same craft descends into dense amber cloud layers"},
            ],
        })
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["spec"]["kind"], "storyboard")

    def test_retry_failed_job(self):
        created = self.client.post("/api/jobs", json={
            "prompt": "A camera glides smoothly above an alien volcanic landscape",
        }).json()
        store.update(created["id"], status="failed", error="temporary worker error")
        response = self.client.post(f"/api/jobs/{created['id']}/retry")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")
        self.assertIsNone(response.json()["error"])

    def test_upload_soundtrack_and_queue_storyboard(self):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(48000)
            audio.writeframes(bytes(48000 * 2 * 2))
        upload = self.client.post(
            "/api/uploads/audio",
            files={"file": ("score.wav", buffer.getvalue(), "audio/wav")},
        )
        self.assertEqual(upload.status_code, 201)
        response = self.client.post("/api/storyboards", json={
            "title": "Scored Venus sequence",
            "music_path": upload.json()["path"],
            "music_volume": 0.1,
            "shots": [
                {"prompt": "A spacecraft approaches Venus under sharp cinematic sunlight"},
                {"prompt": "The spacecraft enters the turbulent orange atmosphere"},
            ],
        })
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["spec"]["music_volume"], 0.1)



if __name__ == "__main__":
    unittest.main()
