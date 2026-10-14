"""Stage source EndArea sprites, timeline and embedded particle plists."""
import hashlib,json,shutil,plistlib,base64,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'analysis/battle-ui/end-turn'
DEST=ROOT/'clients/cocos-poc/assets/resources/recovered/end-turn'
def main():
    report=json.loads((SOURCE/'provenance.json').read_text('utf8'))
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(SOURCE/'timeline.json')!=report['timeline_sha256']:raise ValueError('Changed timeline')
    data=json.loads((SOURCE/'timeline.json').read_text('utf8'))
    files=[(r['name'],r['png_sha256']) for r in report['frames']]
    files += [(r['node']+'.plist',r['source']['sha256']) for r in report['particles']]
    for name,sha in files:
        if digest(SOURCE/name)!=sha:raise ValueError('Changed resource: '+name)
    DEST.mkdir(parents=True,exist_ok=True)
    for name,_ in files:shutil.copyfile(SOURCE/name,DEST/name)
    # Creator's embedded-data decoder fails on these source zlib streams.
    # Preserve particle parameters; bind the exact decompressed PNG explicitly.
    for particle in report['particles']:
        name=particle['node']; config=plistlib.loads((SOURCE/(name+'.plist')).read_bytes())
        png=zlib.decompress(base64.b64decode(config.pop('textureImageData')))
        if not png.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Unexpected particle image')
        config.pop('textureFileName',None)
        (DEST/(name+'.png')).write_bytes(png)
        (DEST/(name+'.plist')).write_bytes(plistlib.dumps(config))
    data['frames']=[dict(source_path=r['key'],resource=Path(r['name']).stem) for r in report['frames']]
    data['particles']=[r['node'] for r in report['particles']]
    data['frame_interval']=json.loads((ROOT/'analysis/battle-ui/native-selection-clock.json').read_text())['frame_interval_float32']
    data['limitations']=['Rebuilt renderer; original runtime and loader timing equivalence unverified.', 'Standard Cocos2d-x easing enum mapping; native fork mapping not traced.']
    (DEST/'end-turn.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf8')
    print('Staged',len(files),'source resources')
if __name__=='__main__':main()
