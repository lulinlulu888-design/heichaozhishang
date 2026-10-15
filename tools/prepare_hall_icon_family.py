"""Merge reviewed icon metadata for one hall family; never edit image pixels."""
import copy
import hashlib
import json
from pathlib import Path

from audit_ai_hall_icons import adaptation, inspect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/unreal/hall-ui/ai-icons'

def main():
    base = json.loads((OUT / 'provenance-unified.json').read_text('utf8'))
    common_path = ROOT / 'analysis/assets/ai-icons/common/provenance.json'
    common = json.loads(common_path.read_text('utf8'))
    manifest = json.loads((common_path.parent / 'manifest.json').read_text('utf8'))
    merged = copy.deepcopy(base)
    merged['scope'] = 'seven reviewed hall display icons; five top-bar optical-size group, chat and harvest keep original footprints'
    merged['commonProvenanceSHA256'] = hashlib.sha256(common_path.read_bytes()).hexdigest()
    for name, label in [('chat', '聊天'), ('harvest', '快速签收')]:
        row = next(r for r in manifest['icons'] if r['name'] == name)
        item = next(r for r in common['icons'] if r['name'] == name)
        selected = next(v for v in item['variants'] if v['selected'])
        source = inspect(ROOT / row['sourcePNG'])
        candidate = inspect(ROOT / row['aiPNG'])
        if source['sha256'] != row['sourcePNG_SHA256'] or candidate['sha256'] != row['aiPNG_SHA256']:
            raise ValueError('Source/selected image identity changed: ' + name)
        merged['icons'].append({
            'name': name, 'label': label,
            'source': {'spriteId': row['sourceSpriteId'], 'png': source['path'],
                       'pngSha256': source['sha256'], 'sourceFrame': row['sourceFrame'],
                       'size': source['size'], 'apkSha256': item['source']['apkSha256'],
                       'provenanceReports': item['source']['provenanceReports']},
            'variants': [{'version': row['aiVersion'], 'path': candidate['path'], 'sha256': candidate['sha256'],
                          'aiGenerated': True, 'prompt': selected['prompt'], 'tool': selected['tool'],
                          'transparentBackgroundRequested': True, 'referencedImagePaths': selected['referencedImages'],
                          'generatedOriginalPath': selected['generatedFile']}],
            'manualReview': row['review'],
        })
    provenance_path = OUT / 'provenance-family.json'
    provenance_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    audits = []
    for item in merged['icons']:
        source = inspect(Path(item['source']['png']))
        variants = []
        for variant in item['variants']:
            candidate = inspect(Path(variant['path']))
            if candidate['sha256'] != variant['sha256']:
                raise ValueError('Variant changed: ' + item['name'])
            variants.append({'version': variant['version'], **candidate, 'adaptation': adaptation(source, candidate)})
        audits.append({'name': item['name'], 'spriteId': item['source']['spriteId'], 'source': source, 'variants': variants})
    report = {'schemaVersion': 1, 'evidenceType': 'ordinary-tools-image-metadata-and-manual-review',
              'provenanceSha256': hashlib.sha256(provenance_path.read_bytes()).hexdigest(),
              'pngMutation': False, 'ueAssetMutation': False, 'icons': audits,
              'limitations': merged['limitations']}
    audit_path = OUT / 'audit-family.json'
    audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'icons': len(audits), 'provenanceSHA256': report['provenanceSha256'],
                      'auditSHA256': hashlib.sha256(audit_path.read_bytes()).hexdigest()}))

if __name__ == '__main__':
    main()
