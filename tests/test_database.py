import shutil
import tempfile
import unittest
from pathlib import Path

from app.database import JobStore


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.store = JobStore(self.root / "jobs.db")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_requeues_interrupted_jobs_without_losing_artifacts(self):
        job = self.store.create({"prompt": "A sufficiently long generation prompt"})
        artifacts = {"shots": [{"status": "completed", "clip": "01.mp4"}]}
        self.store.update(job["id"], status="running", progress=45, artifacts=artifacts)
        self.assertEqual(self.store.recover_interrupted(), 1)
        recovered = self.store.get(job["id"])
        self.assertEqual(recovered["status"], "queued")
        self.assertEqual(recovered["progress"], 45)
        self.assertEqual(recovered["artifacts"], artifacts)


if __name__ == "__main__":
    unittest.main()

