import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.postprocess import mix_soundtrack, write_storyboard_captions


class PostprocessTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_writes_timed_storyboard_captions(self):
        clips = [self.root / "01.mp4", self.root / "02.mp4"]
        with patch("app.postprocess.probe_duration", side_effect=[3.0, 4.0]):
            output = write_storyboard_captions(
                clips,
                ["Venus turns incredibly slowly.", "Its year ends before one full rotation."],
                self.root / "captions.srt",
            )
        text = output.read_text(encoding="utf-8")
        self.assertIn("00:00:00,120 --> 00:00:02,880", text)
        self.assertIn("00:00:03,120 --> 00:00:06,880", text)
        self.assertIn("Its year ends before one full", text)

    def test_music_mix_loops_and_limits_soundtrack(self):
        captured = {}

        def fake_run(command, **_kwargs):
            captured["command"] = command
            return type("Result", (), {"returncode": 0, "stderr": ""})()

        with patch("app.postprocess._ffmpeg", return_value="ffmpeg"), patch(
            "app.postprocess.subprocess.run", side_effect=fake_run
        ):
            mix_soundtrack(
                self.root / "video.mp4",
                self.root / "mixed.mp4",
                music=self.root / "score.wav",
                music_volume=0.1,
            )
        self.assertIn("-stream_loop", captured["command"])
        filter_value = captured["command"][captured["command"].index("-filter_complex") + 1]
        self.assertIn("volume=0.100", filter_value)
        self.assertIn("alimiter", filter_value)


if __name__ == "__main__":
    unittest.main()

