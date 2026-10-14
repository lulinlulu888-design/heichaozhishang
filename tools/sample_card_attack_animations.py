"""Sample five exact APK attack clips with a separately built pinned ACL decoder.

Keeps the existing idle/enemy sampler and its provenance unchanged. This does
not validate arbitrary ACL inputs or establish original battle timing.
"""
import hashlib
import json
import subprocess
from pathlib import Path
from inspect_neox_animation import parse_clip, sample_clip
from export_elsa_model import write_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'analysis/battle-visual/skill-animation'
RUNTIME = ROOT/'tools/runtime/acl-1.2.0'
PINS = {
 'fire_1': '3edd7e7239cf79c61c27ba9dfe9164ee84da565fe436a563401b32bd5c96d951',
 'crit_1': '9d52a0ba728e217cde94f2fd2d85505e66a3856e3e543e2b5492287e19590ddc',
 'fire_1_1': '727a622d1523a3abb077e8183907b617072ee94da44aeac16f5d4267e5609bd8',
 'fire_1_3': '9b89b1eb8392e9216689c6b70717ce263eb6729e06ce159142b8e8ffea4c80b1',
 'fire_2': '509d113822775fc8b25fed419e917fa856f20aa065aedeff2c35da7e2c0caf22',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    wrapper = ROOT/'tools/acl_sample.cpp'
    if sha(wrapper) != 'c2f3e96fc84a7413fd1b060cbea77b48b3cf3818c8b4fc0a754d9802d2b1fdd8':
        raise ValueError('Reference decoder wrapper changed')
    if sha(RUNTIME/'acl-v1.2.0.zip') != '167ea61e953e074d5fa0dcaf5b74f009104da0935ef27d0593b989a14cb0c5f8':
        raise ValueError('Official ACL archive changed')
    # Verify headers used by the compiler match the already-installed archive.
    import zipfile
    with zipfile.ZipFile(RUNTIME/'acl-v1.2.0.zip') as archive:
        for item in archive.infolist():
            if item.filename.startswith('acl-1.2.0/includes/') and not item.is_dir():
                if (RUNTIME/'source'/item.filename).read_bytes() != archive.read(item):
                    raise ValueError('ACL source header changed')
    text = wrapper.read_text('utf8')
    start = text.index('        if (inputHash == ')
    end = text.index('        require(clipName != nullptr,', start)
    checks = ''.join(f'        if (inputHash == "{digest}") clipName = "{name}.acl";\n' for name, digest in PINS.items())
    text = text[:start]+checks+text[end:]
    text = text.replace('four pinned original clips', 'five pinned original attack clips')
    text = text.replace('Decode exactly four SHA-256-pinned original clips', 'Decode exactly five SHA-256-pinned original attack clips')
    # compressed_clip.h: bytes24/25 are segment_range_reduction/has_scale.
    # These pinned attack clips omit scale tracks; one-segment clips omit
    # segment range reduction. Keep exact observed formats, not arbitrary input.
    text = text.replace('raw[23] == 7 && raw[24] == 7 && raw[25] == 1 && raw[26] <= 1',
        'raw[23] == 7 && (raw[24] == 0 || raw[24] == 7) && raw[25] == 0 && raw[26] == 1')
    text = text.replace('uint64_t(h.num_bones) * 3 + 31', 'uint64_t(h.num_bones) * 2 + 31')
    destination = RUNTIME/'attack-wrapper'
    destination.mkdir(exist_ok=True)
    (destination/'acl_sample.cpp').write_text(text, encoding='utf8')
    (destination/'CMakeLists.txt').write_text((RUNTIME/'wrapper/CMakeLists.txt').read_text('utf8'), encoding='utf8')
    cmake = Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe')
    build = RUNTIME/'attack-build'
    subprocess.run([str(cmake), '-S', str(destination), '-B', str(build), '-G', 'Visual Studio 17 2022', '-A', 'x64'], check=True)
    subprocess.run([str(cmake), '--build', str(build), '--config', 'Release', '--parallel', '4'], check=True)
    executable = build/'Release/acl-sample.exe'
    results = []
    for name, pin in PINS.items():
        raw = (SOURCE/(name+'.gisacl')).read_bytes()
        metadata_path = SOURCE/(name+'.json')
        metadata = json.loads(metadata_path.read_text('utf8'))
        parsed = parse_clip(raw)
        if parsed['acl_sha256'] != pin or parsed['sha256'] != metadata['source']['sha256']:
            raise ValueError('Attack payload does not match pinned source')
        acl = SOURCE/(name+'.acl')
        acl.write_bytes(raw[parsed['acl_offset']:])
        sampled = sample_clip(executable, acl, SOURCE/(name+'.poses'), parsed)
        metadata.update(sampled)
        metadata['sampler_executable_sha256'] = sha(executable)
        write_json(metadata_path, metadata)
        results.append(dict(name=name, samples=parsed['samples'], bones=parsed['bone_count'], poses=sampled['poses']))
    write_json(SOURCE/'sampling.json', dict(accepted_input_sha256=PINS, wrapper_sha256=sha(destination/'acl_sample.cpp'),
        executable_sha256=sha(executable), results=results, scope='Original poses only; skill timing and rendering not validated'))
    print(json.dumps(dict(clips=len(results), sampled_bone_frames=sum(r['samples']*r['bones'] for r in results))))


if __name__ == '__main__':
    main()
