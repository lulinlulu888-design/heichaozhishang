"""Verify current Android export provenance and exact APK resource bytes; no device execution."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from verify_end_turn_content import verify_end_turn
from verify_audio_content import verify_audio
from verify_health_content import verify_health
from verify_pile_content import verify_piles
from verify_result_content import verify_result
from verify_city_content import verify_city

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT/'legacy/cocos-poc'
EVIDENCE = ROOT/'analysis/cocos-android'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main(variant='device'):
    if variant not in ('device', 'emulator'):
        raise ValueError('Unknown Android variant')
    output_name = 'android-emulator' if variant == 'emulator' else 'android'
    EVIDENCE = ROOT / ('analysis/cocos-android-emulator' if variant == 'emulator' else 'analysis/cocos-android')
    report = dict(scope='Current export fingerprints and exact packaged data only; no Android runtime validation',
        variant=variant, checks=[], device_runtime_verified=False)
    def check(name, condition):
        report['checks'].append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise ValueError(name)
    try:
        fingerprints = json.loads((EVIDENCE/'export-source-fingerprints.json').read_text('utf-8-sig'))
        check('All exported source fingerprints are current', bool(fingerprints) and all(
            sha(Path(row['Path']).read_bytes()) == row['Hash'].lower() for row in fingerprints))
        check('Battle view and scene templates match', all(
            (PROJECT/f'assets/{name}.ts').read_bytes() == (ROOT/f'tools/templates/{template}.ts').read_bytes()
            for name,template in [('TutorialBattleView','cocos-tutorial-battle-view'),('PrologueSceneView','cocos-prologue-scene-view'),
                ('TargetArrowView','cocos-target-arrow-view'),('TargetArrowGeometry','cocos-target-arrow-geometry'),
                ('CardSelectionView','cocos-card-selection-view'),
                ('EndTurnView','cocos-end-turn-view'),('EnemyTurnPresentation','cocos-enemy-turn-presentation')]))
        check('Creator export succeeded', (EVIDENCE/'generate-android.exit-code.txt').read_text('utf-8-sig').strip()=='36')
        check('Gradle compilation succeeded', (EVIDENCE/'compile-android.exit-code.txt').read_text('utf-8-sig').strip()=='0')
        apk = PROJECT/f'build/{output_name}/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk'
        report['apk'] = str(apk)
        report['apk_sha256'] = sha(apk.read_bytes())
        structural = json.loads((EVIDENCE/'apk-verification.json').read_text('utf8'))
        check('Structural verification applies to this APK', structural['sha256']==report['apk_sha256'] and
            structural['variant'] == variant and
            structural['zip_crc_valid'] and all(r['exit_code']==0 for r in structural['checks'].values()) and
            bool(structural['native_libraries']) and all(r['elf_16k_alignment'] and r['zip_16k_alignment'] and r['relro_16k_alignment'] for r in structural['native_libraries']))
        data_root = PROJECT/f'build/{output_name}/data'
        files = sorted(p for p in data_root.rglob('*') if p.is_file())
        entries = []
        with zipfile.ZipFile(apk) as archive:
            for path in files:
                member = 'assets/'+path.relative_to(data_root).as_posix()
                data = path.read_bytes()
                if archive.read(member) != data:
                    raise ValueError(f'Packaged data differs: {member}')
                entries.append(dict(member=member,bytes=len(data),sha256=sha(data)))
        check('Every exported data file is byte-identical in APK', bool(entries))
        report['files'] = entries
        # The compiled bundle must include the new asset-loading paths, not merely archive names.
        bundle = (data_root/'assets/main/index.js').read_text('utf8')
        check('Terminal pose restoration and input readiness are compiled', all(s in bundle for s in (
            'restored terminal death pose', 'presentationPending', 'acceptsInput')))
        check('Current UI asset loaders included', all(s in bundle for s in ['recovered/card-frames/cost_normal','card-frames','energy-icon']))
        check('Target arrow renderer included', all(s in bundle for s in ['recovered/target-arrow/','TargetArrowCamera','SourceTargetArrowRibbon']))
        check('Selection renderer included', all(s in bundle for s in ['recovered/card-selection/','OriginalCardSelection','HCZS_SELECTION']))
        selection_root = PROJECT/'assets/resources/recovered/card-selection'
        selection = json.loads((selection_root/'selection.json').read_text('utf8'))
        check('All 48 selection source images match provenance', len(selection['frames']) == 48 and all(
            sha((selection_root/(frame['resource']+'.png')).read_bytes()) == frame['png_sha256']
            for frame in selection['frames']))
        resource_config = json.loads((data_root/'assets/resources/cc.config.json').read_text('utf8'))
        exported_paths = {value[0] for value in resource_config['paths'].values()}
        check('Every selection sprite has an exported resource path', all(
            'recovered/card-selection/'+frame['resource']+'/spriteFrame' in exported_paths
            for frame in selection['frames']) and 'recovered/card-selection/selection' in exported_paths)
        packaged_png_hashes = {entry['sha256'] for entry in entries if entry['member'].endswith('.png')}
        check('All 48 original selection PNG byte streams are packaged', all(
            frame['png_sha256'] in packaged_png_hashes for frame in selection['frames']))
        check('Target arrow shader adaptation is current',
            (PROJECT/'assets/resources/recovered/target-arrow/target-arrow.effect').read_bytes()==
            (ROOT/'tools/templates/cocos-target-arrow.effect').read_bytes())
        verify_end_turn(check,bundle,exported_paths,packaged_png_hashes)
        verify_audio(check,bundle,exported_paths,{entry['sha256'] for entry in entries})
        verify_health(check,bundle,exported_paths,packaged_png_hashes)
        verify_piles(check,bundle,exported_paths,packaged_png_hashes)
        verify_result(check,bundle,exported_paths,packaged_png_hashes,data_root)
        verify_city(check,bundle,exported_paths,packaged_png_hashes,data_root)
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['error'] = str(error)
    (EVIDENCE/'content-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:report.get(k) for k in ('passed','apk_sha256','error')}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', choices=('device', 'emulator'), default='device')
    main(parser.parse_args().variant)
