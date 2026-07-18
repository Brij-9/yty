import shutil
import tempfile
import unittest
from pathlib import Path

from app.config import settings
from app.database import JobStore
from app.domain import StoryboardSpec
from app.worker import render_storyboard


class FakeBackend:
    def __init__(self):
        self.calls = []

    def generate(self, spec, output, progress):
        self.calls.append(spec)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"synthetic-test-clip")
        progress(100)
        return output


class StoryboardWorkerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.old_output = settings.output_dir
        self.old_mastering = settings.mastering
        self.old_kokoro = settings.kokoro_url
        object.__setattr__(settings, "output_dir", self.root / "outputs")
        object.__setattr__(settings, "mastering", False)
        settings.output_dir.mkdir(parents=True)
        self.store = JobStore(self.root / "jobs.db")
        self.spec = StoryboardSpec.from_payload({
            "title": "Venus continuity",
            "seed": 20,
            "captions": False,
            "shots": [
                {"prompt": "A wide orbital view of a probe approaching the planet Venus"},
                {"prompt": "The same probe enters the planet's turbulent amber atmosphere"},
                {"prompt": "The probe emerges beneath the clouds above a volcanic landscape"},
            ],
        })
        self.job = self.store.create(self.spec.to_dict())
        self.store.update(self.job["id"], status="running")

    def tearDown(self):
        object.__setattr__(settings, "output_dir", self.old_output)
        object.__setattr__(settings, "mastering", self.old_mastering)
        object.__setattr__(settings, "kokoro_url", self.old_kokoro)
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def extractor(_clip, image):
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"last-frame")
        return image

    @staticmethod
    def assembler(clips, output):
        assert len(clips) >= 2
        output.write_bytes(b"assembled")
        return output

    def test_renders_and_resumes_per_shot_artifacts(self):
        first_backend = FakeBackend()
        output = render_storyboard(
            self.job["id"], self.spec, self.store, first_backend,
            assembler=self.assembler, frame_extractor=self.extractor,
        )
        self.assertEqual(output.read_bytes(), b"assembled")
        self.assertEqual(len(first_backend.calls), 3)
        saved = self.store.get(self.job["id"])
        self.assertEqual(len(saved["artifacts"]["shots"]), 3)
        self.assertTrue(all(item["status"] == "completed" for item in saved["artifacts"]["shots"]))

        resumed_backend = FakeBackend()
        render_storyboard(
            self.job["id"], self.spec, self.store, resumed_backend,
            assembler=self.assembler, frame_extractor=self.extractor,
        )
        self.assertEqual(resumed_backend.calls, [])
        resumed = self.store.get(self.job["id"])
        self.assertTrue(all(item["resumed"] for item in resumed["artifacts"]["shots"]))

    def test_integrates_narration_music_captions_and_mastering(self):
        music = self.root / "score.wav"
        music.write_bytes(b"music")
        spec = StoryboardSpec.from_payload({
            "title": "Finished Venus sequence",
            "music_path": str(music),
            "music_volume": 0.1,
            "captions": True,
            "shots": [
                {"prompt": "A spacecraft approaches Venus in a wide orbital tracking shot", "narration": "Venus turns incredibly slowly."},
                {"prompt": "The same spacecraft enters turbulent amber atmospheric clouds", "narration": "Its year ends before one rotation."},
            ],
        })
        job = self.store.create(spec.to_dict())
        self.store.update(job["id"], status="running")
        object.__setattr__(settings, "mastering", True)
        object.__setattr__(settings, "kokoro_url", "http://local-kokoro")

        def narrator(_text, output):
            output.write_bytes(b"wav")
            return output

        def sound_mixer(_video, output, **kwargs):
            self.assertEqual(kwargs["music"], music)
            self.assertEqual(kwargs["music_volume"], 0.1)
            output.write_bytes(b"mixed")
            return output

        def caption_writer(_clips, narrations, output):
            self.assertEqual(len(narrations), 2)
            output.write_text("captions", encoding="utf-8")
            return output

        def masterer(_video, output, aspect, captions=None):
            self.assertEqual(aspect, "vertical")
            self.assertTrue(captions.is_file())
            output.write_bytes(b"mastered")
            return output

        output = render_storyboard(
            job["id"], spec, self.store, FakeBackend(),
            assembler=self.assembler, frame_extractor=self.extractor,
            narrator=narrator, sound_mixer=sound_mixer,
            caption_writer=caption_writer, masterer=masterer,
        )
        self.assertEqual(output.read_bytes(), b"mastered")
        artifacts = self.store.get(job["id"])["artifacts"]
        self.assertEqual(artifacts["audio_mix"]["status"], "completed")
        self.assertEqual(artifacts["captions"]["status"], "completed")
        self.assertEqual(artifacts["mastering"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
