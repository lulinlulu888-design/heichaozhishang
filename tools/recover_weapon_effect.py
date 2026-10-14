"""Recover lancer2 source, noise textures and overlay geometry; no APK execution."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from export_elsa_model import ROOT, extract, write_json, digest, split_glb, pack_glb, bind_materials
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue
from inspect_neox_model import parse_model
from export_neox_gltf import encode_glb
from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR

OUT = ROOT / 'analysis/battle-visual/weapon/effect'
SOURCES = {
 'shader/lancer2.fx': 'f26a95349b03ea7bf9077e586f07f0c9bd2ddfb92f667a4f151e39561f9d2480',
 'effects/tex/wenli/noise_gq_rlt_01.ktx': '8a3219bc64a2859422ab1fe667a290992279adbfce9d41b32de420a9d1fc6ae0',
 'effects/tex/wenli/noise_100.ktx': '2f678b8697f37dfce7f1dd75f2361c89e06e8ce6ff8ae0b0ff23eba78f89b254',
 'shader/shaderlib/function.fxl': 'c08dae6dd5503a004e6cef264085ebe091a98199fbd3c038581d583858423e72',
}


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    catalogue = read_catalogue(apk)
    sources = []
    for logical, expected in SOURCES.items():
        source = extract(apk, catalogue, logical, OUT / Path(logical).name, APK_SHA256)
        if source['sha256'] != expected:
            raise ValueError('Effect input changed')
        sources.append(source)
    provenance = OUT / 'textures.json'
    texture_sources = [s for s in sources if s['logical_path'].endswith('.ktx')]
    write_json(provenance, texture_sources)
    converted = convert([Path(s['sample_path']) for s in texture_sources], OUT / 'png', DEFAULT_DECODER,
        provenance_path=provenance, inspector=DEFAULT_INSPECTOR)
    parent = OUT.parent
    model = parse_model((parent / 'ailisha_weapon.mesh').read_bytes())
    if model['sha256'] != '674bff2365e5a9db6ed65939a7ec3977b3d8f26218058f54e29758823dd4e06c':
        raise ValueError('Weapon mesh changed')
    mtg = (parent / 'ailisha_weapon.mtg').read_bytes()
    if digest(mtg) != '6d26d4b0a2fc004adf1f109e695ac4c930e226ea52527dc981a884648000f2eb':
        raise ValueError('Weapon material changed')
    elements = [e.find('Material') for e in ET.fromstring(mtg).find('MaterialGroup')]
    bindings = bind_materials(model, (parent / 'ailisha_weapon.gim').read_bytes(),
        [dict(name=e.attrib['Name']) for e in elements])
    material = elements[1]
    parameters = {e.tag: e.attrib['Value'] for e in material.find('ParamTable')}
    macros = {e.attrib['Key']: e.attrib['Val'] for e in material.find('ShaderMacro')}
    if macros != {'BLOOM_SUPPORT': 'TRUE'}:
        raise ValueError('Unexpected material macros')
    blob, _, _ = encode_glb(model, 'Elsa original lancer2 overlay / static', skin=False)
    doc, binary = split_glb(blob)
    doc['meshes'][0]['primitives'] = doc['meshes'][0]['primitives'][1:]
    doc['extras']['missing'] = ['Runtime shader supplied separately', 'Native HDR/bloom/blend equivalence']
    blob = pack_glb(doc, binary)
    (OUT / 'weapon-overlay.glb').write_bytes(blob)
    report = dict(sources=sources, textures=converted['textures'], parameters=parameters, macros=macros,
        bindings=bindings, glb_sha256=digest(blob), glb_bytes=len(blob),
        formula=dict(distortion_uv='uv + time * (0.1, -0.1)',
                     colour_uv='uv + distortion.r * 0.1 + time * (0.1, 0.2)',
                     linear_rgb='srgb_to_linear(noise.rgb) * 3 * srgb_to_linear((1, 0.207843, 0.470588))',
                     alpha='noise.a'),
        source_lines=dict(vertex_distortion_uv=[546, 558], fragment=[598, 655]),
        limitations=['Native runtime macro overrides unobserved; sRGB conversion may be piecewise, power 2.2 or square', 'TransparentMode 5 mapping not established',
                    'HDR packing/bloom pipeline not ported', 'MipLODBias -10 not reproduced'])
    write_json(OUT / 'report.json', report)
    print(json.dumps(dict(glb_bytes=len(blob), textures=len(converted['textures']), parameters=parameters)))


if __name__ == '__main__':
    main()
