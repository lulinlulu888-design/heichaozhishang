"""Combine real icon import receipts with the reviewed native hall frame."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(filename):
    return json.loads((ROOT / filename).read_text(encoding='utf8'))

def sha(filename):
    return hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()

def main():
    reports = {
        'hall':'analysis/unreal/hall-ui/ai-icons/ue-family-import-result.json',
        'battle':'analysis/unreal/battle-ui/ai-icons/ue-import-result.json',
        'common':'analysis/assets/ai-icons/common/ue-import-result.json',
        'batch':'analysis/assets/project-icons-ue-result.json',
    }
    loaded = {key:read(filename) for key,filename in reports.items()}
    if not all(report['passed'] for report in loaded.values()):
        raise ValueError('Every batch must have a successful real UE import receipt')
    hall = read('analysis/unreal/hall-ui/ai-icons/ue-family-input-plan.json')
    common = read('analysis/assets/ai-icons/common/manifest.json')
    battle = read('analysis/unreal/battle-ui/ai-icons/provenance.json')
    unique = {row['sourcePNG_SHA256'] for row in hall['selections']}
    unique.update(row['sourcePNG_SHA256'] for row in common['icons'])
    unique.update(row['sourceSha256'] for row in battle['icons'])
    if len(unique) != 21 or len(hall['selections']) != 7 or len(common['icons']) != 10 or len(battle['icons']) != 6:
        raise ValueError('Reviewed group counts differ')
    frame = 'analysis/unreal/hall-ui/ai-icons/hall-icons-final.png'
    log = (ROOT/'runtime/unreal/preview-elsa.log').read_text(encoding='utf8',errors='replace')
    if 'iconVariant=HallLayoutHDAll' not in log or 'hall screenshot saved=true 1600x900' not in log:
        raise ValueError('Latest native frame/runtime identity not found')
    status = {
        'schemaVersion':1, 'evidenceKind':'ordinary-tool-import-readback-and-native-engine-frame',
        'selectedUniqueStaticSourceIcons':21, 'aiVariantVersionFiles':38,
        'ueImportedUniqueSourceIcons':21, 'hallRuntimeRenderedIcons':7,
        'battleImportedIcons':6, 'battleInGameRenderVerified':False,
        'libraryOnlyIcons':8, 'adminVectorSymbolKinds':22,
        'frame':str(ROOT/frame), 'frameSHA256':sha(frame),
        'runtimeLayout':'/Game/Recovered/Hall/UI/AI/UnifiedV4/HallLayoutHDAll',
        'topBarOpticalSizePolicy':{'referenceBBoxArea':1156,'maxDesignEdge':40,
                                 'centre':'source button centre','aspectRatio':'source body preserved'},
        'originalHallLayoutUnchanged':loaded['hall']['originalLayoutUnchanged'],
        'originalHallAssetFileSHA256':loaded['hall']['originalAssetFileSHA256After'],
        'reports':{key:{'path':filename,'sha256':sha(filename)} for key,filename in reports.items()},
        'scopeLimit':'Retained and identified static icon sources; not all 2680 icon/ namespace images or all APK art.',
        'sourceAndGeneratedPixelsModified':False,
        'knownAIDifferences':['Some low alpha scatter remains','Battle active arrow holes simplified to pale fill',
                             'Dance finger/hair detail is AI interpretation'],
    }
    filename = ROOT/'analysis/assets/project-icon-status.json'
    filename.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'passed':True,'report':str(filename),'uniqueUEImportedIcons':21,'nativeHallRenderedIcons':7}))

if __name__ == '__main__':
    main()
