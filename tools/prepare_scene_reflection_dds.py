"""Pack decoded original cube faces/mips as linear DDS without resampling.

This is a transport conversion. It does not establish cube basis, original
runtime probe selection, or NeoX/UE BRDF equivalence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from PIL import Image
from extract_texture_samples import APK_SHA256

ROOT = Path(__file__).resolve().parents[1]


def pack_cube(levels):
    """DDS DX10 RGBA8: face-major complete authored mip chains, +X..-Z."""
    if not levels or len(levels[0]) != 6:
        raise ValueError('Expected six cube faces')
    size = levels[0][0].width
    if size < 1 or size & (size - 1) or len(levels) != size.bit_length():
        raise ValueError('Expected square power-of-two cube and complete mip chain')
    for mip, faces in enumerate(levels):
        expected = max(1, size >> mip)
        if len(faces) != 6 or any(im.size != (expected, expected) or im.mode != 'RGBA' for im in faces):
            raise ValueError('Cube face dimensions, mode or mip count differ')
    # DDSD_CAPS|HEIGHT|WIDTH|PITCH|PIXELFORMAT|MIPMAPCOUNT, DDSCAPS_COMPLEX|
    # TEXTURE|MIPMAP; DDSCAPS2_CUBEMAP plus all six faces. DXGI 28 is linear.
    header = struct.pack('<7I', 124, 0x2100F, size, size, size * 4, 0, len(levels))
    header += bytes(44)
    header += struct.pack('<8I', 32, 4, int.from_bytes(b'DX10', 'little'), 0, 0, 0, 0, 0)
    header += struct.pack('<5I', 0x401008, 0xFE00, 0, 0, 0)
    dx10 = struct.pack('<5I', 28, 3, 4, 1, 0)  # RGBA8, 2D, texture cube, one cube.
    return b'DDS ' + header + dx10 + b''.join(levels[m][f].tobytes() for f in range(6) for m in range(len(levels)))


def prepare(scene):
    if not scene or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in scene):
        raise ValueError('Expected scene basename')
    folder = ROOT / 'analysis/battle-visual/reflection' / scene
    metadata = folder / 'reflection.json'
    report = json.loads(metadata.read_text('utf8'))
    if report['source']['apk_sha256'] != APK_SHA256:
        raise ValueError('Reflection provenance belongs to a different APK')
    original = Path(report['source']['sample_path'])
    if not original.resolve().is_relative_to((ROOT / 'analysis').resolve()) or hashlib.sha256(original.read_bytes()).hexdigest() != report['source']['sha256']:
        raise ValueError('Original extracted reflection bytes changed')
    texture = report['texture']
    if texture['profile'] != 'linear' or texture['faces'] != 6 or texture['generate_mipmaps']:
        raise ValueError('Unsupported authored cube profile')
    levels, images = [], []
    for mip, level in enumerate(report['levels']):
        outputs = level['textures'][0]['outputs']
        if len(outputs) != 6:
            raise ValueError('Incomplete decoded cube')
        faces = []
        for face, output in enumerate(outputs):
            if output['mip'] != mip or output['face'] != face:
                raise ValueError('Decoded cube mip/face order differs')
            path = (ROOT / output['png']).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValueError('Decoded cube face is outside its source folder')
            raw = path.read_bytes()
            # Re-run the decoder before preparing DDS if decoded data changed.
            if hashlib.sha256(raw).hexdigest() != output['png_sha256']:
                raise ValueError('Decoded face hash changed')
            with Image.open(path) as im:
                if im.size != (max(1, texture['width'] >> mip), max(1, texture['height'] >> mip)):
                    raise ValueError('Decoded dimensions differ from source texture')
                faces.append(im.convert('RGBA'))
            images.append(dict(mip=mip, face=face, png=str(path), sha256=output['png_sha256']))
        levels.append(faces)
    if len(levels) != texture['mip_count']:
        raise ValueError('Authored mip chain incomplete')
    payload = pack_cube(levels)
    target = folder / 'reflectionprobe_0.dds'
    target.write_bytes(payload)
    result = dict(apkSha256=APK_SHA256, sourceCubeSha256=report['source']['sha256'],
        sourceMetadataSha256=hashlib.sha256(metadata.read_bytes()).hexdigest(),
        dds=str(target), ddsSha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload),
        size=texture['width'], mipCount=len(levels), faces=6, dxgiFormat='R8G8B8A8_UNORM',
        decodedInputs=images, faceOrder=['+X','-X','+Y','-Y','+Z','-Z'],
        colorSpaceConversion=False, resampled=False, orientationRemapped=False,
        appliedInUE=False, limitation='Transport only. Engine cube basis, mip retention on import, probe selection and shader combination require native verification.')
    (folder / 'dds.json').write_text(json.dumps(result, indent=2), 'utf8')
    print(json.dumps({key: result[key] for key in ('dds','bytes','mipCount','ddsSha256')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene')
    prepare(parser.parse_args().scene)
