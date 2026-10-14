"""Inspect an actually built local APK; does not install or launch it."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument('--variant', choices=('device', 'emulator'), default='device')
    args = parser.parse_args()
    apk = args.apk.resolve(strict=True)
    emulator = args.variant == 'emulator'
    expected_abi, expected_machine = ('x86_64', 62) if emulator else ('arm64-v8a', 183)
    output = ROOT / ('analysis/cocos-android-emulator' if emulator else 'analysis/cocos-android')
    output.mkdir(parents=True, exist_ok=True)
    config_file = 'build-android-emulator.json' if emulator else 'build-android.json'
    config = json.loads((ROOT / 'clients/cocos-poc' / config_file).read_text(encoding="utf-8"))["packages"]["android"]
    if config['appABIs'] != [expected_abi]:
        raise ValueError('Build variant ABI configuration mismatch')
    build_tools = Path(config["sdkPath"]) / "build-tools/35.0.0"
    java = Path(config["javaHome"]) / "bin/java.exe"
    commands = {
        "aapt2-badging": [str(build_tools / "aapt2.exe"), "dump", "badging", str(apk)],
        "apksigner-verify": [str(java), "-jar", str(build_tools / "lib/apksigner.jar"), "verify", "--verbose", "--print-certs", str(apk)],
        "zipalign-16k": [str(build_tools / "zipalign.exe"), "-c", "-P", "16", "-v", "4", str(apk)],
    }
    checks = {}
    for name, command in commands.items():
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        (output / f"{name}.log").write_bytes(result.stdout)
        checks[name] = {"exit_code": result.returncode, "log": (output / f'{name}.log').relative_to(ROOT).as_posix()}
    native_libraries = []
    with apk.open("rb") as stream, zipfile.ZipFile(apk) as archive:
        corrupt = archive.testzip()
        for item in archive.infolist():
            if not item.filename.startswith("lib/") or not item.filename.endswith(".so"):
                continue
            raw = archive.read(item)
            if raw[:6] != b"\x7fELF\x02\x01":
                raise ValueError(f"Expected little-endian ELF64: {item.filename}")
            machine = struct.unpack_from("<H", raw, 18)[0]
            phoff = struct.unpack_from("<Q", raw, 32)[0]
            phentsize, phnum = struct.unpack_from("<HH", raw, 54)
            loads = []
            relro = []
            for index in range(phnum):
                values = struct.unpack_from("<IIQQQQQQ", raw, phoff + index * phentsize)
                if values[0] == 1:
                    loads.append({"offset": values[2], "vaddr": values[3], "alignment": values[7]})
                elif values[0] == 0x6474E552:
                    relro.append({"vaddr": values[3], "mem_size": values[6], "end_16k_aligned": (values[3] + values[6]) % 16384 == 0})
            stream.seek(item.header_offset)
            header = stream.read(30)
            name_size, extra_size = struct.unpack_from("<HH", header, 26)
            data_offset = item.header_offset + 30 + name_size + extra_size
            native_libraries.append({"entry": item.filename, "sha256": hashlib.sha256(raw).hexdigest(),
                                     "size": len(raw), "elf_machine": machine, "load_segments": loads, "relro_segments": relro,
                                     "relro_16k_alignment": all(v["end_16k_aligned"] for v in relro),
                                     "elf_16k_alignment": bool(loads) and all(v["alignment"] >= 16384 and (v["vaddr"] - v["offset"]) % 16384 == 0 for v in loads),
                                     "zip_method": item.compress_type, "zip_data_offset": data_offset,
                                     "zip_16k_alignment": item.compress_type == zipfile.ZIP_STORED and data_offset % 16384 == 0})
    report = {"apk": str(apk), "variant": args.variant, "expected_abi": expected_abi,
              "size": apk.stat().st_size, "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
              "checks": checks, "zip_crc_valid": corrupt is None, "native_libraries": native_libraries,
              "device_installed": False, "device_runtime_tested": False,
              "scope": "APK signature/metadata/CRC and static ELF/ZIP alignment only; not device compatibility"}
    (output / "apk-verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if corrupt or not native_libraries or any(v["exit_code"] for v in checks.values()):
        raise SystemExit("APK structural/signature check failed; inspect saved evidence")
    if any(v['elf_machine'] != expected_machine or not v['entry'].startswith(f'lib/{expected_abi}/') or
           not v['elf_16k_alignment'] or not v['relro_16k_alignment'] or not v['zip_16k_alignment'] for v in native_libraries):
        raise SystemExit(f'{expected_abi}/16KB static check failed; inspect saved evidence')


if __name__ == "__main__":
    main()
