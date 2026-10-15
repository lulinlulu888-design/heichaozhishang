"""Recover an original scene reflection cube, retaining every face and mip.

The authored prefilter chain is preserved. Cube basis, HDR encoding and NeoX
probe selection still require verification before applying this to UE lighting.
"""
import argparse
import hashlib
import json
from pathlib import Path

from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue, lookup_logical

ROOT = Path(__file__).resolve().parents[1]


def main(scene):
    if not scene or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in scene):
        raise ValueError('Expected a scene basename')
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    catalogue = read_catalogue(apk)
    logical = f'scene/{scene}/{scene}_content/probe/reflectionprobe_0'
    candidates = [logical + suffix for suffix in ('.cube', '.ktx')]
    selected = next((p for p in candidates if len(lookup_logical(catalogue, p)) == 1), None)
    if selected is None:
        raise ValueError('Probe is missing or ambiguous')
    out = ROOT / 'analysis/battle-visual/reflection' / scene
    out.mkdir(parents=True, exist_ok=True)
    source = out / ('reflectionprobe_0' + Path(selected).suffix)
    provenance = extract(apk, catalogue, selected, source, APK_SHA256)
    levels = []
    decoded = convert([source], out / 'mip0', DEFAULT_DECODER, inspector=DEFAULT_INSPECTOR)
    texture = decoded['textures'][0]['texture']
    if texture['faces'] != 6:
        raise ValueError('Expected an original six-face cube')
    levels.append(decoded)
    for mip in range(1, texture['mip_count']):
        levels.append(convert([source], out / ('mip' + str(mip)), DEFAULT_DECODER,
            mip=mip, inspector=DEFAULT_INSPECTOR))
    if any(len(level['textures'][0]['outputs']) != 6 for level in levels):
        raise ValueError('Missing decoded cube faces')
    report = dict(source=provenance, texture=texture, levels=levels,
        orientationRemapped=False, authoredMipsPreserved=True, appliedInUE=False,
        limitations=['Original RGBA samples only; HDR encoding, cube coordinate basis, probe selection and source BRDF remain unverified.'])
    (out / 'reflection.json').write_text(json.dumps(report, indent=2), 'utf8')
    print(json.dumps(dict(scene=scene, faces=6, mipCount=len(levels), decodedImages=6*len(levels))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene')
    main(parser.parse_args().scene)
