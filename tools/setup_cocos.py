"""Download and unpack the pinned official Creator build into this workspace.

Does not install globally, run downloaded code, or accept any software agreement.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "3.8.8"
URL = "https://download.cocos.com/CocosCreator/v3.8.8/CocosCreator-v3.8.8-win-121518.zip"
EXPECTED_BYTES = 1027270586
EXPECTED_ENTRIES = 51661
EXPECTED_EXPANDED_BYTES = 3915570914
EXPECTED_SHA256 = "e365030aa4f24b515f499cf093cd86fdf38a0f763b5fbcacb20e96253e0fcc0b"


def main() -> None:
    archive = ROOT / ".tools/downloads/CocosCreator-v3.8.8-win-121518.zip"
    target = ROOT / ".tools/cocos" / VERSION
    archive.parent.mkdir(parents=True, exist_ok=True)
    partial = archive.with_suffix(".zip.partial")
    if not archive.exists():
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        with urllib.request.urlopen(urllib.request.Request(URL, headers=headers), timeout=60) as response:
            if offset and response.status != 206:
                raise RuntimeError("Server declined download resume; partial retained")
            if not response.url.startswith("https://download.cocos.com/"):
                raise RuntimeError(f"Unexpected download destination: {response.url}")
            with partial.open("ab" if offset else "wb") as output:
                last = 0.0
                while chunk := response.read(4 * 1024 * 1024):
                    output.write(chunk)
                    offset += len(chunk)
                    if time.monotonic() - last > 10:
                        print(f"Downloaded {offset}/{EXPECTED_BYTES} bytes ({offset / EXPECTED_BYTES:.1%})", flush=True)
                        last = time.monotonic()
        if partial.stat().st_size != EXPECTED_BYTES:
            raise RuntimeError("Unexpected archive length; partial retained")
        partial.replace(archive)
    if archive.stat().st_size != EXPECTED_BYTES:
        raise RuntimeError("Existing archive length does not match pinned metadata")
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError("Archive SHA-256 differs from the verified 2026-10-14 download")
    print(f"Archive SHA-256: {digest}", flush=True)
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) != EXPECTED_ENTRIES or sum(v.file_size for v in entries) != EXPECTED_EXPANDED_BYTES:
            raise RuntimeError("ZIP directory does not match pinned metadata")
        for entry in entries:
            relative = PurePosixPath(entry.filename)
            if relative.is_absolute() or ".." in relative.parts or "\\" in entry.filename or ":" in entry.filename:
                raise RuntimeError(f"Unsafe ZIP member: {entry.filename}")
            if entry.external_attr >> 16 & 0o170000 == 0o120000:
                raise RuntimeError(f"Symlink ZIP member: {entry.filename}")
        target.mkdir(parents=True, exist_ok=True)
        marker = target / "codex-download.json"
        if not marker.exists():
            for i, entry in enumerate(entries):
                package.extract(entry, target)
                if i % 5000 == 0:
                    print(f"Extracted and CRC-checked {i}/{len(entries)} entries", flush=True)
            # zipfile verifies each extracted member's CRC. Signature checked separately.
            marker.write_text(json.dumps({
                "url": URL, "version": VERSION, "archive": str(archive.relative_to(ROOT)),
                "sha256": digest, "bytes": EXPECTED_BYTES, "entries": len(entries),
                "expandedBytes": EXPECTED_EXPANDED_BYTES, "crc": "all members verified during extraction",
                "signature": "not yet inspected", "downloadedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }, indent=2) + "\n", encoding="utf-8")
        else:
            previous = json.loads(marker.read_text(encoding="utf-8"))
            if previous["sha256"] != digest:
                raise RuntimeError("Extracted marker differs from current archive")
    print(f"Creator prepared (not started): {target / 'CocosCreator.exe'}", flush=True)


if __name__ == "__main__":
    main()
