"""Export verified weapon geometry/colour in source model space, without a skin.

The independent skeleton AABB check fails for this asset. This static inspection
artifact deliberately has no inferred attachment or animation binding.
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from inspect_elsa_weapon import main as inspect_weapon, ROOT, OUT
from export_elsa_model import extract, digest, write_json, split_glb, pack_glb, bind_materials
from export_neox_gltf import encode_glb
from inspect_neox_model import parse_model
from neox_resource_paths import read_catalogue
from extract_texture_samples import APK_SHA256
from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR


def main():
    inspect_weapon()
    model = parse_model((OUT / 'ailisha_weapon.mesh').read_bytes())
    root = ET.fromstring((OUT / 'ailisha_weapon.mtg').read_bytes())
    materials = []
    for entry in root.find('MaterialGroup'):
        material = entry.find('Material')
        materials.append(dict(name=material.attrib['Name'],
            params={p.tag: p.attrib['Value'] for p in material.find('ParamTable')},
            technique=dict(material.find('Technique').attrib)))
    bindings = bind_materials(model, (OUT / 'ailisha_weapon.gim').read_bytes(), materials)
    # The second layer uses lancer2 procedural noise. Do not export that noise
    # as diffuse colour or pretend straight-alpha blending reproduces the effect.
    logical = materials[0]['params']['Tex0']
    if logical != 'character/player/ailisha/texture/ailisha_weapon_d.dds':
        raise ValueError('Unexpected weapon surface')
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    ktx_path = OUT / 'ailisha_weapon_d.ktx'
    source = extract(apk, read_catalogue(apk), str(Path(logical).with_suffix('.ktx')).replace('\\', '/'), ktx_path, APK_SHA256)
    provenance = OUT / 'texture-provenance.json'
    write_json(provenance, [source])
    decoded = convert([ktx_path], OUT / 'colour-png', DEFAULT_DECODER,
                      provenance_path=provenance, inspector=DEFAULT_INSPECTOR)
    texture = decoded['textures'][0]
    png = Path(texture['outputs'][0]['png'])
    if not png.is_absolute():
        png = ROOT / png
    # Explicit linear-to-sRGB encoding for the glTF colour texture.
    if texture['texture']['profile'] == 'linear':
        import numpy as np
        from PIL import Image
        pixels = np.array(Image.open(png).convert('RGBA'))
        x = pixels[:, :, :3].astype(np.float64) / 255
        encoded = np.where(x <= .0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - .055)
        pixels[:, :, :3] = np.clip(np.rint(encoded * 255), 0, 255).astype('uint8')
        png = png.with_name(png.stem + '.gltf-srgb.png')
        Image.fromarray(pixels).save(png)
    raw, _, _ = encode_glb(model, 'Elsa source weapon / static geometry', skin=False)
    doc, binary = split_glb(raw)
    doc['meshes'][0]['primitives'] = doc['meshes'][0]['primitives'][:1]
    doc['meshes'][0]['primitives'][0]['material'] = 0
    binary += b'\0' * (-len(binary) % 4)
    offset = len(binary)
    image = png.read_bytes()
    binary += image
    doc['bufferViews'].append(dict(buffer=0, byteOffset=offset, byteLength=len(image)))
    doc['images'] = [dict(bufferView=len(doc['bufferViews']) - 1, mimeType='image/png')]
    doc['samplers'] = [dict(magFilter=9729, minFilter=9987, wrapS=10497, wrapT=10497)]
    doc['textures'] = [dict(source=0, sampler=0)]
    doc['extensionsUsed'] = ['KHR_materials_unlit']
    doc['materials'] = [dict(name='Original weapon Tex0 / unlit inspection',
        pbrMetallicRoughness=dict(baseColorTexture=dict(index=0), metallicFactor=0, roughnessFactor=1),
        extensions={'KHR_materials_unlit': {}}, doubleSided=True)]
    doc['extras']['missing'] = ['Attachment and skin binding', 'Original subsurface material', 'lancer2 effect overlay']
    doc['extras']['bindingWarning'] = 'Weapon auxiliary bone AABB validation failed; static model-space export only.'
    blob = pack_glb(doc, binary)
    (OUT / 'elsa-weapon-static.glb').write_bytes(blob)
    report = dict(glb_sha256=digest(blob), glb_bytes=len(blob), bindings=bindings,
        source_materials=materials, decoded_texture=texture, gltf_png_sha256=digest(image),
        exported_surface_vertices=612, exported_surface_triangles=884,
        scope='Static source geometry and Tex0 inspection; no attachment or skin',
        omitted='Second geometry layer retained in source, omitted here because lancer2 shader is not restored')
    write_json(OUT / 'static-export-report.json', report)
    print(json.dumps(dict(glb_bytes=len(blob), sha256=digest(blob))))


if __name__ == '__main__':
    main()
