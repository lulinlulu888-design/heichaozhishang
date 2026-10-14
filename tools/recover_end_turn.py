"""Recover original EndArea animation tracks, sprites and particle configuration evidence."""
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
from inspect_selection_timeline import read_timeline
from inspect_battle_ui_layout import Reader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui/end-turn'


def main():
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:raise ValueError('APK changed')
    OUT.mkdir(parents=True,exist_ok=True)
    catalogue=read_catalogue(apk)
    plist_path=OUT/'FightPanel.plist'
    plist_source=extract(apk,catalogue,'uires/FightPanel.plist',plist_path,APK_SHA256)
    texture_path=OUT/'FightPanel.ktx'
    texture_source=extract(apk,catalogue,'uires/FightPanel.pkm',texture_path,APK_SHA256)
    decoded=convert([texture_path],OUT/'decoded',DEFAULT_DECODER)
    record=decoded['textures'][0]['outputs'][0]
    atlas=Image.open(ROOT/record['png']).convert('RGBA')
    plist=plistlib.loads(plist_path.read_bytes())
    if atlas.size!=tuple(map(int,re.findall(r'\d+',plist['metadata']['size']))):raise ValueError('Atlas size mismatch')
    source_path=ROOT/'analysis/battle-ui/EndArea.csb'
    source=json.loads((ROOT/'analysis/battle-ui/EndArea.source.json').read_text('utf8'))
    data=source_path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=source['sha256']:raise ValueError('Source CSB changed')
    timeline=read_timeline(data)
    reader=Reader(data); root=reader.scalar('I',0)
    hierarchy=reader.node(reader.pointer(reader.field(root,3)))
    nodes=[]
    def walk(node):
        nodes.append(node)
        for child in node['children']:walk(child)
    walk(hierarchy)
    node_tags={n['action_tag'] for n in nodes}
    if any(t['action_tag'] not in node_tags for t in timeline['timelines']):raise ValueError('Unbound track')
    resources=[f['value'] for t in timeline['timelines'] for f in t['frames'] if f['kind']=='texture']
    resources += [n['resource'] for n in nodes if n.get('resource') and n['resource']['plist']=='FightPanel.plist']
    if any(r['plist']!='FightPanel.plist' for r in resources):raise ValueError('Unexpected frame atlas')
    keys=sorted({r['path'] for r in resources})
    timeline_path=OUT/'timeline.json'
    timeline_path.write_text(json.dumps(dict(source=source,hierarchy=hierarchy,**timeline),indent=2),'utf8')
    particles=[]
    for n in nodes:
        if n['classname']!='Particle':continue
        logical='uires/'+n['resource']['path']
        path=OUT/(n['name']+'.plist')
        origin=extract(apk,catalogue,logical,path,APK_SHA256)
        config=plistlib.loads(path.read_bytes())
        particles.append(dict(node=n['name'],source=origin,keys=sorted(config),
            texture_file=config.get('textureFileName'),embedded_texture=bool(config.get('textureImageData'))))
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
    # Extraction diagnostic only; original tint/blend is intentionally not applied.
    from PIL import ImageDraw
    columns=8; cell=180
    sheet=Image.new('RGBA',(columns*cell,((len(rows)+columns-1)//columns)*cell),(24,28,35,255))
    draw=ImageDraw.Draw(sheet)
    for i,row in enumerate(rows):
        with Image.open(OUT/row['name']) as sprite:
            sprite.thumbnail((170,150))
            x=(i%columns)*cell; y=(i//columns)*cell
            sheet.alpha_composite(sprite,(x+(cell-sprite.width)//2,y))
            draw.text((x+3,y+154),row['name'],fill='white')
    sheet.save(OUT/'contact-sheet.png')
    report=dict(apk_sha256=APK_SHA256,plist_source=plist_source,texture_source=texture_source,decoded=record,
        layout_source=source,particles=particles,
        animations=timeline['animations'],timeline_count=len(timeline['timelines']),
        timeline_sha256=hashlib.sha256(timeline_path.read_bytes()).hexdigest(),frames=rows,
        attribution='Exact source plist path and verified png-to-pkm loader suffix mapping',
        limitations=['Original tint, blend state and animation timing not applied','No playable client changes or original runtime comparison'])
    (OUT/'provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(frames=len(rows),atlas_size=atlas.size,texture_sha256=texture_source['sha256'])))


if __name__=='__main__':main()
