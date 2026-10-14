"""Bounded static CSB timeline extraction for the source small-card selection effect."""
import hashlib
import json
import plistlib
from pathlib import Path
from inspect_battle_ui_layout import Reader
from export_elsa_model import extract
from neox_resource_paths import read_catalogue, lookup_logical
from extract_texture_samples import APK_SHA256

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui'


def read_timeline(data):
    r=Reader(data)
    root=r.scalar('I',0)
    def scalar(table,index,fmt='i',default=0):
        field=r.field(table,index)
        return r.scalar(fmt,field) if field else default
    def vector(table,index):
        p=r.pointer(r.field(table,index))
        if not p:return []
        count=r.scalar('I',p)
        if count>10000:raise ValueError('Timeline vector too large')
        return [r.pointer(p+4+i*4) for i in range(count)]
    action=r.pointer(r.field(root,4))
    timelines=[]
    kinds=('point','scale','color','texture','event','int','bool','inner_action','blend')
    for timeline in vector(action,2):
        frames=[]
        for frame in vector(timeline,2):
            variants=[(i,r.pointer(r.field(frame,i))) for i in range(9) if r.field(frame,i)]
            if len(variants)!=1:raise ValueError('Ambiguous frame variant')
            kind,t=variants[0]
            value_field=r.field(t,2)
            if kind in (0,1):value=r.pair(value_field)
            elif kind==2:value=list(r.unpack('BBBB',value_field)) if value_field else None
            elif kind==3:value=r.resource(r.pointer(value_field))
            elif kind==4:value=r.string(value_field)
            elif kind==5:value=scalar(t,2)
            elif kind==6:value=bool(scalar(t,2,'B',1))
            elif kind==8:value=list(r.unpack('ii',value_field)) if value_field else None
            else:raise ValueError('Inner-action frame is not implemented')
            easing=r.pointer(r.field(t,3))
            easing_points=[]
            if easing:
                p=r.pointer(r.field(easing,1))
                if p:
                    count=r.scalar('I',p)
                    if count>1000:raise ValueError('Easing vector too large')
                    easing_points=[r.pair(p+4+i*8) for i in range(count)]
            frames.append(dict(index=scalar(t,0),tween=bool(scalar(t,1,'B',1)),kind=kinds[kind],value=value,
                easing_type=scalar(easing,0,default=-1) if easing else -1,easing_points=easing_points))
        timelines.append(dict(property=r.string(r.field(timeline,0)),action_tag=scalar(timeline,1),frames=frames))
    animations=[dict(name=r.string(r.field(t,0)),start=scalar(t,1),end=scalar(t,2)) for t in vector(root,5)]
    return dict(duration=scalar(action,0),speed=scalar(action,1,'f'),animations=animations,timelines=timelines)


def main():
    links=json.loads((OUT/'layout-links.json').read_text('utf8'))
    source=next(r for r in links['layouts'] if r['name']=='EffectCardSelected_SmallCard')['layout_source']
    data=(OUT/'EffectCardSelected_SmallCard.csb').read_bytes()
    if hashlib.sha256(data).hexdigest()!=source['sha256']:
        raise ValueError('Source layout changed')
    parsed=read_timeline(data)
    timelines=parsed['timelines']
    animations=parsed['animations']
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:raise ValueError('APK identity mismatch')
    catalogue=read_catalogue(apk)
    atlas_path=OUT/'selection-CommonUI.plist'
    atlas_source=extract(apk,catalogue,'uires/CommonUI.plist',atlas_path,APK_SHA256)
    atlas=plistlib.loads(atlas_path.read_bytes())
    requested=sorted({f['value']['path'] for t in timelines for f in t['frames'] if f['kind']=='texture'})
    matched={name:atlas['frames'][name] for name in requested if name in atlas['frames']}
    texture_path='uires/'+atlas['metadata']['textureFileName']
    result=dict(source=source,**parsed,
        atlas=dict(source=atlas_source,metadata=atlas['metadata'],frames=matched,
            missing=sorted(set(requested)-set(matched)),texture_path=texture_path,
            direct_matches=lookup_logical(catalogue,texture_path),
            pkm_matches=lookup_logical(catalogue,texture_path.rsplit('.',1)[0]+'.pkm')),
        limitations=['Static schema interpretation, not original playback','Frame index is not a verified wall-clock time',
            'Color bytes are source A,R,G,B order','No native fork extension inference'])
    (OUT/'selection-timeline.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(duration=result['duration'],speed=result['speed'],animations=animations,
        timelines=len(timelines),properties=sorted({t['property'] for t in timelines}),frames=sum(len(t['frames']) for t in timelines))))


if __name__=='__main__':main()
