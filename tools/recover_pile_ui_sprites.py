"""Extract exact original card-library frames referenced by the recovered CSBs."""
import hashlib
import json
import plistlib
import re
from pathlib import Path
from PIL import Image
from decode_ktx import convert, DEFAULT_DECODER
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui/piles/sprites'
WANTED={
    'Common/Res/tab_bg.png':'tab-background',
    'Common/Res/common_tab_select1.png':'tab-draw-selected',
    'Common/Res/tab_select2.png':'tab-discard-selected',
    'Common/Res/tab_select3.png':'tab-consumed-selected',
    'dialog/Res/dialog_lv2_cutline_main.png':'tab-divider',
    'paidui/listPaidui/res/img_InfoShow_mask.png':'bottom-mask',
    'paidui/Res/icon_change.png':'change-view-icon',
    'dialog/Res/CommonBtn/dialog_widget_btn_small.png':'change-view-button',
}


def recover(wanted=WANTED, out=OUT, evidence=None):
    # Callers select only frames present in their hash-bound CSB report.
    WANTED, OUT = wanted, out
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:
            raise ValueError('APK identity changed')
    evidence=evidence or ROOT/'analysis/battle-ui/piles/report.json'
    report=json.loads(evidence.read_text('utf8'));bindings={}
    queue=[v['tree'] for v in report['layouts'].values()]
    while queue:
        node=queue.pop();queue.extend(node['children'])
        ref=node.get('resource',{})
        if ref.get('path') in WANTED:
            if ref['path'] in bindings and bindings[ref['path']]!=ref['plist']:
                raise ValueError('ambiguous atlas binding')
            bindings[ref['path']]=ref['plist']
    if set(bindings)!=set(WANTED):
        raise ValueError('expected source UI frame absent')
    OUT.mkdir(parents=True,exist_ok=True)
    catalogue=read_catalogue(apk);atlases={};sources=[];frames=[]
    for plist_name in sorted(set(bindings.values())):
        stem=Path(plist_name).stem
        directory=OUT/stem;directory.mkdir(exist_ok=True)
        plist_path=directory/'atlas.plist';texture=directory/'atlas.ktx'
        plist_source=extract(apk,catalogue,'uires/'+plist_name,plist_path,APK_SHA256)
        texture_source=extract(apk,catalogue,'uires/'+plist_name.removesuffix('.plist')+'.pkm',texture,APK_SHA256)
        decoded=convert([texture],directory/'decoded',DEFAULT_DECODER)
        images=decoded['textures'][0]['outputs']
        if len(images)!=1:
            raise ValueError('expected one atlas image')
        image=Image.open(ROOT/images[0]['png']).convert('RGBA')
        atlas=plistlib.loads(plist_path.read_bytes())
        atlases[plist_name]=(atlas,image)
        sources.append(dict(plist=plist_source,texture=texture_source,decoded=images[0]))
    for key,name in WANTED.items():
        atlas,image=atlases[bindings[key]];frame=atlas['frames'][key]
        x,y,w,h=map(int,re.findall(r'-?\d+',frame['frame']))
        sx,sy,sw,sh=map(int,re.findall(r'-?\d+',frame['sourceColorRect']))
        size=tuple(map(int,re.findall(r'\d+',frame['sourceSize'])))
        rw,rh=(h,w) if frame['rotated'] else (w,h)
        if not(0<=x<x+rw<=image.width and 0<=y<y+rh<=image.height):
            raise ValueError('atlas bounds mismatch')
        pixels=image.crop((x,y,x+rw,y+rh))
        if frame['rotated']:pixels=pixels.transpose(Image.Transpose.ROTATE_90)
        if pixels.size!=(sw,sh) or not(0<=sx<=sx+sw<=size[0] and 0<=sy<=sy+sh<=size[1]):
            raise ValueError('trim bounds mismatch')
        canvas=Image.new('RGBA',size);canvas.paste(pixels,(sx,sy))
        path=OUT/(name+'.png');canvas.save(path)
        frames.append(dict(name=name,source_frame=key,plist=bindings[key],frame=frame,size=size,
                           png=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    result=dict(apk_sha256=APK_SHA256,layout_report_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
                sources=sources,frames=frames,
                limitations=['Original atlas pixels only; no UI runtime/timeline proof.'])
    (OUT/'report.json').write_text(json.dumps(result,indent=2),'utf8')
    print(json.dumps(dict(atlases=len(atlases),frames=[dict(name=r['name'],size=r['size']) for r in frames])))


if __name__=='__main__':recover()
