"""Report why a recovered hero fails the source reference-pose skin check.

Reads the per-purpose asset audit written before export. Diagnostic only: no
correction is applied and nothing here makes a failed hero exportable.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from inspect_neox_animation import parse_library, file_sha256
from inspect_neox_model import parse_model, matrix_rows
from export_elsa_animation import quaternion_matrix
from verify_lynn_idle import frame_skin_stats, sampled_to_reference_layout

ROOT = Path(__file__).resolve().parents[1]


def diagnose(character_id, purpose):
    base = ROOT / 'analysis/characters' / ('hero-' + str(character_id).zfill(3)) / purpose
    audit = json.loads((base / 'asset-audit.json').read_text('utf8'))

    def read(logical):
        record = audit['sources'][logical]
        path = Path(record['sample_path'])
        if file_sha256(path) != record['sha256']:
            raise ValueError('Source identity changed')
        return path.read_bytes()

    entry = audit['models'][0]
    model = parse_model(read(entry['path'][:-4] + '.mesh'))
    library = parse_library(read(entry['libraries'][0]), allow_empty_roots=True)
    reference = dict(zip(library['bone_names'], library['reference_pose']))
    missing = [b['name'] for b in model['bones'] if b['name'] not in reference]
    if missing:
        return dict(characterId=character_id, kind='mesh-bones-missing-from-library', missing=missing[:20])
    worlds = {}

    def world(index):
        if index not in worlds:
            bone = model['bones'][index]
            pose = reference[bone['name']]
            local = np.eye(4)
            local[:3, :3] = quaternion_matrix(pose[3:7]) * pose[7:10]
            local[:3, 3] = pose[:3]
            worlds[index] = local if bone['parent'] is None else world(bone['parent']) @ local
        return worlds[index]

    rows = []
    for index, bone in enumerate(model['bones']):
        mesh = np.asarray(matrix_rows(bone['matrix_raw']))
        composed = world(index)
        error = float(np.max(np.abs(composed - mesh)))
        if index in model['used_bones'] and error >= 1e-4:
            rows.append(dict(index=index, name=bone['name'], error=round(error, 5),
                parent=None if bone['parent'] is None else model['bones'][bone['parent']]['name'],
                translationError=round(float(np.max(np.abs(composed[:3, 3] - mesh[:3, 3]))), 5),
                linearError=round(float(np.max(np.abs(composed[:3, :3] - mesh[:3, :3]))), 5)))
    roots = [r for r in rows if r['parent'] not in {x['name'] for x in rows}]
    result = dict(characterId=character_id, kind='weighted-bind-mismatch' if rows else 'reference-matches',
        weightedBones=len(model['used_bones']), mismatchedWeighted=len(rows),
        maxError=max((r['error'] for r in rows), default=0.0),
        mismatchRoots=roots[:12])
    clip_name = audit['selection']['clip']
    clip_json = base / 'poses' / (clip_name + '.json')
    if clip_json.exists():
        clip = json.loads(clip_json.read_text('utf8'))
        values = np.frombuffer((base / 'poses' / (clip_name + '.poses')).read_bytes(), dtype='<f4',
            offset=20).reshape(clip['samples'], clip['bone_count'], 10)
        mapping = clip['bone_mappings'][entry['path'][:-4] + '.mesh']
        result['frame0'] = frame_skin_stats(model, {m['name']: sampled_to_reference_layout(values[0, m['clip_index']])
            for m in mapping})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('character_ids', type=int, nargs='+')
    parser.add_argument('--purpose', choices=('hall', 'battle'), default='battle')
    args = parser.parse_args()
    results = []
    for hid in args.character_ids:
        try:
            results.append(diagnose(hid, args.purpose))
        except Exception as error:
            results.append(dict(characterId=hid, kind='diagnostic-error', error=f'{type(error).__name__}: {error}'))
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
