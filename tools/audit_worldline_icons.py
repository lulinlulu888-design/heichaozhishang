"""Append metadata-only worldline control-art audit; preserve historical counts.

No APK extraction, PNG decoding/editing, AI generation, UE import or C++ edits.
Compare current page consumers with the previously reviewed 21 icon sources.
"""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
BASELINE=ROOT/'analysis/assets/icon-audit-latest.json'
HISTORY=ROOT/'analysis/assets/icon-audit.json'
CURRENT=ROOT/'analysis/unreal/worldline-ui/icon-inventory.json'
LAYOUT=ROOT/'analysis/unreal/worldline-ui/layout.json'
OUTPUT=ROOT/'analysis/assets/worldline-source-icons-audit.json'
ICON_CATEGORIES={'navigation-icon','ui-symbol-candidate','currency-icon-candidate',
                 'item-icon-candidate','equipment-icon-candidate','skill-buff-icon-candidate',
                 'other-icon-namespace-candidate'}
EXPECTED={
    'a2d0a1bae517808aba3d2034':('back','ui-symbol-candidate'),
    '1a3385b920e937f28cfba72a':('info','ui-symbol-candidate'),
    '8f96dcd8fa42d39c21e9a396':('branch','navigation-control-art'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text('utf8'))


def main():
    history_before=sha(HISTORY)
    baseline_before=sha(BASELINE)
    baseline=read(BASELINE);current=read(CURRENT);layout=read(LAYOUT)
    if sha(LAYOUT)!=current['sourceLayoutSha256']:
        raise ValueError('Worldline icon inventory/layout mismatch')
    originals=[row for row in baseline['recovered_original_images'] if row['classification'] in ICON_CATEGORIES]
    original_hashes={row['encoded_sha256'] for row in originals}
    if len(originals)!=21 or len(original_hashes)!=21:
        raise ValueError('Frozen reviewed 21-icon baseline changed')
    if {row['id'] for row in current['icons']}!=set(EXPECTED):
        raise ValueError('Current worldline control inventory changed')
    consumed={item['spriteId'] for item in layout['page']['items'] if item['kind']=='sprite'}
    if len(layout['page']['items'])!=14 or len(consumed)!=12 or layout['progressBinding']['chapterInstances']!=0:
        raise ValueError('Frozen static source page changed')
    results=[]
    for row in current['icons']:
        path=Path(row['png']).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError('Source icon outside workspace')
        raw=path.read_bytes()
        dimensions=list(struct.unpack_from('>II',raw,16)) if raw[:8]==b'\x89PNG\r\n\x1a\n' and len(raw)>=33 else None
        if sha(path)!=row['pngSha256'] or dimensions!=row['size']:
            raise ValueError('Current source PNG changed: '+row['id'])
        if row['id'] not in consumed:
            raise ValueError('Inventory includes a template-only image')
        hash_matches=[old['logical_path'] for old in originals if old['encoded_sha256']==row['pngSha256']]
        name_matches=[old['logical_path'] for old in originals if old['logical_path'].removeprefix('uires/')==row['sourceFrame']]
        action,category=EXPECTED[row['id']]
        results.append(dict(**row,action=action,classification=category,
            category_reason='Original full branch navigation art with raster title; not a compact glyph' if action=='branch'
                            else 'Original topbar action symbol verified by source consumer',
            baseline21EncodedHashMatches=hash_matches,baseline21LogicalSourceMatches=name_matches,
            sameSourceAsBaseline21=bool(hash_matches or name_matches),currentPageConsumer=True,
            sourcePNGPreserved=True,pixelDecodePerformed=False))
    report_path=ROOT/'analysis/unreal/worldline-ui/import-result.json'
    receipt=read(report_path) if report_path.exists() else None
    imported=bool(receipt and receipt.get('passed') and not receipt.get('validationOnly'))
    frame_path=ROOT/'analysis/unreal/worldline-ui/worldline-native-frame.png'
    paint_path=ROOT/'analysis/unreal/worldline-ui/worldline-native-frame.png.ui.json'
    native_verified=False
    native_evidence=None
    if frame_path.exists() and paint_path.exists():
        paint=read(paint_path)
        raw_frame=frame_path.read_bytes()
        dimensions=list(struct.unpack_from('>II',raw_frame,16)) if raw_frame[:8]==b'\x89PNG\r\n\x1a\n' and len(raw_frame)>=33 else None
        painted=set(paint.get('actualPaintedSprites',[]))
        native_verified=(paint.get('mode')=='original-worldline-static-source-page' and
            paint.get('sourceLayoutSha256')==current['sourceLayoutSha256'] and
            paint.get('visible') is True and paint.get('sourceReady') is True and
            paint.get('readOnlySourceInspection') is True and paint.get('progressAvailable') is False and
            paint.get('chapterInstances')==0 and painted==consumed and set(EXPECTED).issubset(painted) and
            dimensions==[1600,900])
        if not native_verified:
            raise ValueError('Native frame/state does not match the frozen current worldline page')
        native_evidence=dict(frame=frame_path.relative_to(ROOT).as_posix(),frameSHA256=sha(frame_path),
            capture=paint_path.relative_to(ROOT).as_posix(),captureSHA256=sha(paint_path),dimensions=dimensions,
            actualPaintedSprites=paint['actualPaintedSprites'],currentThreeSourceIdsMatched=sorted(EXPECTED),
            sourceLayoutSha256=paint['sourceLayoutSha256'],chapterInstances=0,progressAvailable=False,
            readOnlySourceInspection=True,scope='Native rebuilt UE page paint proof; not original APK runtime compatibility')
        for row in results:
            row['nativeRenderVerified']=row['id'] in painted
    union=original_hashes|{row['pngSha256'] for row in results}
    symbols={row['pngSha256'] for row in results if row['classification']=='ui-symbol-candidate'}
    result=dict(schema='hczs-worldline-source-icons-append-v1',evidenceKind='ordinary metadata/IHDR/file-hash audit',
        frozenHistoricalAuditSHA256=history_before,frozenBaselineAuditSHA256=baseline_before,
        baselineReviewedStaticIconSources=21,baselineAIOriginalIconSources=21,baselineAIVariantFiles=38,
        worldlineCurrentControlArtSources=3,newEncodedSourceHashes=len(union)-len(original_hashes),
        worldlineCompactSymbols=2,worldlineFullNavigationArtwork=1,
        combinedUniqueStaticControlArtSourcePNGs=len(union),
        combinedUniqueCompactIconCandidateSourcePNGs=len(original_hashes|symbols),
        sameSourceOrEncodedHashAsBaseline21=sum(row['sameSourceAsBaseline21'] for row in results),
        newWorldlineAIVariants=0,aiPolicy='Original source comparison first; no AI generated in this audit',
        sourcePageDrawItems=14,sourcePageSprites=12,sourcePageTextItems=2,sourceChapterInstances=0,
        sourceProgressAvailable=False,unusedTemplateTexturesExcludedFromCurrentRuntimeCount=32,
        currentVariant='original-apk',ueImported=imported,
        importReceipt=dict(path=report_path.relative_to(ROOT).as_posix(),sha256=sha(report_path)) if receipt else None,
        nativeRenderVerified=native_verified,nativeRenderEvidence=native_evidence,icons=results,
        inputs={str(path.relative_to(ROOT)).replace('\\','/'):sha(path) for path in (CURRENT,LAYOUT)},
        limitations=['Encoded SHA256 and original logical source identity compared; no perceptual/pixel-equality inference.',
                     '21 AI-selected source icons remain 21; new original worldline sources are a separate batch.',
                     'Full branch navigation artwork is included only in the broader static control-art source count.',
                     'Layout consumption/preparation is not native render or interaction verification.'])
    if history_before!=sha(HISTORY) or baseline_before!=sha(BASELINE):
        raise ValueError('Frozen historical audit changed during read-only scan')
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    ledger_path=ROOT/'analysis/resource-ledger/worldline-icons-increment.json'
    ledger_path.parent.mkdir(parents=True,exist_ok=True)
    ledger=dict(schema='hczs-resource-ledger-worldline-control-art-increment-v1',
        iconAudit=dict(path=OUTPUT.relative_to(ROOT).as_posix(),sha256=sha(OUTPUT)),
        baselineStaticIconSources=21,newCurrentControlArtSourcePNGs=3,combinedUniqueControlArtSourcePNGs=24,
        newCompactSymbolPNGs=2,newFullNavigationArtworkPNGs=1,aiNewVariants=0,
        sourcePageDrawItems=14,sourcePageSprites=12,sourcePageTextItems=2,chapterInstances=0,
        unusedTemplateTexturesExcluded=32,ueImported=imported,nativeRenderVerified=native_verified,
        caveat='Original static page paint only; no original account progress or branch/info gameplay completion',
        historicalResourceLedgerRewritten=False)
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps({key:result[key] for key in ('newEncodedSourceHashes','combinedUniqueStaticControlArtSourcePNGs',
        'combinedUniqueCompactIconCandidateSourcePNGs','newWorldlineAIVariants','ueImported','nativeRenderVerified')},ensure_ascii=False))


if __name__=='__main__':
    main()
