"""Recover original worldline atlas frames, standalone textures and fonts.

Reuses the common NPK and KTX converters.  Untrimmed atlas crops are original
pixels; no AI variant or reconstructed gameplay state is introduced here.
"""
import argparse
import hashlib
import json
import plistlib
from pathlib import Path
from PIL import Image, ImageDraw

from audit_worldline_ui_dependencies import OUT as DEP, digest, main as audit
from decode_ktx import convert, DEFAULT_DECODER
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import lookup_logical, read_catalogue
from recover_hall_ui_sprites import crop_frame

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/worldline/ui-sprites'


def font_record(apk, catalogue, logical):
    target=OUT/'fonts'/(hashlib.sha256(logical.encode()).hexdigest()[:24]+'.ttf')
    target.parent.mkdir(parents=True,exist_ok=True)
    source=extract(apk,catalogue,logical,target,APK_SHA256)
    payload=target.read_bytes()
    if len(payload)<12 or payload[:4] not in (b'\0\1\0\0',b'OTTO'):
        raise ValueError('Unsupported original font container')
    count=int.from_bytes(payload[4:6],'big')
    if not 0<count<=256 or 12+count*16>len(payload):
        raise ValueError('Font directory bounds invalid')
    for offset in range(12,12+count*16,16):
        start=int.from_bytes(payload[offset+8:offset+12],'big')
        size=int.from_bytes(payload[offset+12:offset+16],'big')
        if start+size>len(payload):
            raise ValueError('Font table out of bounds')
    return dict(logical_path=logical,source=source,path=str(target.relative_to(ROOT)),
                sha256=digest(target),tables=count)


def main(revalidate=True):
    if revalidate:
        audit()
    report_path=DEP/'report.json'
    report=json.loads(report_path.read_text('utf8'))
    if report['apk_sha256']!=APK_SHA256:
        raise ValueError('Mixed source APK report')
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if not revalidate and digest(apk)!=APK_SHA256:
        raise ValueError('Unexpected APK bytes')
    catalogue=read_catalogue(apk)
    OUT.mkdir(parents=True,exist_ok=True)
    sources,frames,files,fonts,unresolved=[],[],[],[],[]
    atlases={}
    for logical,record in report['atlases'].items():
        path=DEP/'source'/logical
        if digest(path)!=record['source']['sha256']:
            raise ValueError('Original atlas hash drift')
        atlas=plistlib.loads(path.read_bytes())
        atlases[logical]=atlas
        texture_logical=record['texture_path'].removesuffix('.png')+'.pkm'
        directory=OUT/Path(logical).stem
        directory.mkdir(parents=True,exist_ok=True)
        texture=directory/'atlas.ktx'
        source=extract(apk,catalogue,texture_logical,texture,APK_SHA256)
        decoded=convert([texture],directory/'decoded',DEFAULT_DECODER)
        outputs=decoded['textures'][0]['outputs']
        if len(outputs)!=1:
            raise ValueError('Expected one original atlas image')
        image=Image.open(ROOT/outputs[0]['png']).convert('RGBA')
        sources.append(dict(plist=record['source'],texture=source,decoded=outputs[0],dimensions=image.size))
        wanted={r['reference']['path'] for r in report['resources']
                if r['lookup_path']==logical and r.get('frame_present')}
        # Auto code binds replacements by a frame string + plist; membership in
        # exactly one of the declared original atlases supplies its pixels.
        script_wanted={r['reference']['path'] for r in report['resources']
                       if r['field']=='script-resource-string' and r['reference']['path'].endswith('.png')}
        wanted.update(s for s in script_wanted if s in atlas['frames'])
        for key in sorted(wanted):
            frame=atlas['frames'][key]
            pixels=crop_frame(image,frame)
            name=hashlib.sha256((logical+'\0'+key).encode()).hexdigest()[:24]
            target=directory/(name+'.png')
            pixels.save(target)
            frames.append(dict(plist=logical,source_frame=key,frame=frame,
                png=str(target.relative_to(ROOT)),size=pixels.size,sha256=digest(target),
                authority='decoded-original-atlas-frame'))
    file_refs=sorted({r['lookup_path'] for r in report['resources']
                      if r['kind']=='file' and r['lookup_path'].endswith(('.png','.ttf'))})
    for logical in file_refs:
        if logical.endswith('.ttf'):
            fonts.append(font_record(apk,catalogue,logical))
            continue
        name=logical.removeprefix('uires/')
        memberships=[key for key,atlas in atlases.items() if name in atlas['frames']]
        if memberships:
            if len(memberships)!=1:
                raise ValueError('Ambiguous explicit original script atlas frame: '+name)
            continue
        direct=lookup_logical(catalogue,logical)
        packed=logical.removesuffix('.png')+'.pkm'
        candidates=lookup_logical(catalogue,packed)
        directory=OUT/'standalone'/hashlib.sha256(logical.encode()).hexdigest()[:24]
        directory.mkdir(parents=True,exist_ok=True)
        if len(direct)==1:
            target=directory/'original.png'
            source=extract(apk,catalogue,logical,target,APK_SHA256)
            image=Image.open(target).convert('RGBA')
            # Preserve original file byte identity; no re-encode required.
            png=target
            resolution='direct-original-png'
        elif not direct and len(candidates)==1:
            target=directory/'original.ktx'
            source=extract(apk,catalogue,packed,target,APK_SHA256)
            decoded=convert([target],directory/'decoded',DEFAULT_DECODER)
            outputs=decoded['textures'][0]['outputs']
            if len(outputs)!=1:
                raise ValueError('Expected one standalone original image')
            png=ROOT/outputs[0]['png']
            image=Image.open(png).convert('RGBA')
            resolution='original-loader-png-to-pkm-substitution'
        else:
            unresolved.append(dict(logical_path=logical,pngMatches=len(direct),pkmMatches=len(candidates),
                reason='no-unique-original-pixel; no substitute image'))
            continue
        files.append(dict(logical_path=logical,source=source,png=str(png.relative_to(ROOT)),
                          size=image.size,sha256=digest(png),resolution=resolution))
    result=dict(schemaVersion=1,apk_sha256=APK_SHA256,dependency_report_sha256=digest(report_path),
                sources=sources,frames=frames,files=files,fonts=fonts,unresolved=unresolved,
                evidence_kind='ordinary-tool-original-pixel-decode',
                limitations=['Atlas crops untrim original source dimensions; no source pixel modification',
                  'Standalone .png -> .pkm path resolution follows the separately documented original loader mapping',
                  'No original chapter/account state or timeline execution; frames may represent mutually exclusive runtime states'])
    (OUT/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    images=frames+files
    sheet=Image.new('RGB',(1200,max(1,(len(images)+5)//6)*150),(37,40,49))
    draw=ImageDraw.Draw(sheet)
    for i,row in enumerate(images):
        image=Image.open(ROOT/row['png']).convert('RGBA')
        image.thumbnail((190,112))
        x,y=(i%6)*200,(i//6)*150
        sheet.paste(image,(x+(190-image.width)//2,y),image)
        label=row.get('source_frame') or row['logical_path']
        draw.text((x+3,y+114),str(i)+': '+Path(label).name[:24],fill='white')
        draw.text((x+3,y+130),str(row['size']),fill='white')
    sheet.save(OUT/'contact-sheet.png')
    summary=dict(atlases=len(sources),frames=len(frames),standalone=len(files),fonts=len(fonts),
                 unresolved=unresolved,reportSha256=digest(OUT/'report.json'))
    print(json.dumps(summary,ensure_ascii=False))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing-audit',action='store_true')
    args=parser.parse_args()
    main(not args.existing_audit)
