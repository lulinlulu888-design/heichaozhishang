"""Recover every explicit atlas frame in the parsed hall dependency graph."""
import hashlib
import json
import plistlib
import re
from pathlib import Path
from PIL import Image, ImageDraw
from audit_hall_ui_dependencies import main as audit
from decode_ktx import convert, DEFAULT_DECODER
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]


def crop_frame(image, frame):
    x, y, w, h = map(int, re.findall(r'-?\d+', frame['frame']))
    sx, sy, sw, sh = map(int, re.findall(r'-?\d+', frame['sourceColorRect']))
    size = tuple(map(int, re.findall(r'\d+', frame['sourceSize'])))
    rw, rh = (h, w) if frame['rotated'] else (w, h)
    if not (0 <= x < x+rw <= image.width and 0 <= y < y+rh <= image.height):
        raise ValueError('Frame outside source atlas')
    pixels = image.crop((x, y, x+rw, y+rh))
    if frame['rotated']:
        pixels = pixels.transpose(Image.Transpose.ROTATE_90)
    if pixels.size != (sw, sh) or not (0 <= sx <= sx+sw <= size[0] and 0 <= sy <= sy+sh <= size[1]):
        raise ValueError('Inconsistent trim rectangle')
    canvas = Image.new('RGBA', size)
    canvas.paste(pixels, (sx, sy))
    return canvas


def main():
    audit()  # Revalidates APK and all parsed layout/atlas source bytes.
    base = ROOT/'analysis/hall/ui-dependencies'
    evidence = base/'report.json'
    report = json.loads(evidence.read_text('utf8'))
    out = ROOT/'analysis/hall/ui-sprites'
    out.mkdir(parents=True, exist_ok=True)
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    catalogue = read_catalogue(apk)
    sources, frames, fonts = [], [], []
    for logical in sorted({r['lookup_path'] for r in report['resources']
                           if r['field']=='font_resource' and r['kind']=='file'}):
        target=out/(hashlib.sha256(logical.encode()).hexdigest()[:24]+'.ttf')
        source=extract(apk,catalogue,logical,target,APK_SHA256)
        payload=target.read_bytes()
        if len(payload)<12 or payload[:4] not in (b'\0\1\0\0',b'OTTO'):
            raise ValueError('Unsupported source font container')
        count=int.from_bytes(payload[4:6],'big')
        if not 0<count<=256 or 12+count*16>len(payload):raise ValueError('Invalid font directory')
        for offset in range(12,12+count*16,16):
            start=int.from_bytes(payload[offset+8:offset+12],'big')
            size=int.from_bytes(payload[offset+12:offset+16],'big')
            if start+size>len(payload):raise ValueError('Font table out of bounds')
        fonts.append(dict(logical_path=logical,source=source,path=str(target.relative_to(ROOT)),
                          sha256=hashlib.sha256(payload).hexdigest(),tables=count))
    for logical, record in report['atlases'].items():
        source_file = base/'source'/logical
        if hashlib.sha256(source_file.read_bytes()).hexdigest() != record['source']['sha256']:
            raise ValueError('Atlas changed since audit')
        atlas = plistlib.loads(source_file.read_bytes())
        # Existing native loader analysis established .png -> .pkm substitution.
        texture_logical = record['texture_path'].removesuffix('.png')+'.pkm'
        directory = out/Path(logical).stem
        directory.mkdir(exist_ok=True)
        texture = directory/'atlas.ktx'
        texture_source = extract(apk, catalogue, texture_logical, texture, APK_SHA256)
        decoded = convert([texture], directory/'decoded', DEFAULT_DECODER)
        outputs = decoded['textures'][0]['outputs']
        if len(outputs) != 1:
            raise ValueError('Expected one decoded atlas image')
        image = Image.open(ROOT/outputs[0]['png']).convert('RGBA')
        sources.append(dict(plist=record['source'], texture=texture_source,
                            decoded=outputs[0], dimensions=image.size))
        wanted = sorted({r['reference']['path'] for r in report['resources']
                         if r['lookup_path']==logical and r.get('frame_present')})
        for key in wanted:
            frame = atlas['frames'][key]
            pixels = crop_frame(image, frame)
            name = hashlib.sha256((logical+'\0'+key).encode()).hexdigest()[:24]
            target = directory/(name+'.png')
            pixels.save(target)
            frames.append(dict(plist=logical, source_frame=key, frame=frame,
                png=str(target.relative_to(ROOT)), size=pixels.size,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    result = dict(apk_sha256=APK_SHA256,
        dependency_report_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
        sources=sources, frames=frames, fonts=fonts,
        limitations=['Only explicit frames from successfully parsed layouts',
            'Original pixels decoded and untrimmed; no UI layout/timeline/runtime execution'])
    (out/'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    sheet = Image.new('RGB', (1200, ((len(frames)+5)//6)*140), (38, 42, 50))
    draw = ImageDraw.Draw(sheet)
    for index, frame in enumerate(frames):
        thumb = Image.open(ROOT/frame['png']).convert('RGBA')
        thumb.thumbnail((185, 105))
        x, y = (index % 6)*200, (index//6)*140
        sheet.paste(thumb, (x+(190-thumb.width)//2, y), thumb)
        draw.text((x+4, y+108), f'{index}: '+Path(frame['source_frame']).name[:24], fill='white')
    sheet.save(out/'contact-sheet.png')
    print(json.dumps(dict(atlases=len(sources), unique_frames=len(frames))))


if __name__ == '__main__':
    main()
