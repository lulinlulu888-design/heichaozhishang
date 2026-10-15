"""Convert completed Bilibili PC caches locally, without changing the downloads.

Only the observed nine ASCII-zero prefix is removed, and only before an ISO
BMFF ftyp box. Audio/video are identified with ffprobe, never by file size.
No login, network request, .playurl, or danmaku file is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[2]
PREFIX = b"000000000"


def emit(message):
    print(message, flush=True)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, value):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot(paths):
    return [(str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns) for p in paths]


def media_offset(path):
    with path.open("rb") as stream:
        header = stream.read(48)
    offset = len(PREFIX) if header.startswith(PREFIX) else 0
    body = header[offset:]
    if len(body) < 16 or body[4:8] != b"ftyp" or not 16 <= int.from_bytes(body[:4], "big") <= path.stat().st_size - offset:
        raise ValueError(f"Unrecognized media header: {path.name}; left untouched")
    return offset


def run(command, timeout=900):
    completed = subprocess.run(
        [str(item) for item in command], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if completed.returncode:
        raise RuntimeError(f"{Path(command[0]).name} failed ({completed.returncode}): {completed.stderr[-2000:]}")
    return completed


def resolve_tool(name, explicit):
    candidates = [explicit, os.environ.get(name.upper() + "_PATH"), shutil.which(name)]
    candidates.extend(sorted((PROJECT / "tools/runtime").glob(f"ffmpeg*/**/{name}.exe")))
    for item in candidates:
        if item and Path(item).is_file():
            return Path(item).resolve()
    raise FileNotFoundError(f"{name} not found. Supply --{name} <executable> or put it on PATH.")


def probe(ffprobe, path):
    data = run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    # Even when ffprobe exits successfully, damaged/truncated containers may warn.
    if data.stderr.strip():
        raise ValueError(f"Container errors in {path.name}: {data.stderr[-1200:]}")
    return json.loads(data.stdout)


def duration_of(info):
    return float(info["format"]["duration"])


def completion_problem(metadata, paths):
    if metadata.get("status") != "completed":
        return f"download {metadata.get('status', 'unknown')} ({metadata.get('progress', '?')}%)"
    if float(metadata.get("progress", 0)) < 100:
        return "progress is below 100%"
    if len(paths) != 2:
        return f"expected two local m4s tracks, found {len(paths)}"
    total = int(metadata.get("totalSize", 0))
    loaded = int(metadata.get("loadedSize", 0))
    if total <= 0 or loaded != total:
        return "download byte counts are incomplete"
    actual = sum(p.stat().st_size for p in paths)
    # Desktop metadata may include or exclude its artificial track prefixes.
    stripped = actual - sum(media_offset(p) for p in paths)
    if total not in (actual, stripped):
        return f"track size mismatch: metadata={total}, actual={actual}, payload={stripped}"
    return None


def normalized_identity(metadata, folder):
    bvid = str(metadata.get("bvid", "local"))
    cid = str(metadata.get("cid", folder.name))
    return re.sub(r"[^A-Za-z0-9_-]", "_", f"{bvid}_{cid}")


def copy_track(source, target):
    offset = media_offset(source)
    digest = hashlib.sha256()
    with source.open("rb") as original, target.open("xb") as repaired:
        digest.update(original.read(offset))
        for block in iter(lambda: original.read(4 * 1024 * 1024), b""):
            digest.update(block)
            repaired.write(block)
    return {"path": str(source.resolve()), "size": source.stat().st_size,
            "sha256": digest.hexdigest(), "removedPrefixBytes": offset}


def extract_frames(ffmpeg, video, destination, duration, interval, at=()):
    destination.mkdir(exist_ok=True)
    result = []
    times = sorted(set(range(0, max(1, math.floor(duration)), interval)) | {s for s in at if s < duration})
    for second in times:
        name = f"{int(second):06d}" if float(second).is_integer() else f"{second:010.3f}".replace(".", "_")
        image = destination / f"{name}.jpg"
        valid = False
        if image.is_file() and image.stat().st_size:
            try:
                checked = run([ffmpeg, "-hide_banner", "-v", "error", "-xerror", "-nostdin",
                               "-i", image, "-frames:v", "1", "-f", "null", "-"])
                valid = not checked.stderr.strip()
            except RuntimeError:
                pass
        if not valid:
            pending = image.with_name(image.stem + ".pending.jpg")
            # This exact private partial file belongs to this generated frame.
            pending.unlink(missing_ok=True)
            run([ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-n",
                 "-ss", second, "-i", video, "-map", "0:v:0", "-frames:v", "1",
                 "-q:v", "2", pending])
            if not pending.is_file() or pending.stat().st_size == 0:
                raise ValueError(f"No decoded frame at {second}s")
            pending.replace(image)
        if not image.is_file() or image.stat().st_size == 0:
            raise ValueError(f"No decoded frame at {second}s")
        result.append({"path": f"frames/{image.name}", "seconds": second})
    return result


def merge_frames(existing, generated):
    # Preserve deliberately chosen action reference frames across incremental runs.
    entries = {frame["path"]: frame for frame in existing + generated}
    return sorted(entries.values(), key=lambda frame: (frame["seconds"], frame["path"]))


def convert_one(folder, metadata, args, ffmpeg, ffprobe):
    tracks = sorted(folder.glob("*.m4s"))
    problem = completion_problem(metadata, tracks)
    if problem:
        return {"status": "skipped", "reason": problem}
    before = snapshot(tracks)
    time.sleep(args.stable_seconds)
    if snapshot(tracks) != before:
        return {"status": "skipped", "reason": "tracks are still being written"}
    destination = args.output_root / normalized_identity(metadata, folder)
    destination.mkdir(exist_ok=True)
    movie = destination / "reference.mp4"
    manifest = destination / "reference.json"
    pending_manifest = destination / "reference.pending.json"
    if not manifest.exists() and pending_manifest.exists() and movie.is_file():
        recovered = read_json(pending_manifest)
        if sha256(movie) != recovered.get("outputSha256"):
            raise ValueError("Interrupted conversion's movie does not match its pending manifest")
        pending_manifest.replace(manifest)
        emit("RECOVER completed conversion manifest")
    previous = read_json(manifest) if manifest.exists() else None
    if previous:
        same_source = previous.get("sourceSnapshot") == [list(s) for s in before]
        same_hashes = same_source and [sha256(p) for p in tracks] == [s["sha256"] for s in previous["sources"]]
        same_output = movie.is_file() and sha256(movie) == previous.get("outputSha256")
        if not (same_hashes and same_output and previous.get("verification", {}).get("fullDecode")):
            raise ValueError(f"Existing conversion differs: {destination}; choose a new --output-root")
        previous["frames"] = merge_frames(previous.get("frames", []), extract_frames(
            ffmpeg, movie, destination / "frames", previous["durationSeconds"], args.frame_interval, args.at))
        write_json(manifest, previous)
        return {"status": "unchanged", "video": str(movie), "frames": len(previous["frames"])}
    if movie.exists():
        raise FileExistsError(f"Untracked output exists; not overwriting {movie}")
    emit(f"CONVERT {metadata.get('title', folder.name)}")
    # Only a newly created private work directory is recursively cleaned up.
    with tempfile.TemporaryDirectory(prefix=".convert-", dir=destination) as work:
        work_path = Path(work).resolve()
        if not work_path.is_relative_to(destination.resolve()):
            raise ValueError("Temporary directory escaped output root")
        sources, inputs = [], {}
        for index, source in enumerate(tracks):
            repaired = work_path / f"track-{index}.mp4"
            sources.append(copy_track(source, repaired))
            details = probe(ffprobe, repaired)
            streams = details.get("streams", [])
            if len(streams) != 1 or streams[0]["codec_type"] not in ("video", "audio"):
                raise ValueError(f"Expected one video or audio stream: {source.name}")
            kind = streams[0]["codec_type"]
            if kind in inputs:
                raise ValueError(f"Duplicate {kind} tracks in {folder}")
            inputs[kind] = (repaired, details)
        if set(inputs) != {"video", "audio"}:
            raise ValueError("Need one video and one audio track")
        expected = float(metadata["duration"])
        if expected <= 0:
            raise ValueError("Invalid duration in download metadata")
        for kind, (_, details) in inputs.items():
            if abs(duration_of(details) - expected) > 2:
                raise ValueError(f"Incomplete {kind}: metadata={expected}s, track={duration_of(details)}s")
        pending = work_path / "reference.mp4"
        run([ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-n",
             "-i", inputs["video"][0], "-i", inputs["audio"][0],
             "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-map_metadata", "-1",
             "-movflags", "+faststart", pending])
        details = probe(ffprobe, pending)
        video = next(s for s in details["streams"] if s["codec_type"] == "video")
        audio = next(s for s in details["streams"] if s["codec_type"] == "audio")
        if abs(duration_of(details) - expected) > 2:
            raise ValueError("Remuxed duration differs from download metadata")
        if video["codec_name"] != inputs["video"][1]["streams"][0]["codec_name"] or audio["codec_name"] != inputs["audio"][1]["streams"][0]["codec_name"]:
            raise ValueError("Output codecs differ from source")
        emit(f"VERIFY full audio/video decode: {duration_of(details):.2f}s, {video['width']}x{video['height']}")
        verified = run([ffmpeg, "-hide_banner", "-v", "error", "-xerror", "-nostdin",
                        "-i", pending, "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
                       timeout=max(900, expected * 2))
        if verified.stderr.strip():
            raise ValueError(f"Decode reported errors: {verified.stderr[-1200:]}")
        if snapshot(tracks) != before:
            raise ValueError("Source changed during conversion; output discarded")
        document = {
            "schemaVersion": 1, "title": metadata.get("title", folder.name),
            "bvid": metadata.get("bvid"), "cid": metadata.get("cid"),
            "durationSeconds": duration_of(details),
            "video": {"path": "reference.mp4", "width": video["width"], "height": video["height"],
                      "codec": video["codec_name"], "fps": video.get("avg_frame_rate")},
            "audio": {"codec": audio["codec_name"], "sampleRate": audio.get("sample_rate")},
            "sources": sources, "sourceSnapshot": before,
            "outputSha256": sha256(pending), "frames": [],
            "verification": {"fullDecode": True, "streamCopy": True, "sourceUnchanged": True},
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        write_json(pending_manifest, document)
        pending.replace(movie)
        # Commit valid video provenance before optional frame extraction.
        pending_manifest.replace(manifest)
    emit("FRAMES extracting timestamped reference images")
    document["frames"] = extract_frames(ffmpeg, movie, destination / "frames", document["durationSeconds"], args.frame_interval, args.at)
    write_json(manifest, document)
    return {"status": "converted", "video": str(movie), "frames": len(document["frames"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, default=Path.home() / "Videos/bilibili")
    parser.add_argument("--output-root", type=Path, default=PROJECT / "analysis/video-references")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--only", action="append", default=[], help="Filter by CID, BVID, or cache folder name")
    parser.add_argument("--frame-interval", type=int, default=15, help="Seconds between full-resolution reference images")
    parser.add_argument("--at", action="append", type=float, default=[], help="Also capture this exact time in seconds; repeatable")
    parser.add_argument("--stable-seconds", type=float, default=1.0)
    parser.add_argument("--list", action="store_true", help="Inspect completion metadata only")
    args = parser.parse_args()
    if args.frame_interval < 1 or args.stable_seconds < 0:
        parser.error("frame-interval must be positive; stable-seconds must be nonnegative")
    if any(not math.isfinite(s) or s < 0 for s in args.at):
        parser.error("--at must be a finite, nonnegative time in seconds")
    args.cache_root = args.cache_root.resolve(strict=True)
    args.output_root = args.output_root.resolve()
    if args.output_root.is_relative_to(args.cache_root) or args.cache_root.is_relative_to(args.output_root):
        parser.error("Cache and output roots must be separate, non-nested directories")
    ffmpeg, ffprobe = (None, None) if args.list else (resolve_tool("ffmpeg", args.ffmpeg), resolve_tool("ffprobe", args.ffprobe))
    args.output_root.mkdir(parents=True, exist_ok=True)
    entries, errors = [], 0
    # Only read local download metadata and track files, never signed playback URLs.
    for metadata_file in sorted(args.cache_root.rglob("videoInfo.json")):
        try:
            metadata = read_json(metadata_file)
            folder = metadata_file.parent
            if args.only and not set(args.only).intersection([folder.name, str(metadata.get("cid")), str(metadata.get("bvid"))]):
                continue
            if not list(folder.glob("*.m4s")):
                continue
            item = {"folder": str(folder), "title": metadata.get("title"), "bvid": metadata.get("bvid")}
            if args.list:
                problem = completion_problem(metadata, sorted(folder.glob("*.m4s")))
                item.update(status="skipped" if problem else "ready", reason=problem)
            else:
                item.update(convert_one(folder, metadata, args, ffmpeg, ffprobe))
        except Exception as error:
            item = {"folder": str(metadata_file.parent), "status": "error", "reason": str(error)}
            errors += 1
        entries.append(item)
        emit(json.dumps(item, ensure_ascii=False))
    if not args.list:
        write_json(args.output_root / "conversion-index.json", {"schemaVersion": 1, "entries": entries})
        gallery = Path(__file__).with_name("build_video_gallery.py")
        if gallery.exists():
            emit(run([sys.executable, "-X", "utf8", gallery, "--root", args.output_root]).stdout.strip())
    emit(f"DONE {len(entries)} local media folders, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
