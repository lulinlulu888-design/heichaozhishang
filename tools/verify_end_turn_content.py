"""Source-bound EndArea assets shared by native package verifiers."""
import base64,hashlib,json,plistlib,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def verify_end_turn(check,bundle,paths,png_hashes):
    source=ROOT/'analysis/battle-ui/end-turn'
    staged=ROOT/'clients/cocos-poc/assets/resources/recovered/end-turn'
    report=json.loads((source/'provenance.json').read_text('utf8'))
    manifest=json.loads((staged/'end-turn.json').read_text('utf8'))
    sha=lambda b:hashlib.sha256(b).hexdigest()
    check('EndArea renderer and sequential enemy actions included',all(s in bundle for s in
        ['recovered/end-turn/','OriginalEndArea','HCZS_END_AREA','HCZS_ACTION_QUEUE']))
    check('EndArea timeline matches extracted source',all(manifest[k]==json.loads((source/'timeline.json').read_text('utf8'))[k]
        for k in ['hierarchy','animations','timelines','speed','duration']))
    check('All 41 EndArea source sprites are unchanged and packaged',len(report['frames'])==41 and all(
        sha((staged/f['name']).read_bytes())==f['png_sha256'] and f['png_sha256'] in png_hashes
        for f in report['frames']))
    check('EndArea sprite and manifest paths exported',all('recovered/end-turn/'+f['resource']+'/spriteFrame' in paths
        for f in manifest['frames']) and 'recovered/end-turn/end-turn' in paths)
    for row in report['particles']:
        name=row['node'];original=(source/(name+'.plist')).read_bytes()
        check(name+' source identity',sha(original)==row['source']['sha256'])
        config=plistlib.loads(original);png=zlib.decompress(base64.b64decode(config.pop('textureImageData')))
        config.pop('textureFileName',None)
        check(name+' parameter and lossless PNG adaptation',plistlib.loads((staged/(name+'.plist')).read_bytes())==config
            and (staged/(name+'.png')).read_bytes()==png)
        check(name+' resources exported and PNG packaged',sha(png) in png_hashes
            and 'recovered/end-turn/'+name in paths and 'recovered/end-turn/'+name+'/spriteFrame' in paths)
