import shutil
import tempfile
import unittest
from pathlib import Path

from app.config import settings
from app.narration import NarrationError, synthesize


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.content


class NarrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.old_url = settings.kokoro_url
        object.__setattr__(settings, "kokoro_url", "http://local-kokoro")

    def tearDown(self):
        object.__setattr__(settings, "kokoro_url", self.old_url)
        shutil.rmtree(self.root, ignore_errors=True)

    def test_accepts_valid_local_wav(self):
        wav = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + bytes(36)
        output = synthesize(
            "A year on Venus ends before a day.",
            self.root / "voice.wav",
            opener=lambda *_args, **_kwargs: FakeResponse(wav),
        )
        self.assertEqual(output.read_bytes(), wav)

    def test_rejects_non_wav_response(self):
        with self.assertRaises(NarrationError):
            synthesize(
                "This should not be accepted as narration.",
                self.root / "voice.wav",
                opener=lambda *_args, **_kwargs: FakeResponse(b"not audio" * 10),
            )


if __name__ == "__main__":
    unittest.main()

