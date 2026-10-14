"""Convert observed KTX1 ASTC textures without changing the source resource.

Only bounded, non-array 2D/cubemap ASTC is accepted. All mip/face payloads are
validated before one mip is exported via ARM's astcenc. No orientation flip or
material color-space assumption is applied. The original internal-format enum
selects linear/sRGB decoding; a PNG alone does not establish material semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
IDENTIFIER = b"\xabKTX 11\xbb\r\n\x1a\n"
BLOCKS = ((4, 4), (5, 4), (5, 5), (6, 5), (6, 6), (8, 5), (8, 6),
          (8, 8), (10, 5), (10, 6), (10, 8), (10, 10), (12, 10), (12, 12))
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_PIXELS = 64 * 1024 * 1024
DEFAULT_DECODER = ROOT / "tools/runtime/astcenc-5.7.0/bin/bin/astcenc-sse2.exe"
DEFAULT_INSPECTOR = ROOT / "tools/runtime/astc-inspector-5.7.0/build/Release/astc-block-info.exe"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_bounded(path):
    with pathlib.Path(path).open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("texture exceeds file size limit")
    return data


def parse_ktx(data):
    """Return offsets and metadata, preserving rather than interpreting pixels."""
    if len(data) < 64 or data[:12] != IDENTIFIER:
        raise ValueError("not a complete KTX1 header")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("texture exceeds file size limit")
    endian = {b"\x01\x02\x03\x04": "<", b"\x04\x03\x02\x01": ">"}.get(data[12:16])
    if endian is None:
        raise ValueError("invalid KTX endianness")
    fields = struct.unpack_from(endian + "12I", data, 16)
    (gl_type, type_size, gl_format, internal, base, width, height, depth,
     arrays, faces, declared_mips, metadata_size) = fields
    if (gl_type, type_size, gl_format) != (0, 1, 0):
        raise ValueError("expected compressed KTX with one-byte data elements")
    if 0x93B0 <= internal < 0x93B0 + len(BLOCKS):
        block = BLOCKS[internal - 0x93B0]
        profile = "linear"
    elif 0x93D0 <= internal < 0x93D0 + len(BLOCKS):
        block = BLOCKS[internal - 0x93D0]
        profile = "srgb"
    else:
        raise ValueError(f"unsupported ASTC internal format 0x{internal:x}")
    if not (0 < width <= 16384 and 0 < height <= 16384 and width * height <= MAX_PIXELS):
        raise ValueError("dimensions exceed supported pixel bounds")
    if depth != 0 or arrays != 0 or faces not in (1, 6):
        raise ValueError("only non-array 2D textures or cubemaps are supported")
    if faces == 6 and width != height:
        raise ValueError("cubemap faces must be square")
    mip_count = declared_mips or 1
    if not 1 <= mip_count <= max(width, height).bit_length():
        raise ValueError("invalid mip level count")
    end_metadata = 64 + metadata_size
    if metadata_size % 4 or end_metadata > len(data):
        raise ValueError("metadata bounds/alignment")
    metadata = []
    pos = 64
    while pos < end_metadata:
        if pos + 4 > end_metadata:
            raise ValueError("truncated metadata length")
        size = struct.unpack_from(endian + "I", data, pos)[0]
        pos += 4
        if not size or pos + size > end_metadata:
            raise ValueError("metadata entry bounds")
        raw = data[pos:pos + size]
        key, separator, value = raw.partition(b"\x00")
        if not separator or not key:
            raise ValueError("metadata key must be null-terminated")
        try:
            key_text = key.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("metadata key is not UTF-8") from exc
        entry = {"key": key_text, "value_hex": value.hex()}
        try:
            entry["text"] = value.rstrip(b"\x00").decode("utf-8")
        except UnicodeDecodeError:
            pass
        metadata.append(entry)
        pos += (size + 3) & ~3
        if pos > end_metadata:
            raise ValueError("metadata padding exceeds declared block")
    levels = []
    for mip in range(mip_count):
        if pos + 4 > len(data):
            raise ValueError("missing mip size")
        image_size = struct.unpack_from(endian + "I", data, pos)[0]
        pos += 4
        w, h = max(1, width >> mip), max(1, height >> mip)
        expected = ((w + block[0] - 1) // block[0]) * ((h + block[1] - 1) // block[1]) * 16
        if image_size != expected:
            raise ValueError(f"mip {mip} payload size {image_size} != expected {expected}")
        face_offsets = []
        for _ in range(faces):
            if pos + image_size > len(data):
                raise ValueError("truncated face payload")
            face_offsets.append(pos)
            pos += (image_size + 3) & ~3
        levels.append({"mip": mip, "width": w, "height": h,
                       "image_size": image_size, "face_offsets": face_offsets})
    if pos != len(data):
        raise ValueError("unexpected trailing KTX data")
    warnings = []
    if base != 0x1908:
        warnings.append(f"glBaseInternalFormat=0x{base:x} differs from expected GL_RGBA; "
                        "only the validated ASTC payload is exported")
    return {"width": width, "height": height, "faces": faces, "block": list(block),
            "internal_format": internal, "base_format": base, "profile": profile,
            "mip_count": mip_count, "generate_mipmaps": declared_mips == 0,
            "metadata": metadata, "levels": levels, "warnings": warnings,
            "orientation_changed": False}


def raw_astc(data, texture, mip=0, face=0):
    if not 0 <= mip < texture["mip_count"] or not 0 <= face < texture["faces"]:
        raise ValueError("requested mip/face outside texture")
    level = texture["levels"][mip]
    # ASTC_MAGIC_ID 0x5CA1AB13 is stored least-significant byte first.
    header = struct.pack("<I", 0x5CA1AB13) + bytes((*texture["block"], 1))
    for dimension in (level["width"], level["height"], 1):
        header += dimension.to_bytes(3, "little")
    offset = level["face_offsets"][face]
    return header + data[offset:offset + level["image_size"]]


def display_path(path):
    try:
        return pathlib.Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(pathlib.Path(path).resolve())


def validate_blocks(data, texture, inspector):
    """Use ARM's block API, not decoded error colors, to establish LDR validity."""
    reports = []
    with tempfile.TemporaryDirectory(prefix="hczs-astc-check-") as directory:
        probe = pathlib.Path(directory) / "probe.astc"
        for mip, level in enumerate(texture["levels"]):
            for face in range(texture["faces"]):
                probe.write_bytes(raw_astc(data, texture, mip, face))
                run = subprocess.run([str(inspector), str(probe)], capture_output=True, text=True, timeout=60)
                if run.returncode not in (0, 2):
                    raise RuntimeError(f"ASTC inspector failed: {run.stderr[-2000:]}")
                report = json.loads(run.stdout)
                expected = level["image_size"] // 16
                if (report["width"] != level["width"] or report["height"] != level["height"]
                        or report["block"] != texture["block"] or report["block_count"] != expected
                        or report["inspection_profile"] != "HDR"):
                    raise ValueError("ASTC inspector output does not match requested texture")
                if (run.returncode or report["hdr_blocks"] or report["error_blocks"]
                        or not report["ldr_compatible"] or report["ldr_blocks"] != expected):
                    raise ValueError(f"mip {mip} face {face}: unsupported HDR or invalid ASTC blocks: "
                                     f"HDR={report['hdr_blocks']}, error={report['error_blocks']}; "
                                     f"details={report['first_problem_blocks'][:2]}")
                reports.append({"mip": mip, "face": face, **report})
    return {"validated_mips": texture["mip_count"], "validated_faces_per_mip": texture["faces"],
            "block_count": sum(r["block_count"] for r in reports),
            "hdr_blocks": 0, "error_blocks": 0, "reports": reports}


def convert(inputs, output, decoder, mip=0, provenance_path=None, inspector=DEFAULT_INSPECTOR):
    from PIL import Image

    decoder = pathlib.Path(decoder).resolve()
    if not decoder.is_file():
        raise ValueError("astcenc missing; run tools/setup_astcenc.ps1 or pass --astcenc")
    inspector = pathlib.Path(inspector).resolve()
    if not inspector.is_file():
        raise ValueError("ASTC block inspector missing; run tools/setup_astc_inspector.py or pass --inspector")
    output = pathlib.Path(output).resolve()
    provenance = {}
    if provenance_path:
        for entry in json.loads(pathlib.Path(provenance_path).read_text(encoding="utf-8")):
            if "sample_path" in entry:
                source = ROOT / entry["sample_path"].replace("\\", "/")
                provenance[str(source.resolve())] = entry
    # Validate every input before starting the external decoder.
    prepared = []
    for path in inputs:
        path = pathlib.Path(path).resolve()
        data = read_bounded(path)
        texture = parse_ktx(data)
        if not 0 <= mip < texture["mip_count"]:
            raise ValueError(f"{path.name}: requested mip does not exist")
        evidence = provenance.get(str(path))
        if provenance_path and (not evidence or evidence["sha256"] != sha256(data)):
            raise ValueError(f"{path.name}: missing/mismatched resource provenance")
        profile_validation = validate_blocks(data, texture, inspector)
        prepared.append((path, data, texture, evidence, profile_validation))
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for path, data, texture, evidence, profile_validation in prepared:
        record = {"source": display_path(path), "source_sha256": sha256(data),
                  "texture": texture, "provenance": evidence,
                  "block_validation": profile_validation, "outputs": []}
        for face in range(texture["faces"]):
            stem = f"{path.stem}.{sha256(data)[:12]}.m{mip}.f{face}"
            astc_path = output / (stem + ".astc")
            png_path = output / (stem + ".png")
            astc_path.write_bytes(raw_astc(data, texture, mip, face))
            mode = "-ds" if texture["profile"] == "srgb" else "-dl"
            command = [str(decoder), mode, str(astc_path), str(png_path), "-silent"]
            run = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if run.returncode:
                raise RuntimeError(f"astcenc failed for {path.name}: {run.stderr[-2000:]} {run.stdout[-2000:]}")
            with Image.open(png_path) as image:
                image.load()
                level = texture["levels"][mip]
                if image.format != "PNG" or image.size != (level["width"], level["height"]):
                    raise ValueError("decoded image format/dimensions mismatch")
                rgba = image.convert("RGBA")
                result = {"mip": mip, "face": face, "width": image.width, "height": image.height,
                          "png": display_path(png_path), "png_sha256": sha256(png_path.read_bytes()),
                          "rgba_sha256": sha256(rgba.tobytes()),
                          "channel_extrema_rgba": rgba.getextrema(),
                          "astc": display_path(astc_path), "astc_sha256": sha256(astc_path.read_bytes()),
                          "decoder_mode": mode}
            record["outputs"].append(result)
        results.append(record)
    manifest = {"format_version": 1, "decoder": display_path(decoder),
                "decoder_sha256": sha256(decoder.read_bytes()),
                "block_inspector": display_path(inspector),
                "block_inspector_sha256": sha256(inspector.read_bytes()),
                "scope": "ASTC LDR pixel conversion, with original orientation and enum color profile; "
                         "does not validate original game material appearance",
                "textures": results}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "analysis/assets/converted-ktx")
    parser.add_argument("--astcenc", type=pathlib.Path, default=DEFAULT_DECODER)
    parser.add_argument("--inspector", type=pathlib.Path, default=DEFAULT_INSPECTOR)
    parser.add_argument("--mip", type=int, default=0)
    parser.add_argument("--provenance", type=pathlib.Path)
    args = parser.parse_args()
    result = convert(args.inputs, args.output, args.astcenc, args.mip, args.provenance, args.inspector)
    print(json.dumps({"textures": len(result["textures"]),
                      "pngs": sum(len(r["outputs"]) for r in result["textures"]),
                      "manifest": str(args.output / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
