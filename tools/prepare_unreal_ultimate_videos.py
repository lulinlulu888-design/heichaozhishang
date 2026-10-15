"""Stage original APK ultimate movies without transcoding or modifying the APK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APK = ROOT / "heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk"
DESTINATION = ROOT / "clients/unreal5 5.8/Content/Movies/Recovered/Ultimates"
PREFIX = "assets/res/video/dazhao/"


def stage(names):
    items = []
    with zipfile.ZipFile(APK) as archive:
        members = {Path(item.filename).name: item for item in archive.infolist()
                   if item.filename.startswith(PREFIX) and item.filename.endswith(".mp4")}
        selected = sorted(members) if not names else sorted(set(names))
        unknown = set(selected) - members.keys()
        if unknown:
            raise ValueError(f"Unknown original movie names: {sorted(unknown)}")
        DESTINATION.mkdir(parents=True, exist_ok=True)
        for name in selected:
            member = members[name]
            if member.filename != PREFIX + name:
                raise ValueError(f"Unexpected nested movie path: {member.filename}")
            data = archive.read(member)  # ZipFile verifies the APK member CRC.
            digest = hashlib.sha256(data).hexdigest()
            destination = DESTINATION / name
            if destination.exists():
                if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                    raise ValueError(f"Refusing to overwrite a modified movie: {destination}")
                status = "verified-existing"
            else:
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=DESTINATION, suffix=".pending", delete=False) as stream:
                        temporary = Path(stream.name)
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    # Windows rename refuses a destination that appeared concurrently.
                    temporary.rename(destination)
                    status = "staged"
                finally:
                    if temporary and temporary.exists():
                        temporary.unlink()
            items.append({"apkMember": member.filename, "path": str(destination),
                          "bytes": len(data), "sha256": digest,
                          "zipCrc32": f"{member.CRC:08x}", "status": status})
    report = {"schemaVersion": 1, "mode": "original-apk-byte-copy", "apk": str(APK),
              "availableMovies": len(members), "items": items}
    report_path = ROOT / "analysis/unreal/ultimate-videos/staged.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movie", action="append", help="Exact original basename; omitted stages all movies")
    args = parser.parse_args()
    result = stage(args.movie)
    print(json.dumps({"staged": len(result["items"]), "available": result["availableMovies"],
                      "destination": str(DESTINATION)}, ensure_ascii=False))
