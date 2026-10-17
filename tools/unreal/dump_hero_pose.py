"""Dump native component-space bone positions of one imported battle hero at t=0.

Run with -ExecCmds="py <this file>" -HczsHeroId=N. Read-only diagnostic.
"""
import json
import re
from pathlib import Path

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
hero = int(re.search(r'-HczsHeroId=(\d+)', u.SystemLibrary.get_command_line())[1])
report = json.loads((ROOT / 'analysis/characters' / ('hero-' + str(hero).zfill(3)) / 'battle/export/export-report.json').read_text('utf8'))
folder = '/Game/Recovered/Heroes/Hero' + str(hero).zfill(3) + '/Battle/v_' + report['sha256'][:16]
objects = [u.load_asset(p) for p in u.EditorAssetLibrary.list_assets(folder, True, False)]
mesh = next(a for a in objects if isinstance(a, u.SkeletalMesh))
anim = next(a for a in objects if isinstance(a, u.AnimSequence))
options = u.AnimPoseEvaluationOptions()
options.set_editor_property('optional_skeletal_mesh', mesh)
result = {}
for label, pose in (('anim0', u.AnimPoseExtensions.get_anim_pose_at_time(anim, 0.0, options)),
                    ('ref', u.AnimPoseExtensions.get_reference_pose(mesh.get_editor_property('skeleton')))):
    rows = {}
    for name in u.AnimPoseExtensions.get_bone_names(pose):
        t = u.AnimPoseExtensions.get_bone_pose(pose, name, u.AnimPoseSpaces.WORLD)
        p = t.translation
        rows[str(name)] = [p.x, p.y, p.z]
    result[label] = rows
out = ROOT / 'runtime' / ('hero-pose-' + str(hero).zfill(3) + '.json')
out.write_text(json.dumps(result), 'utf8')
u.SystemLibrary.quit_editor()
