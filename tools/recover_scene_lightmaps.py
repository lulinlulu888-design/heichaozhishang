"""Recover scene-relative NeoX lightmaps and per-submesh bindings from the APK.

No rebaking or rendering: UV transforms, encode kind and RGB scale/add remain
source values. Decoding the texture does not establish NeoX/UE lighting parity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue, lookup_logical

ROOT = Path(__file__).resolve().parents[1]


def recover(scene, out):
    if not scene or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in scene):
        raise ValueError('Expected a scene basename')
    out = out.resolve()
    if not out.is_relative_to((ROOT / 'analysis').resolve()):
        raise ValueError('Output must stay in analysis')
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('Original APK changed')
    catalogue = read_catalogue(apk)
    out.mkdir(parents=True, exist_ok=True)
    logical = f'scene/{scene}/{scene}.scn'
    source = out / 'scene.scn'
    provenance = extract(apk, catalogue, logical, source, APK_SHA256)
    root = ET.fromstring(source.read_bytes())
    path_node = root.find('.//LightMapPath')
    if path_node is None:
        raise ValueError('Scene has no LightMapPath')
    prefix = path_node.attrib['Path'].replace('\\', '/')
    textures = []
    for node in root.iter():
        if not node.tag.startswith('lightmap_') or 'Path' not in node.attrib:
            continue
        relative = node.attrib['Path'].replace('\\', '/')
        exact = prefix + '/' + relative
        candidates = [exact, exact.rsplit('.', 1)[0] + '.ktx']
        selected = next((p for p in candidates if len(lookup_logical(catalogue, p)) == 1), None)
        if selected is None:
            raise ValueError('Lightmap missing or ambiguous: ' + exact)
        local = out / (node.tag + Path(selected).suffix)
        record = extract(apk, catalogue, selected, local, APK_SHA256)
        decoded = convert([local], out / (node.tag + '-pixels'), DEFAULT_DECODER, inspector=DEFAULT_INSPECTOR)
        textures.append(dict(index=int(node.tag.split('_')[-1]), logicalPath=selected,
            source=record, decoded=decoded))
    indices = {t['index'] for t in textures}
    bindings = []
    for model in root.iter('model'):
        for slot, lightmap in enumerate(model.findall('Lightmap/sub_lightmap')):
            values = dict(lightmap.attrib)
            if int(values['texture_index']) not in indices:
                raise ValueError('Instance references an unavailable lightmap')
            bindings.append(dict(instanceName=model.get('Name'), instanceUuid=model.get('UUID'),
                filePathIndex=model.get('FilePathIndex'), sourceSubmeshOrdinal=slot, values=values))
    result = dict(apkSha256=APK_SHA256, scene=logical, sceneSource=provenance,
        textures=textures, bindings=bindings, lightingAppliedInUE=False,
        limitations=['Source submesh ordinal still requires UE material-slot mapping.',
            'UV1 orientation, linear sampling, encode_type=4 decoding and BRDF combination require native render validation.'])
    (out / 'lightmaps.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(scene=scene, lightmapTextures=len(textures), submeshBindings=len(bindings))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene')
    args = parser.parse_args()
    recover(args.scene, ROOT / 'analysis/battle-visual/lightmaps' / args.scene)
