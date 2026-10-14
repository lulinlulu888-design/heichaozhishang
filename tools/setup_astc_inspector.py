"""Build a local block inspector from pinned, unmodified ARM astcenc 5.7.0.

Requires existing Windows VS 2022 C++ Build Tools and CMake; installs nothing
globally. The official source archive is SHA256-pinned; build artifacts and
provenance remain in ignored tools/runtime/astc-inspector-5.7.0/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "tools/runtime/astc-inspector-5.7.0"
URL = "https://codeload.github.com/ARM-software/astc-encoder/zip/refs/tags/5.7.0"
SHA = "a28919f28547f9d9bc480f3147dcfc8383d7d845c635da90a7edd0a99576b496"


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def build(destination=DEST):
    if os.name != "nt":
        raise RuntimeError("this build recipe targets existing Windows VS 2022 Build Tools")
    destination = pathlib.Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "astc-encoder-5.7.0.zip"
    if not archive.is_file():
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024:
            raise RuntimeError("source archive exceeds download bound")
        if hashlib.sha256(data).hexdigest() != SHA:
            raise RuntimeError("downloaded ARM source archive hash mismatch")
        archive.write_bytes(data)
    if digest(archive) != SHA:
        raise RuntimeError("cached ARM source archive hash mismatch")
    source = destination / "source"
    # Restore exactly the pinned source on each build. No remote code patching.
    with zipfile.ZipFile(archive) as zipped:
        if sum(i.file_size for i in zipped.infolist()) > 256 * 1024 * 1024:
            raise RuntimeError("source archive exceeds extracted size bound")
        for item in zipped.infolist():
            parts = pathlib.PurePosixPath(item.filename).parts
            if not parts or parts[0] != "astc-encoder-5.7.0" or ".." in parts or "\\" in item.filename:
                raise RuntimeError("source archive member outside expected tree")
        zipped.extractall(source)
    vswhere = pathlib.Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / \
        "Microsoft Visual Studio/Installer/vswhere.exe"
    if not vswhere.is_file():
        raise RuntimeError("VS installer vswhere is missing")
    vs_path = subprocess.check_output([str(vswhere), "-latest", "-products", "*",
        "-version", "[17.0,18.0)", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
        "-property", "installationPath"], text=True).strip()
    if not vs_path:
        raise RuntimeError("VS 2022 C++ Build Tools not found")
    cmake = shutil.which("cmake") or str(pathlib.Path(vs_path) /
        "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe")
    if not pathlib.Path(cmake).is_file():
        raise RuntimeError("CMake not found in PATH or VS")
    wrapper = destination / "wrapper"
    wrapper.mkdir(exist_ok=True)
    checker = ROOT / "tools/astc_block_info.cpp"
    shutil.copyfile(checker, wrapper / checker.name)
    cmake_text = '''cmake_minimum_required(VERSION 3.15)
cmake_policy(SET CMP0091 NEW)
project(hczs_astc_inspector LANGUAGES C CXX)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
set(ASTCENC_CLI OFF CACHE BOOL "" FORCE)
set(ASTCENC_DECOMPRESSOR OFF CACHE BOOL "" FORCE)
set(ASTCENC_SHAREDLIB OFF CACHE BOOL "" FORCE)
set(ASTCENC_ISA_SSE2 ON CACHE BOOL "" FORCE)
set(ASTCENC_WERROR ON CACHE BOOL "" FORCE)
add_subdirectory("../source/astc-encoder-5.7.0" astcenc)
add_executable(astc-block-info astc_block_info.cpp)
target_compile_features(astc-block-info PRIVATE cxx_std_14)
target_link_libraries(astc-block-info PRIVATE astcenc-sse2-static)
'''
    (wrapper / "CMakeLists.txt").write_text(cmake_text, encoding="utf-8")
    build_dir = destination / "build"
    configure = [cmake, "-S", str(wrapper), "-B", str(build_dir),
                 "-G", "Visual Studio 17 2022", "-A", "x64",
                 "-DCMAKE_GENERATOR_INSTANCE=" + vs_path]
    compile_command = [cmake, "--build", str(build_dir), "--config", "Release",
                       "--target", "astc-block-info", "--parallel", "4"]
    subprocess.run(configure, check=True)
    subprocess.run(compile_command, check=True)
    executable = build_dir / "Release/astc-block-info.exe"
    compiler_files = list(build_dir.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
    provenance = {"version": "5.7.0", "source": URL, "source_archive_sha256": SHA,
                  "checksum_basis": "local SHA256 of official tag archive; pinned for subsequent builds",
                  "checker_source_sha256": digest(checker),
                  "cmake_wrapper_sha256": digest(wrapper / "CMakeLists.txt"),
                  "configure_command": configure, "build_command": compile_command,
                  "cmake_version": subprocess.check_output([cmake, "--version"], text=True).strip(),
                  "compiler_config_sha256": {str(p): digest(p) for p in compiler_files},
                  "executable": str(executable), "executable_sha256": digest(executable),
                  "scope": "reproducible source/configuration; executable byte identity across toolchains is not promised"}
    (destination / "source.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return executable


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=pathlib.Path, default=DEST)
    args = parser.parse_args()
    print(build(args.destination))
