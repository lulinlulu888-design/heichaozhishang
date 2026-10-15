"""Audit tutorial source/build provenance without executing Cocos or game code."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "legacy/cocos-poc"
OUTPUT = ROOT / "analysis/tutorial-client/build-verification.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    report = {"scope": "Static source, bundle and packaged artifact checks only",
              "ui_verified": False, "device_runtime_verified": False,
              "checks": [], "artifacts": []}

    def check(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise ValueError(name)

    def artifact(path):
        data = path.read_bytes()
        report["artifacts"].append({"path": path.relative_to(ROOT).as_posix(),
                                    "bytes": len(data), "sha256": sha(data)})
        return data

    try:
        check("Cocos strict TypeScript check passed", (ROOT / "analysis/tutorial-client/typescript.exit-code.txt").read_text(encoding="utf-8-sig").strip() == "0")
        for name, template in (("ToolchainProof", "cocos-toolchain-proof"),
                               ("TutorialBattleController", "cocos-tutorial-battle-controller"),
                               ("TutorialBattleView", "cocos-tutorial-battle-view"),
                               ("RecoveredCharacterView", "cocos-recovered-character-view")):
            source = artifact(PROJECT / f"assets/{name}.ts")
            check(f"{name}: generator template matches", source == (ROOT / f"tools/templates/{template}.ts").read_bytes())

        tests = json.loads((ROOT / "analysis/test/tutorial-client/evidence.json").read_text(encoding="utf-8-sig"))
        check("controller HTTP tests match current source", tests["controllerSourceSha256"] ==
              sha((PROJECT / "assets/TutorialBattleController.ts").read_bytes()))
        check("controller HTTP tests passed and cleaned up", bool(tests["tests"]) and
              all(test["status"] == "passed" for test in tests["tests"]) and tests["cleanupComplete"])

        for directory, stages in (("cocos-toolchain", ("build-web",)),
                                  ("cocos-native-model", ("generate-windows", "compile-windows")),
                                  ("cocos-android", ("generate-android",))):
            evidence = ROOT / "analysis" / directory
            fingerprints = json.loads((evidence / "export-source-fingerprints.json").read_text(encoding="utf-8-sig"))
            check(f"{directory}: all export source hashes current", len(fingerprints) == 10 and all(
                sha(Path(item["Path"]).read_bytes()) == item["Hash"].lower() for item in fingerprints))
            for stage in stages:
                check(f"{directory}: {stage} completed", (evidence / f"{stage}.exit-code.txt").read_text(encoding="utf-8-sig").strip() == "36")
        check("Android Gradle compiled", (ROOT / "analysis/cocos-android/compile-android.exit-code.txt").read_text(encoding="utf-8-sig").strip() == "0")

        bundles = {
            "web": PROJECT / "build/web-desktop/assets/main/index.js",
            "windows": PROJECT / "build/windows-model/proj/Debug/Resources/assets/main/index.js",
            "android": PROJECT / "build/android/data/assets/main/index.js",
        }
        packed = {}
        for platform, path in bundles.items():
            packed[platform] = artifact(path)
            text = packed[platform].decode("utf-8")
            check(f"{platform}: controller and view registered", all(
                f'System.register("chunks:///_virtual/{module}.ts"' in text
                for module in ("TutorialBattleController", "TutorialBattleView", "ToolchainProof")))
        check("Windows exported bundle equals executable resources", packed["windows"] ==
              (PROJECT / "build/windows-model/data/assets/main/index.js").read_bytes())
        artifact(PROJECT / "build/windows-model/proj/Debug/hczs-cocos-poc.exe")
        apk = PROJECT / "build/android/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk"
        artifact(apk)
        with zipfile.ZipFile(apk) as archive:
            check("APK contains exact exported tutorial bundle", archive.read("assets/assets/main/index.js") == packed["android"])
            resource_root = PROJECT / 'build/android/data/assets/resources'
            resource_files = sorted(path for path in resource_root.rglob('*') if path.is_file())
            check("APK contains every exact exported resources file", bool(resource_files) and all(
                archive.read('assets/assets/resources/' + path.relative_to(resource_root).as_posix()) == path.read_bytes()
                for path in resource_files))
        for model, directory, filenames in (
            ('elsa', 'cocos-character', ('import-verification.json', 'import-verification-windows.json', 'import-verification-android.json')),
            ('enemy991', 'cocos-enemy', ('import-verification-web.json', 'import-verification-windows.json', 'import-verification-android.json'))):
            for filename in filenames:
                audit = json.loads(artifact(ROOT / 'analysis' / directory / filename))
                check(f"{model}: {filename} audit passed with current inputs", audit['passed'] and audit['model'] == model and
                    bool(audit['checks']) and all(item['passed'] for item in audit['checks']) and
                    bool(audit['inputs']) and all(sha((ROOT / item['path']).read_bytes()) == item['sha256'] for item in audit['inputs']))
        structural = json.loads((ROOT / "analysis/cocos-android/apk-verification.json").read_text(encoding="utf-8-sig"))
        check("APK signature/alignment evidence matches current package", structural["sha256"] == sha(apk.read_bytes()) and
              structural["zip_crc_valid"] and all(item["exit_code"] == 0 for item in structural["checks"].values()) and
              bool(structural["native_libraries"]) and all(item["elf_16k_alignment"] and item["zip_16k_alignment"] and
              item["relro_16k_alignment"] for item in structural["native_libraries"]))
        report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error"] = str(error)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(report["checks"]),
                      "report": OUTPUT.relative_to(ROOT).as_posix(), "error": report.get("error")}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
