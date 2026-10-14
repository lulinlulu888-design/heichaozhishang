"""Stage only hash-verified source arrow PNGs and the shared effect adaptation."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'analysis/battle-ui/target-arrow'
destination=ROOT/'clients/cocos-poc/assets/resources/recovered/target-arrow'
manifest=json.loads((source/'manifest.json').read_text('utf8'))
destination.mkdir(parents=True,exist_ok=True)
files=[]
for row in manifest['textures']:
    result=row['outputs'][0]
    path=ROOT/result['png']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=result['png_sha256']:
        raise ValueError('Arrow PNG changed')
    name=Path(row['source']).stem+'.png'
    shutil.copyfile(path,destination/name)
    files.append(dict(name=name,png_sha256=result['png_sha256'],source=row['provenance']))
shutil.copyfile(ROOT/'tools/templates/cocos-target-arrow.effect',destination/'target-arrow.effect')
(destination/'provenance.json').write_text(json.dumps(dict(files=files,
    source_manifest_sha256=hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
    adaptations=['Creator shader syntax and cc_time.x clock; original clock rate not runtime-verified',
        'Offscreen additive composition; orientation and color require runtime comparison']),indent=2),encoding='utf8')
print(json.dumps(dict(staged=len(files),destination=str(destination))))
