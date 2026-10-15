"""Check the model-variant Windows build against current export bytes; no execution."""
import hashlib
import json
import struct
from pathlib import Path
from verify_end_turn_content import verify_end_turn
from verify_audio_content import verify_audio
from verify_health_content import verify_health
from verify_pile_content import verify_piles
from verify_result_content import verify_result
from verify_city_content import verify_city

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT/'legacy/cocos-poc'
EVIDENCE = ROOT/'analysis/cocos-native-model'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    report = dict(scope='Static Windows export and executable resource verification only',runtime_verified=False,checks=[])
    def check(name, condition):
        report['checks'].append(dict(name=name,passed=bool(condition)))
        if not condition:
            raise ValueError(name)
    try:
        fingerprints=json.loads((EVIDENCE/'export-source-fingerprints.json').read_text('utf-8-sig'))
        check('Export inputs match current source', bool(fingerprints) and all(digest(Path(r['Path']))==r['Hash'].lower() for r in fingerprints))
        for stage,expected in [('generate-windows','36'),('configure-windows','0'),('compile-windows','36')]:
            check(stage+' succeeded',(EVIDENCE/(stage+'.exit-code.txt')).read_text('utf-8-sig').strip()==expected)
        build=PROJECT/'build/windows-model'
        exe=build/'proj/Debug/hczs-cocos-poc.exe'
        data=exe.read_bytes()
        check('Executable has x64 PE header',data[:2]==b'MZ' and data[struct.unpack_from('<I',data,60)[0]:][:6]==b'PE\0\0\x64\x86')
        report['executable']=dict(path=str(exe),bytes=len(data),sha256=digest(exe))
        source=build/'data'
        resource=exe.parent/'Resources'
        files=sorted(p for p in source.rglob('*') if p.is_file())
        rows=[]
        for path in files:
            relative=path.relative_to(source)
            target=resource/relative
            if not target.is_file() or digest(path)!=digest(target):
                raise ValueError('Executable resources differ: '+str(relative))
            rows.append(dict(path=relative.as_posix(),bytes=path.stat().st_size,sha256=digest(path)))
        check('All exported data matches executable Resources',bool(rows))
        report['resources']=rows
        bundle=(resource/'assets/main/index.js').read_text('utf8')
        check('Terminal pose restoration and input readiness are compiled', all(s in bundle for s in (
            'restored terminal death pose', 'presentationPending', 'acceptsInput')))
        check('Current card font and energy loaders included',all(s in bundle for s in ('recovered/card-frames/cost_normal','energy-icon','card-frames')))
        check('Target arrow renderer included',all(s in bundle for s in ('recovered/target-arrow/','TargetArrowCamera','SourceTargetArrowRibbon')))
        check('Selection renderer included',all(s in bundle for s in ('recovered/card-selection/','OriginalCardSelection','HCZS_SELECTION')))
        selection_root=PROJECT/'assets/resources/recovered/card-selection'
        selection=json.loads((selection_root/'selection.json').read_text('utf8'))
        check('48 selection source images match provenance',len(selection['frames'])==48 and all(
            digest(selection_root/(frame['resource']+'.png'))==frame['png_sha256'] for frame in selection['frames']))
        config=json.loads((resource/'assets/resources/cc.config.json').read_text('utf8'))
        paths={value[0] for value in config['paths'].values()}
        check('Selection sprite resource paths included',all(
            'recovered/card-selection/'+frame['resource']+'/spriteFrame' in paths for frame in selection['frames'])
            and 'recovered/card-selection/selection' in paths)
        png_hashes={row['sha256'] for row in rows if row['path'].endswith('.png')}
        check('48 selection PNG byte streams present in Resources',all(frame['png_sha256'] in png_hashes for frame in selection['frames']))
        check('Arrow source templates are current', all(
            (PROJECT/f'assets/{name}.ts').read_bytes()==(ROOT/f'tools/templates/{template}.ts').read_bytes()
            for name,template in [('TargetArrowView','cocos-target-arrow-view'),('TargetArrowGeometry','cocos-target-arrow-geometry'),
                                  ('PrologueSceneView','cocos-prologue-scene-view'),
                                  ('TutorialBattleView','cocos-tutorial-battle-view'),('CardSelectionView','cocos-card-selection-view'),
                ('EndTurnView','cocos-end-turn-view'),('EnemyTurnPresentation','cocos-enemy-turn-presentation')]))
        check('Arrow shader template is current',
            (PROJECT/'assets/resources/recovered/target-arrow/target-arrow.effect').read_bytes()==
            (ROOT/'tools/templates/cocos-target-arrow.effect').read_bytes())
        verify_end_turn(check,bundle,paths,png_hashes)
        verify_audio(check,bundle,paths,{row['sha256'] for row in rows})
        verify_health(check,bundle,paths,png_hashes)
        verify_piles(check,bundle,paths,png_hashes)
        verify_result(check,bundle,paths,png_hashes,resource)
        verify_city(check,bundle,paths,png_hashes,resource)
        report['passed']=True
    except Exception as error:
        report.update(passed=False,error=str(error))
    (EVIDENCE/'content-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(passed=report['passed'],files=len(report.get('resources',[])),error=report.get('error'))))
    if not report['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
