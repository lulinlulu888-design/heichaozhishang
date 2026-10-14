"""Build the pinned official ACL 1.2.0 data decoder using existing VS/CMake."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'tools/runtime/acl-1.2.0'
URL = 'https://codeload.github.com/nfrechette/acl/zip/refs/tags/v1.2.0'
SHA = '167ea61e953e074d5fa0dcaf5b74f009104da0935ef27d0593b989a14cb0c5f8'


def build():
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST/'acl-v1.2.0.zip'
    if not archive.exists():
        with urllib.request.urlopen(URL, timeout=45) as response:
            data = response.read(32*1024*1024+1)
        if len(data) > 32*1024*1024 or hashlib.sha256(data).hexdigest() != SHA:
            raise ValueError('source archive size/hash mismatch')
        archive.write_bytes(data)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA:
        raise ValueError('cached ACL archive hash mismatch')
    with zipfile.ZipFile(archive) as z:
        if sum(x.file_size for x in z.infolist()) > 128*1024*1024:
            raise ValueError('source size exceeds budget')
        for item in z.infolist():
            p = PurePosixPath(item.filename)
            if not p.parts or p.parts[0] != 'acl-1.2.0' or '..' in p.parts or '\\' in item.filename:
                raise ValueError('unsafe source archive member')
        z.extractall(DEST/'source')
    vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
    vs = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-version', '[17.0,18.0)',
        '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
    if not vs:
        raise RuntimeError('existing VS 2022 C++ toolchain required')
    cmake = shutil.which('cmake') or str(Path(vs)/'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe')
    wrapper = DEST/'wrapper'
    wrapper.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'tools/acl_sample.cpp', wrapper/'acl_sample.cpp')
    (wrapper/'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.15)
project(hczs_acl_sample LANGUAGES CXX)
add_executable(acl-sample acl_sample.cpp)
target_compile_features(acl-sample PRIVATE cxx_std_17)
target_include_directories(acl-sample PRIVATE ../source/acl-1.2.0/includes)
target_link_libraries(acl-sample PRIVATE bcrypt)
''', encoding='utf8')
    commands = [[cmake, '-S', str(wrapper), '-B', str(DEST/'build'), '-G', 'Visual Studio 17 2022',
                 '-A', 'x64', '-DCMAKE_GENERATOR_INSTANCE='+vs],
                [cmake, '--build', str(DEST/'build'), '--config', 'Release', '--parallel', '4']]
    for command in commands:
        subprocess.run(command, check=True)
    executable = DEST/'build/Release/acl-sample.exe'
    (DEST/'provenance.json').write_text(json.dumps({'sourceUrl': URL, 'archiveSha256': SHA,
        'checksumBasis': 'SHA256 recorded from the official tag archive and pinned for subsequent builds',
        'wrapperSha256': hashlib.sha256((ROOT/'tools/acl_sample.cpp').read_bytes()).hexdigest(),
        'executableSha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'commands': commands,
        'acceptedInputSha256': {
            'stand_idle.acl': 'cda4d69e000276ee263a47d5531c43cbc6ae84ff6e133d64fbeeb7ccb7de898f',
            'skin.acl': '6bf93b1e7791dd6124a6e13c26538cfeac56d65c0d49abffc68a818c06be4cbd',
            'tutorial_enemy_idle.acl': '26de4e5657227f27f19f64dc2c91aefe1dc5c23face79af10cb8811d5bc88a3f',
            'tutorial_enemy_fire.acl': '7615d852c5356a2dd11f2c2e7fc04953e21a71bb5364e245fafaa8de4decbfbc'},
        'scope': 'Only four SHA-256-pinned original clips (two Elsa, two tutorial enemy); official ACL decoder; no game execution'}, indent=2), encoding='utf8')
    print(executable)


if __name__ == '__main__':
    build()
