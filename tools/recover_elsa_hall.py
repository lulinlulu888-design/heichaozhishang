"""Recover Elsa's exact source-configured home_stand_idle_1 on original LOD0.

Reuse the pinned ACL sampler and original Elsa GLB encoder. Preserve mesh,
inverse-bind matrices, original texture pixels and known source toe difference.
This exports recovery inputs; UE playback/material fidelity remain separate.
"""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from export_elsa_model import extract, split_glb, write_json
from export_elsa_animation import encode, load_clip, validate_roundtrip
from extract_texture_samples import APK_SHA256
from inspect_neox_animation import parse_clip, parse_library, map_bones
from sample_lynn_idle import sample_pinned
from trace_first_encounter import literal_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/elsa-hall'
BASE_SHA = '84956d9eeec1285c4de49faa6f0def6453663f288fb40352cf23deec6479a35f'
CLIP = 'home_stand_idle_1'
CLIP_PATH = 'character/player/ailisha/ailisha_gis_acl/home_stand_idle_1.gisacl'
CLIP_SHA = 'd0dd4e2ed98af4662510ad4d1a394cbd946fb42f01fde6d34460a8f7f9203bb6'
ACL_SHA = '8821aee0cfe7ca014ac1e783db847f41a762097a473b0b87cc3c8b4729b1977a'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('Original APK changed')
    table = literal_table(1955, {0, 20})
    if any(row['fields']['ANIM_STATES_HOME_STAND_IDLE'] != CLIP for row in table['rows']):
        raise ValueError('Elsa hall animation source configuration changed')
    levels = literal_table(6328, {16, 17, 18, 19})
    row0 = next(row['fields'] for row in levels['rows'] if row['id'] == 16)
    if row0['LEVEL'] != 0 or row0['MODEL_PATH'] != 'character/player/ailisha/ailisha_yangcheng.gim':
        raise ValueError('Elsa source LOD0 mapping changed')
    base_path = ROOT / 'analysis/elsa-model/elsa-yangcheng.colour-reference.glb'
    base = base_path.read_bytes()
    if hashlib.sha256(base).hexdigest() != BASE_SHA:
        raise ValueError('Original geometry/image GLB changed')
    document, _ = split_glb(base)
    sources = json.loads((ROOT / 'analysis/elsa-model/export-report.json').read_text('utf8'))['sources']
    gim = Path(sources['gim']['sample_path']).read_bytes()
    if hashlib.sha256(gim).hexdigest() != sources['gim']['sha256']:
        raise ValueError('Source GIM changed')
    library_paths = [e.attrib['value'] for e in ET.fromstring(gim).findall('GisFiles/*')]
    if len(library_paths) != 1:
        raise ValueError('Source GIM animation library is ambiguous')
    catalogue = json.loads((ROOT / 'analysis/resource-mapping/npk-indices.json').read_text('utf8'))
    library_path = OUT / 'ailisha.gisacl'
    library_source = extract(apk, catalogue, library_paths[0], library_path, APK_SHA256)
    library = parse_library(library_path.read_bytes())
    source_path = OUT / (CLIP + '.gisacl')
    clip_source = extract(apk, catalogue, CLIP_PATH, source_path, APK_SHA256)
    raw = source_path.read_bytes()
    parsed = parse_clip(raw)
    if parsed['sha256'] != CLIP_SHA or parsed['acl_sha256'] != ACL_SHA:
        raise ValueError('Pinned Elsa hall clip changed')
    names = [document['nodes'][i]['name'] for i in document['skins'][0]['joints']]
    mapping = map_bones(library, parsed, names)
    if len(mapping) != 180 or len(names) != 180:
        raise ValueError('Unexpected Elsa skeleton mapping')
    parsed.update(source=clip_source, library_sha256=library['sha256'], bone_mapping=mapping,
                  library_record=next(r for r in library['clips'] if r['name'] == CLIP))
    write_json(OUT / (CLIP + '.json'), parsed)
    sample_pinned(OUT, {CLIP: ACL_SHA}, 'elsa-hall-idle', 1)
    clip = load_clip(OUT, CLIP, library, names)
    glb, animations, bind_error = encode(base, [clip])
    verified = validate_roundtrip(base, glb, [clip])
    if verified[0]['moving_tracks'] == 0 or verified[0]['max_vertex_displacement_from_first_frame'] <= 1e-4:
        raise ValueError('Recovered source hall idle has no measurable motion')
    target = OUT / 'elsa-hall-idle.colour-reference.glb'
    target.write_bytes(glb)
    report = dict(output=str(target), sha256=hashlib.sha256(glb).hexdigest(), bytes=len(glb),
                  character_id=1, model_path=row0['MODEL_PATH'], source_lod_row=16, source_lod_level=0,
                  base_glb=str(base_path), base_glb_sha256=BASE_SHA, source_apk_sha256=APK_SHA256,
                  source_model=sources, source_library=library_source, animations=animations,
                  verification=verified, max_bind_matrix_to_trs_error=bind_error,
                  known_bind_difference=dict(mesh_joint=50, name='bip001 r toe0', degrees=3.811740265875115,
                                             affected_vertices=39, correction_applied=False),
                  source_tables=dict(entities=table, levels=levels),
                  limitations=['Original geometry/images/inverse-bind bytes retained; known source right-toe bind difference retained.',
                               'Original home_stand_idle_1 sampled exactly; events, physics and NeoX toon shaders are not restored.',
                               'CPU numerical validation does not prove Unreal animation playback or material appearance.'])
    write_json(OUT / 'export-report.json', report)
    print(json.dumps(dict(output=str(target), sha256=report['sha256'], clip=CLIP,
                          samples=clip['frames'], channels=animations[0]['channels'],
                          duration=animations[0]['duration_source_seconds'], moving_tracks=verified[0]['moving_tracks'])))


if __name__ == '__main__':
    main()
