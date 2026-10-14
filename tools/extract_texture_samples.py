"""Reproduce seven fixed KTX samples directly from the unmodified APK.

Seeks inside ZIP members and reads one NXPK record per pack. Does not unpack the
whole asset tree. Both the source APK and each decoded sample have pinned hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import zipfile

from decode_ktx import display_path, parse_ktx, sha256
from extract_npk import APK, ROOT, decode_entry

APK_SHA256 = "aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4"
SAMPLES = (
    ("uires", 3481, "c6557b5b2a4e64ad4d01f93006d92f74bb5dbad794d5f9c03b7347614f2d38e1"),
    ("ui_model", 19, "38f10c44f51b86f7576c0008f946defb37dfe1c54b35176bdfae8adaa74ef720"),
    ("character", 6569, "2978abe7801dfc21ad0abe50d50424726b29af061074c8606bb7ff5c46e81b11"),
    ("effects", 6289, "7d711f67004c436250efa10c3b6dcb522d7da30f5ad21663e757641c9abdbc0a"),
    ("scene", 306, "1ff9523dc0879e62d134943739d61e7898d6e463bc3e08c0f6cb4fa544ddc23e"),
    ("textures", 9, "f9e47b53d21bfd93737748831692cc4201e5122e15737cdb6e2dafcff97bf3fe"),
    ("model", 3442, "02ee5ca623583b5b2be98d6d7c181c3b17a03fd38c95cc8ee984b0761454992a"),
)


def read_record(archive, member, index):
    info = archive.getinfo(member)
    with archive.open(info) as stream:
        header = stream.read(24)
        if len(header) != 24:
            raise ValueError("short NXPK header")
        magic, count, _, _, version, index_offset = struct.unpack("<4s5I", header)
        if (magic != b"NXPK" or index_offset < 24 or count > 1000000
                or index_offset + count * 28 != info.file_size or not 0 <= index < count):
            raise ValueError("invalid NXPK header/index bounds")
        stream.seek(index_offset + index * 28)
        record_bytes = stream.read(28)
        if len(record_bytes) != 28:
            raise ValueError("short NXPK record")
        keys = ("name_hash", "offset", "stored_size", "original_size",
                "digest1", "digest2", "compression", "encryption")
        record = dict(zip(keys, struct.unpack("<6I2H", record_bytes)))
        if (record["offset"] < 24 or record["offset"] + record["stored_size"] > index_offset
                or record["stored_size"] > 8 * 1024 * 1024):
            raise ValueError("sample entry exceeds bounds")
        stream.seek(record["offset"])
        stored = stream.read(record["stored_size"])
        if len(stored) != record["stored_size"]:
            raise ValueError("truncated sample payload")
        decoded = decode_entry(stored, {**record, "offset": 0}, max_decoded_bytes=8 * 1024 * 1024)
    return record, decoded, version


def extract(apk, output):
    apk = pathlib.Path(apk)
    with apk.open("rb") as stream:
        source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if source_hash != APK_SHA256:
        raise ValueError("APK differs from pinned evidence; refusing fixed-index extraction")
    output = pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=True)
    samples = []
    with zipfile.ZipFile(apk) as archive:
        for pack, index, expected_sha in SAMPLES:
            member = f"assets/res/{pack}.npk"
            entry, data, version = read_record(archive, member, index)
            if sha256(data) != expected_sha:
                raise ValueError(f"{member} record {index}: sample digest mismatch")
            texture = parse_ktx(data)
            destination = output / f"{pack}.{index:05d}.KTX1.bin"
            destination.write_bytes(data)
            samples.append({"member": member, "index": index, "name_hash": f'{entry["name_hash"]:08x}',
                            "npk_offset": entry["offset"], "stored_size": entry["stored_size"],
                            "decoded_size": len(data), "compression": entry["compression"],
                            "encryption": entry["encryption"], "npk_version": version,
                            "sha256": expected_sha, "apk_sha256": source_hash, "kind": "KTX1",
                            "sample_path": display_path(destination), "texture": texture})
    manifest = output / "resource_samples.json"
    manifest.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=pathlib.Path, default=APK)
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "analysis/assets/texture-samples")
    args = parser.parse_args()
    print(extract(args.apk, args.output))


if __name__ == "__main__":
    main()
