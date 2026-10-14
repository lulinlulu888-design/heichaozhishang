"""Recover all 48 original selection frames from the path-resolved CommonUI atlas."""
import hashlib
import json
import plistlib
import re
from pathlib import Path
from PIL import Image
from decode_ktx import convert, DEFAULT_DECODER
from export_elsa_model import extract
from neox_resource_paths import read_catalogue
from extract_texture_samples import APK_SHA256

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui/card-selection'


def main():
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:raise ValueError('APK changed')
    OUT.mkdir(parents=True,exist_ok=True)
    catalogue=read_catalogue(apk)
    plist_path=OUT/'CommonUI.plist'
    plist_source=extract(apk,catalogue,'uires/CommonUI.plist',plist_path,APK_SHA256)
    texture_path=OUT/'CommonUI.ktx'
    texture_source=extract(apk,catalogue,'uires/CommonUI.pkm',texture_path,APK_SHA256)
    decoded=convert([texture_path],OUT/'decoded',DEFAULT_DECODER)
    record=decoded['textures'][0]['outputs'][0]
    atlas=Image.open(ROOT/record['png']).convert('RGBA')
    plist=plistlib.loads(plist_path.read_bytes())
    if atlas.size!=tuple(map(int,re.findall(r'\d+',plist['metadata']['size']))):raise ValueError('Atlas size mismatch')
    timeline_path=ROOT/'analysis/battle-ui/selection-timeline.json'
    timeline=json.loads(timeline_path.read_text('utf8'))
    if plist_source['sha256']!=timeline['atlas']['source']['sha256']:raise ValueError('Timeline atlas changed')
    keys=sorted({f['value']['path'] for t in timeline['timelines'] for f in t['frames'] if f['kind']=='texture'})
    if len(keys)!=48:raise ValueError('Unexpected frame inventory')
    rows=[]
    for key in keys:
        frame=plist['frames'][key]
        x,y,w,h=map(int,re.findall(r'-?\d+',frame['frame']))
        sx,sy,sw,sh=map(int,re.findall(r'-?\d+',frame['sourceColorRect']))
        size=tuple(map(int,re.findall(r'\d+',frame['sourceSize'])))
        rw,rh=(h,w) if frame['rotated'] else (w,h)
        if not (0<=x<x+rw<=atlas.width and 0<=y<y+rh<=atlas.height):raise ValueError('Crop outside atlas')
        pixels=atlas.crop((x,y,x+rw,y+rh))
        if frame['rotated']:pixels=pixels.transpose(Image.Transpose.ROTATE_90)
        if pixels.size!=(sw,sh) or not (0<=sx<=sx+sw<=size[0] and 0<=sy<=sy+sh<=size[1]):
            raise ValueError('Invalid trim geometry')
        restored=Image.new('RGBA',size);restored.paste(pixels,(sx,sy))
        name=Path(key).parent.name+'-'+Path(key).name
        path=OUT/name;restored.save(path)
        rows.append(dict(key=key,name=name,frame=frame,size=size,
            png_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),rgba_sha256=hashlib.sha256(restored.tobytes()).hexdigest()))
    # Contact sheet is an extraction diagnostic, not a game screenshot.
    sheet=Image.new('RGBA',(12*190,4*230),(24,28,35,255))
    groups=sorted({Path(row['key']).parent.name for row in rows})
    for row in rows:
        group=Path(row['key']).parent.name
        number=int(Path(row['key']).stem.rsplit('_',1)[1])
        with Image.open(OUT/row['name']) as sprite:
            sheet.alpha_composite(sprite,(number*190+(190-sprite.width)//2,groups.index(group)*230+(230-sprite.height)//2))
    sheet.save(OUT/'contact-sheet.png')
    report=dict(apk_sha256=APK_SHA256,plist_source=plist_source,texture_source=texture_source,decoded=record,
        timeline_sha256=hashlib.sha256(timeline_path.read_bytes()).hexdigest(),frames=rows,
        attribution='Exact source plist path and verified png-to-pkm loader suffix mapping',
        limitations=['Original tint, blend state and animation timing not applied','No playable client changes or original runtime comparison'])
    (OUT/'provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(frames=len(rows),atlas_size=atlas.size,texture_sha256=texture_source['sha256'])))


if __name__=='__main__':main()
