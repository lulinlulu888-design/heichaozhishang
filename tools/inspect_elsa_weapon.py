"""Recover Elsa's authored weapon and verify its skin binding without target execution.

Local static evidence, not a REA runtime result. Does not interpret BindType 263.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from export_elsa_model import extract, write_json, digest
from extract_texture_samples import APK_SHA256
from inspect_neox_model import ModelError, parse_model, validate_bind_pose
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/weapon'
HASHES = {
    'gim': 'dc87eeace7351727f86eca52a1a3cea5bcd5dd0f06e7696435da0f170a62c528',
    'mesh': '674bff2365e5a9db6ed65939a7ec3977b3d8f26218058f54e29758823dd4e06c',
    'mtg': '6d26d4b0a2fc004adf1f109e695ac4c930e226ea52527dc981a884648000f2eb',
}


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    actor_dir = ROOT / 'analysis/battle-visual/scene-export/source'
    gim = (actor_dir / 'File_26.gim').read_bytes()
    mesh = (actor_dir / 'File_26.mesh').read_bytes()
    if digest(gim) != 'cec24d79e67c9bc86993d0ab4115f484d6e222f0954252d02d8505899d0eccf7' or digest(mesh) != '37475c3438660c0cff65febfdf908a8aaec918344db1a6a547ef893b59e6b3f5':
        raise ValueError('Actor source identity changed')
    sockets = [s for s in ET.fromstring(gim).find('Sockets') if s.attrib['Name'] == 'wuqi']
    if len(sockets) != 1:
        raise ValueError('Weapon socket must be unique')
    socket = sockets[0]
    objects = list(socket.find('BoundObject'))
    logical = objects[0].attrib['Name']
    if len(objects) != 1 or logical != 'character/player/ailisha/ailisha_weapon.gim':
        raise ValueError('Unexpected weapon reference')
    OUT.mkdir(parents=True, exist_ok=True)
    catalogue = read_catalogue(apk)
    sources = {}
    for ext, expected in HASHES.items():
        path = str(Path(logical).with_suffix('.' + ext)).replace('\\', '/')
        sources[ext] = extract(apk, catalogue, path, OUT / Path(path).name, APK_SHA256)
        if sources[ext]['sha256'] != expected:
            raise ValueError('Weapon source identity changed')
    weapon = parse_model((OUT / 'ailisha_weapon.mesh').read_bytes())
    try:
        bind = validate_bind_pose(weapon)
    except ModelError as error:
        # Keep a failed independent check as evidence; do not export a skin
        # using a matrix convention that this asset has not corroborated.
        bind = dict(validated=False, error=str(error))
    actor = parse_model(mesh)
    by_name = {b['name']: b for b in actor['bones']}
    used = sorted({j for js, ws in zip(weapon['joints'], weapon['weights']) for j, w in zip(js, ws) if w > 0})
    rows = []
    for i in used:
        bone = weapon['bones'][i]
        other = by_name.get(bone['name'])
        rows.append(dict(index=i, name=bone['name'], source_bind=bone['matrix_raw'],
            actor_bind=other['matrix_raw'] if other else None,
            max_bind_difference=max(abs(a-b) for a, b in zip(bone['matrix_raw'], other['matrix_raw'])) if other else None))
    result = dict(evidence_kind='Hash-verified local static extraction; no native runtime evidence',
        sources=sources, socket=dict(socket.attrib), bound_object=dict(objects[0].attrib),
        vertices=weapon['vertex_count'], triangles=weapon['triangle_count'], bones=len(weapon['bones']),
        used_bones=rows, bind_validation=bind,
        all_vertices_single_joint_unit_weight=all(sum(w > 0 for w in ws) == 1 and max(ws) == 1 for ws in weapon['weights']),
        unresolved=['Weapon bind matrix/local AABB discrepancy must be resolved before skin export',
                    'Native BindType 263 semantics and visibility triggers',
                    'Preserve weapon inverse bind; actor bind cannot be substituted',
                    'Surface colour shader and lancer2 additive effect',
                    'Animated attachment and rendered verification'])
    write_json(OUT / 'binding-report.json', result)
    print(json.dumps({k: result[k] for k in ('vertices', 'triangles', 'bones', 'used_bones', 'all_vertices_single_joint_unit_weight')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
