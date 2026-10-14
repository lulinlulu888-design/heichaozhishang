"""Create the isolated 3.8.8 proof from shipped official 2D templates."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / ".tools/cocos/3.8.8"
PROJECT = ROOT / "clients/cocos-poc"
SCENE_UUID = "1cce6d16-610f-45bd-8b9f-63628732ec0f"
SCRIPT_UUID = "98d6ba2e-cfc1-44e9-8f01-3237a0dfc5ba"


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    if PROJECT.exists():
        raise SystemExit(f"Refusing to replace existing project: {PROJECT}")
    shutil.copytree(EDITOR / "resources/templates/empty-2d", PROJECT)
    with (PROJECT / ".gitignore").open("a", encoding="utf-8") as ignore:
        ignore.write("\n/assets/resources/recovered/\n/assets/resources/recovered.meta\n/assets/imported-models/\n/assets/imported-models.meta\n/settings/v2/packages/information.json\n")
    write_json(PROJECT / "package.json", {
        "name": "hczs-cocos-poc", "uuid": "ba2a6c96-ee88-4fbb-bbcf-19912dbd0dc0",
        "creator": {"version": "3.8.8"}, "private": True,
    })
    assets = PROJECT / "assets"
    shutil.copytree(ROOT / "tools/templates/cocos-web", PROJECT / "build-templates/web-desktop")
    assets.mkdir()
    template = EDITOR / "resources/resources/3d/engine/editor/assets/default_file_content/scene/scene-2d.scene"
    scene = json.loads(template.read_text(encoding="utf-8"))
    scene[0]["_name"] = scene[1]["_name"] = "ToolchainProof"
    scene[1]["_id"] = SCENE_UUID
    # Creator's serialized script class ID: first five hex characters, followed by
    # base64 pairs encoding the remaining groups of three hex digits (23 chars).
    hexid = SCRIPT_UUID.replace("-", "")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    script_id = hexid[:5] + "".join(alphabet[int(hexid[i:i+3], 16) >> 6] + alphabet[int(hexid[i:i+3], 16) & 63] for i in range(5, 32, 3))
    component_index = len(scene)
    scene.append({"__type__": script_id, "_name": "", "_objFlags": 0,
                  "node": {"__id__": 2}, "_enabled": True, "__prefab": None,
                  "_id": "hczs-toolchain-proof-component"})
    scene[2]["_components"].append({"__id__": component_index})
    write_json(assets / "ToolchainProof.scene", scene)
    meta = json.loads(template.with_suffix(".scene.meta").read_text(encoding="utf-8"))
    meta["uuid"] = SCENE_UUID
    write_json(assets / "ToolchainProof.scene.meta", meta)
    write_json(assets / "ToolchainProof.ts.meta", {"ver": "4.0.24", "importer": "typescript", "imported": True,
               "uuid": SCRIPT_UUID, "files": [], "subMetas": {}, "userData": {}})
    source = ROOT / "tools/templates/cocos-toolchain-proof.ts"
    shutil.copyfile(source, assets / "ToolchainProof.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-recovered-character-view.ts", assets / "RecoveredCharacterView.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-tutorial-battle-controller.ts", assets / "TutorialBattleController.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-tutorial-battle-view.ts", assets / "TutorialBattleView.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-target-arrow-geometry.ts", assets / "TargetArrowGeometry.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-target-arrow-view.ts", assets / "TargetArrowView.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-card-selection-view.ts", assets / "CardSelectionView.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-enemy-turn-presentation.ts", assets / "EnemyTurnPresentation.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-end-turn-view.ts", assets / "EndTurnView.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-victory-title-view.ts", assets / "VictoryTitleView.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-prologue-scene-view.ts", assets / "PrologueSceneView.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-city-scene-view.ts", assets / "CitySceneView.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-battle-audio.ts", assets / "BattleAudio.ts")
    shutil.copyfile(ROOT / "tools/templates/cocos-prologue-lighting.ts", assets / "PrologueLighting.ts")
    engine_path = PROJECT / "settings/v2/packages/engine.json"
    engine = json.loads(engine_path.read_text(encoding="utf8"))
    config = engine['modules']['configs']['defaultConfig']
    for module in ('3d', 'skeletal-animation'):
        config['cache'][module]['_value'] = True
        if module not in config['includeModules']:
            config['includeModules'].append(module)
    config['includeModules'].sort()
    write_json(engine_path, engine)
    write_json(PROJECT / "build-web.json", {
        "name": "hczs-cocos-poc", "platform": "web-desktop", "debug": True,
        "buildPath": "project://build", "outputName": "web-desktop",
        "startScene": SCENE_UUID, "scenes": [{"url": "db://assets/ToolchainProof.scene", "uuid": SCENE_UUID}],
    })
    for platform in ("mac", "ios"):
        shutil.copyfile(ROOT / f"tools/templates/cocos-build-{platform}.json", PROJECT / f"build-{platform}.json")
    print(PROJECT)


if __name__ == "__main__":
    main()
