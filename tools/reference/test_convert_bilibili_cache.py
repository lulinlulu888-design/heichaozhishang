"""Data-safety regression with three-second synthetic, disposable cache files.

Set FFMPEG_PATH and FFPROBE_PATH if the executables are not on PATH.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CONVERTER = Path(__file__).with_name("convert_bilibili_cache.py")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(arguments: list, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(value) for value in arguments], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


class CacheDataSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
        cls.ffprobe = os.environ.get("FFPROBE_PATH") or shutil.which("ffprobe")
        if not cls.ffmpeg or not cls.ffprobe:
            raise unittest.SkipTest("Provide local FFMPEG_PATH and FFPROBE_PATH to run the media regression")
        cls.workspace = tempfile.TemporaryDirectory(prefix="hczs-video-reference-test-")
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.root = Path(cls.workspace.name)
        video, audio = cls.root / "video.mp4", cls.root / "audio.mp4"
        commands = [
            [cls.ffmpeg, "-v", "error", "-nostdin", "-n", "-f", "lavfi", "-i",
             "testsrc2=size=320x180:rate=12", "-t", "3", "-an", "-c:v", "mpeg4", "-q:v", "5", video],
            [cls.ffmpeg, "-v", "error", "-nostdin", "-n", "-f", "lavfi", "-i",
             "sine=frequency=440:sample_rate=48000", "-t", "3", "-vn", "-c:a", "aac", audio],
        ]
        for command in commands:
            result = execute(command)
            if result.returncode:
                raise RuntimeError(f"Synthetic media generation failed: {result.stderr}")
        cls.video_bytes = video.read_bytes()
        cls.audio_bytes = audio.read_bytes()

    def setUp(self):
        self.case = self.root / self._testMethodName
        self.cache = self.case / "缓存 & cache"
        self.source = self.cache / "合成素材"
        self.source.mkdir(parents=True)
        self.output = self.case / "参考输出"
        self.destination = self.output / "BV_SYNTHETIC_3"
        # File names deliberately do not identify track types.
        (self.source / "01.m4s").write_bytes(b"000000000" + self.audio_bytes)
        (self.source / "02.m4s").write_bytes(b"000000000" + self.video_bytes)
        total = sum(path.stat().st_size for path in self.source.glob("*.m4s"))
        self.metadata = {
            "status": "completed", "progress": 100, "loadedSize": total, "totalSize": total,
            "duration": 3, "title": "合成回归 & 本地素材", "bvid": "BV_SYNTHETIC", "cid": 3,
        }
        self.write_metadata()
        self.original_hashes = self.source_hashes()

    def write_metadata(self):
        (self.source / "videoInfo.json").write_text(json.dumps(self.metadata, ensure_ascii=False), encoding="utf-8")

    def source_hashes(self) -> dict:
        return {path.name: digest(path) for path in self.source.iterdir() if path.is_file()}

    def convert(self, expected_status: str, expected_exit: int = 0):
        result = execute([
            sys.executable, "-X", "utf8", CONVERTER,
            "--cache-root", self.cache, "--output-root", self.output,
            "--ffmpeg", self.ffmpeg, "--ffprobe", self.ffprobe,
            "--stable-seconds", "0", "--frame-interval", "1",
        ])
        self.assertEqual(result.returncode, expected_exit, result.stdout + result.stderr)
        index = json.loads((self.output / "conversion-index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index["entries"]), 1)
        self.assertEqual(index["entries"][0]["status"], expected_status, index)
        self.assertEqual(self.source_hashes(), self.original_hashes, "Original cache bytes changed")
        return index["entries"][0]

    def movie_fingerprint(self):
        movie = self.destination / "reference.mp4"
        return digest(movie), movie.stat().st_mtime_ns

    def test_conversion_preserves_original_sha(self):
        self.convert("converted")
        manifest = json.loads((self.destination / "reference.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["verification"]["fullDecode"])
        self.assertEqual(len(manifest["frames"]), 3)
        observed = execute([self.ffprobe, "-v", "error", "-show_streams", "-of", "json", self.destination / "reference.mp4"])
        self.assertEqual(observed.returncode, 0, observed.stderr)
        streams = json.loads(observed.stdout)["streams"]
        self.assertCountEqual([stream["codec_type"] for stream in streams], ["video", "audio"])

    def test_repeat_does_not_replace_movie(self):
        self.convert("converted")
        before = self.movie_fingerprint()
        self.convert("unchanged")
        self.assertEqual(self.movie_fingerprint(), before)

    def test_bad_jpeg_is_repaired(self):
        self.convert("converted")
        image = self.destination / "frames" / "000001.jpg"
        image.write_bytes(b"broken-jpeg")
        before = self.movie_fingerprint()
        self.convert("unchanged")
        self.assertEqual(self.movie_fingerprint(), before)
        self.assertNotEqual(image.read_bytes(), b"broken-jpeg")
        decoded = execute([self.ffmpeg, "-v", "error", "-xerror", "-nostdin", "-i", image,
                           "-frames:v", "1", "-f", "null", "-"])
        self.assertEqual(decoded.returncode, 0, decoded.stderr)
        self.assertFalse(decoded.stderr.strip(), decoded.stderr)
        self.assertFalse(list(image.parent.glob("*.pending.jpg")))

    def test_pending_manifest_recovers_without_remux(self):
        self.convert("converted")
        manifest = self.destination / "reference.json"
        pending = self.destination / "reference.pending.json"
        manifest.replace(pending)
        before = self.movie_fingerprint()
        self.convert("unchanged")
        self.assertEqual(self.movie_fingerprint(), before)
        self.assertTrue(manifest.is_file())
        self.assertFalse(pending.exists())
        self.assertTrue(json.loads(manifest.read_text(encoding="utf-8"))["verification"]["fullDecode"])

    def test_unknown_header_is_rejected_without_source_change(self):
        (self.source / "02.m4s").write_bytes(b"XXXXXXXXX" + self.video_bytes)
        self.original_hashes = self.source_hashes()
        result = self.convert("error", expected_exit=1)
        self.assertIn("Unrecognized media header", result["reason"])
        self.assertFalse((self.destination / "reference.mp4").exists())

    def test_downloading_entry_is_skipped(self):
        self.metadata.update(status="downloading", progress=30, loadedSize=self.metadata["totalSize"] // 3)
        self.write_metadata()
        self.original_hashes = self.source_hashes()
        self.convert("skipped")
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
