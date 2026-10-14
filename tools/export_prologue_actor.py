"""Export the actual prologue actor with its own bind matrices and source idle.

Consumes provenance-bearing extractions; does not claim scripted scene playback.
"""
import json
from export_elsa_model import ROOT, digest, parse_materials, bind_materials, encode_reference, split_glb, pack_glb, write_json
from export_elsa_animation import load_clip, encode, validate_roundtrip, parse_library
from inspect_neox_model import parse_model
from extract_texture_samples import APK_SHA256


def run(with_attacks=False, with_reactions=False, with_battle_idle=False):
    with_reactions = with_reactions or with_battle_idle
    with_attacks = with_attacks or with_reactions
    source = ROOT/'analysis/battle-visual/scene-export/source'
    hashes = {
        'gim': 'cec24d79e67c9bc86993d0ab4115f484d6e222f0954252d02d8505899d0eccf7',
        'mesh': '37475c3438660c0cff65febfdf908a8aaec918344db1a6a547ef893b59e6b3f5',
        'mtg': '672f08c5a8280f407db221142764c93b7f414e3c24865f90366480ec72323a74',
    }
    payloads = {}
    for ext, expected in hashes.items():
        p = source/f'File_26.{ext}'
        payloads[ext] = p.read_bytes()
        provenance = json.loads(p.with_suffix(p.suffix+'.provenance.json').read_text('utf8'))
        if digest(payloads[ext]) != expected or provenance['sha256'] != expected or provenance['apk_sha256'] != APK_SHA256:
            raise ValueError('scene actor extraction identity mismatch')
    if b'character/player/ailisha/ailisha.gisacl' not in payloads['gim']:
        raise ValueError('scene actor animation library reference absent')
    model = parse_model(payloads['mesh'])
    materials = parse_materials(payloads['mtg'])
    bindings = bind_materials(model, payloads['gim'], materials)
    textures = json.loads((ROOT/'analysis/elsa-model/export-report.json').read_text('utf8'))['decoded_colour_textures']
    base, _, bind = encode_reference(model, bindings, materials, textures)
    doc, binary = split_glb(base)
    doc['meshes'][0]['name'] = 'PrologueElsa'
    for n in doc['nodes']:
        if 'mesh' in n:
            n['name'] = 'PrologueElsa'
    base = pack_glb(doc, binary)
    recovered = ROOT/'analysis/animation/recovered'
    library = parse_library((recovered/'ailisha.gisacl').read_bytes())
    if library['sha256'] != '2eda877730287d1c0843150eb4050d5b46ab8e910e7d9f3828609b61a98c5b41':
        raise ValueError('source library changed')
    names = [doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']]
    clips = [load_clip(recovered, 'stand_idle', library, names)]
    if with_attacks:
        attacks = ROOT/'analysis/battle-visual/skill-animation'
        clips.extend(load_clip(attacks, name, library, names) for name in
                     ('fire_1', 'crit_1', 'fire_1_1', 'fire_1_3', 'fire_2'))
    if clips[0]['metadata']['source']['apk_sha256'] != APK_SHA256:
        raise ValueError('clip APK identity mismatch')
    if with_reactions:
        reactions = ROOT/'analysis/battle-visual/player-reactions'
        clips.extend(load_clip(reactions, name, library, names) for name in ('hit_2', 'death'))
    if with_battle_idle:
        clips.append(load_clip(ROOT/'analysis/battle-visual/battle-idle', 'idle_1', library, names))
    glb, reports, error = encode(base, clips)
    animated, binary = split_glb(glb)
    # This measurement belongs to the different yangcheng mesh, not this actor.
    animated['extras'].pop('knownBindDifference', None)
    animated['extras']['scenePlaybackScope'] = 'Source stand_idle selected for preview; original scripted action sequence not recovered.'
    if with_attacks:
        animated['extras']['scenePlaybackScope'] = 'Original idle and five attack poses; original runtime sequence, hit timing and effects not recovered.'
    if with_reactions:
        animated['extras']['scenePlaybackScope'] = 'Original idle, five attacks, hit_2 and death poses; reaction selection and timing reconstructed.'
    if with_battle_idle:
        animated['extras']['scenePlaybackScope'] = 'Includes source battle IDLE_1 -> idle_1; low-health state selection and full effects remain incomplete.'
    glb = pack_glb(animated, binary)
    verified = validate_roundtrip(base, glb, clips)
    out = ROOT/'analysis/battle-visual'/('actor-battle-idle' if with_battle_idle else 'actor-reactions' if with_reactions else 'actor-attacks' if with_attacks else 'actor')
    out.mkdir(parents=True, exist_ok=True)
    (out/'prologue-elsa.glb').write_bytes(glb)
    report = dict(source_hashes=hashes, library_sha256=library['sha256'], bind_validation=bind,
                  max_bind_trs_error=error, clips=reports, verification=verified,
                  glb_sha256=digest(glb), glb_bytes=len(glb), scope=animated['extras']['scenePlaybackScope'])
    write_json(out/'report.json', report)
    return dict(glb_bytes=len(glb), verification=verified)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-attacks', action='store_true')
    parser.add_argument('--with-reactions', action='store_true')
    parser.add_argument('--with-battle-idle', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.with_attacks, args.with_reactions, args.with_battle_idle), indent=2))
