"""Export source enemy idle/fire/skill_2/skill_3, preserving old two-clip artifacts."""
from export_tutorial_enemy_animation import ROOT, load_inputs, encode, validate_roundtrip, sha, save_json
from export_elsa_animation import load_clip
from inspect_neox_animation import parse_library
from export_elsa_model import split_glb


def main():
    old = ROOT/'analysis/tutorial-enemy-animation'
    out = ROOT/'analysis/battle-visual/enemy-skills'
    base, clips, source_hash = load_inputs(ROOT/'analysis/tutorial-enemy/tutorial-enemy-991.colour-reference.glb', old)
    library = parse_library((old/'library.gisacl').read_bytes())
    doc, _ = split_glb(base)
    names = [doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']]
    clips.extend(load_clip(out, name, library, names) for name in ('skill_2', 'skill_3'))
    blob, reports, error = encode(base, clips, ('idle', 'fire', 'skill_2', 'skill_3'))
    verification = validate_roundtrip(base, blob, clips)
    if sum(r['sample_count_verified'] for r in verification) != 17934:
        raise ValueError('Incomplete four-clip sampling')
    if any(r['moving_tracks'] < 1 for r in verification):
        raise ValueError('Missing motion')
    (out/'enemy-skills.glb').write_bytes(blob)
    save_json(out/'report.json', dict(glb_sha256=sha(blob), glb_bytes=len(blob),
        base_sha256=sha(base), original_summary_sha256=source_hash,
        clips=reports, verification=verification, max_bind_trs_error=error,
        scope='Source poses; runtime events, effects and timing remain incomplete'))
    print(sha(blob), len(blob), 'verified bone samples: 17934')


if __name__ == '__main__':
    main()
