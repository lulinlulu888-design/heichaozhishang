"""Sample two exact APK enemy skill clips with a separately built pinned ACL decoder.

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
SOURCE = ROOT/'analysis/battle-visual/enemy-skills'
RUNTIME = ROOT/'tools/runtime/acl-1.2.0'
PINS = {
 'skill_2': 'ba75c0d5c78b8d96496e1983e283e57dd1eb7ad4f980c200ffe04a55db977642',
 'skill_3': '8efad5014ef28970068eabcbaa50760ea6eba91cee1a6eb15ab1e582edff646b',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    # Extract only the two authored skill clips, retaining source identities.
    import sample_tutorial_enemy_animation as enemy
    from inspect_neox_animation import extract_with_provenance, clip_path, map_bones
    from neox_resource_paths import read_catalogue
    from extract_texture_samples import APK_SHA256
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    _, _, library, model = enemy.inputs()
    catalogue = read_catalogue(apk)
    SOURCE.mkdir(parents=True, exist_ok=True)
    for name, pin in PINS.items():
        path = SOURCE/(name+'.gisacl')
        source = extract_with_provenance(apk, catalogue, clip_path(enemy.LIBRARY_PATH, name), path, APK_SHA256)
        metadata = parse_clip(path.read_bytes())
        if metadata['acl_sha256'] != pin:
            raise ValueError('Enemy skill payload changed')
        metadata['source'] = source
        metadata['library_record'] = next(r for r in library['clips'] if r['name'] == name)
        metadata['bone_mapping'] = map_bones(library, metadata, [b['name'] for b in model['bones']])
        write_json(SOURCE/(name+'.json'), metadata)
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
    text = text.replace('four pinned original clips', 'two pinned enemy skill clips')
    text = text.replace('Decode exactly four SHA-256-pinned original clips', 'Decode exactly two SHA-256-pinned enemy skill clips')
    destination = RUNTIME/'enemy-skills-wrapper'
    destination.mkdir(exist_ok=True)
    (destination/'acl_sample.cpp').write_text(text, encoding='utf8')
    (destination/'CMakeLists.txt').write_text((RUNTIME/'wrapper/CMakeLists.txt').read_text('utf8'), encoding='utf8')
    cmake = Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe')
    build = RUNTIME/'enemy-skills-build'
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
