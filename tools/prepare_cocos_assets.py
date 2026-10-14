"""Stage local recovered examples with provenance; never commit the staged assets."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "clients/cocos-poc"


def main():
    manifest = json.loads((ROOT / "analysis/assets/converted-ktx/manifest.json").read_text(encoding="utf-8"))
    record = next(v for v in manifest["textures"]
                  if v.get("provenance", {}).get("member") == "assets/res/uires.npk"
                  and v["provenance"].get("index") == 3481)
    png = next(v for v in record["outputs"] if v["mip"] == 0 and v["face"] == 0)
    examples = [(png["png"], "assets/resources/recovered/portrait.png", png["png_sha256"])]
    glb = ROOT / "analysis/model-conversion/character.06424.skinned.glb"
    if glb.exists():
        examples.append((str(glb.relative_to(ROOT)), "assets/imported-models/character.06424.skinned.glb", None))
    provenance = {"scope": "Recovered character portraits plus independent texture/mesh examples; no texture/mesh shared identity inferred", "files": []}
    for source_name, destination_name, expected_hash in examples:
        source = ROOT / source_name
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if expected_hash and digest != expected_hash:
            raise RuntimeError(f"Source checksum mismatch: {source}")
        destination = PROJECT / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        provenance["files"].append({"source": source_name, "destination": destination_name, "sha256": digest,
                                  "source_manifest": "analysis/assets/converted-ktx/manifest.json" if expected_hash else "analysis/model-conversion/"})
    portrait_manifest = "analysis/resource-mapping/characters/portraits.json"
    portraits = json.loads((ROOT / portrait_manifest).read_text(encoding="utf-8"))
    characters = json.loads((ROOT / "analysis/game-data/characters.json").read_text(encoding="utf-8"))
    character_paths = {row["id"]: row["fields"]["CharImage"] for row in characters["rows"]}
    seen = set()
    for portrait in portraits:
        character_id = portrait["character_id"]
        if character_id in seen or character_paths.get(character_id) != portrait["logical_path"]:
            raise RuntimeError(f"Unverified or duplicate portrait mapping: {character_id}")
        seen.add(character_id)
        source = ROOT / portrait["png"]
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != portrait["png_sha256"]:
            raise RuntimeError(f"Source checksum mismatch: {source}")
        destination_name = f"assets/resources/recovered/characters/{character_id}.png"
        destination = PROJECT / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        provenance["files"].append({"source": portrait["png"], "destination": destination_name,
                                  "sha256": digest, "source_manifest": portrait_manifest,
                                  "character_id": character_id, "logical_path": portrait["logical_path"],
                                  "apk_member": portrait["member"], "npk_index": portrait["index"],
                                  "name_hash": portrait["name_hash"], "texture_sha256": portrait["source_sha256"]})
    if seen != set(character_paths):
        raise RuntimeError("Not all recovered sample characters have verified portraits")
    animation_manifest = ROOT / 'analysis/elsa-animation/manifest.json'
    if animation_manifest.exists():
        animation = json.loads(animation_manifest.read_text(encoding='utf8'))
        if animation['file'] != 'elsa-yangcheng.animated.glb' or animation['clipNames'] != ['stand_idle', 'skin']:
            raise RuntimeError('Unexpected recovered animation manifest')
        source = animation_manifest.parent / animation['file']
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != animation['glbSha']:
            raise RuntimeError('Animated character source checksum mismatch')
        destination_name = 'assets/resources/recovered/models/elsa/elsa.glb'
        destination = PROJECT / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        provenance['files'].append({'source': source.relative_to(ROOT).as_posix(), 'destination': destination_name,
                                    'sha256': digest, 'source_manifest': animation_manifest.relative_to(ROOT).as_posix(),
                                    'character_id': 1, 'clips': animation['clipNames'],
                                    'scope': 'Original sampled poses; colour-reference materials, not original toon shading'})
    else:
        raise RuntimeError('Animated Elsa asset is missing. Run tools/export_elsa_animation.py first.')
    lynn_report = ROOT / 'analysis/characters/lynn/export/export-report.json'
    lynn = json.loads(lynn_report.read_text(encoding='utf8'))
    source = ROOT / 'analysis/characters/lynn/export/lynn-idle.colour-reference.glb'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != lynn['sha256']:
        raise RuntimeError('Lynn animated source checksum mismatch')
    destination_name = 'assets/resources/recovered/models/lynn/lynn.glb'
    destination = PROJECT / destination_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    provenance['files'].append({'source': source.relative_to(ROOT).as_posix(),
        'destination': destination_name, 'sha256': digest, 'character_id': 2,
        'source_manifest': lynn_report.relative_to(ROOT).as_posix(), 'clips': ['idle_1'],
        'scope': 'Original local TRS and inverse binds; unlit colour reference only'})
    enemy_manifest = ROOT / 'analysis/tutorial-enemy-animated/manifest.json'
    enemy = json.loads(enemy_manifest.read_text(encoding='utf8'))
    if enemy['file'] != 'tutorial-enemy-991.animated.glb' or enemy['clipNames'] != ['idle', 'fire']:
        raise RuntimeError('Unexpected tutorial enemy animation manifest')
    source = enemy_manifest.parent / enemy['file']
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != enemy['glbSha'] or digest != 'fb9286f587c7c24b7344e5116318c45224add56deaacf36d21ed22b2aa0276ea':
        raise RuntimeError('Tutorial enemy source checksum mismatch')
    destination_name = 'assets/resources/recovered/models/enemy991/enemy991.glb'
    destination = PROJECT / destination_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    meta_path = destination.with_suffix('.glb.meta')
    if not meta_path.exists():
        meta_path.write_text(json.dumps({'ver': '2.3.14', 'importer': 'gltf', 'imported': False,
            'uuid': 'c744184a-ec92-4c0e-8f59-7c763f7c5192', 'files': [], 'subMetas': {},
            'userData': {}}, indent=2) + '\n', encoding='utf8')
    provenance['files'].append({'source': source.relative_to(ROOT).as_posix(), 'destination': destination_name,
        'sha256': digest, 'source_manifest': enemy_manifest.relative_to(ROOT).as_posix(),
        'monster_id': 991, 'clips': enemy['clipNames'],
        'scope': 'Original idle/fire samples; Tex0 colour reference only, no original emission or skill mapping'})
    (PROJECT / "asset-provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from prepare_cocos_prologue import main as prepare_prologue
    prepare_prologue()
    from prepare_cocos_cards import main as prepare_cards
    prepare_cards()
    print(json.dumps(provenance, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
