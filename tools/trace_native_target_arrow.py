"""Preserve hash-bound offline Thumb evidence for the APK targeting arrow."""
import hashlib
import json
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'analysis/bootstrap/extracted/lib/armeabi-v7a/libclient.so'
EXPECTED = '54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef'
OBJDUMP = Path('D:/Android/Sdk/ndk/27.0.12077973/toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-objdump.exe')
OUT = ROOT/'analysis/battle-ui'


def main():
    data = SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Native source identity mismatch')
    # Thumb ADD register,PC at b45428 reads PC=b4542c.
    error_address = 0xb4542c + struct.unpack_from('<I', data, 0xb45720)[0]
    error = data[error_address:data.index(b'\0', error_address)].decode('ascii')
    if error != 'self == NULL in pycocos_cocos2dx_DrawNode_drawArrow':
        raise ValueError('Arrow wrapper anchor mismatch')
    ranges = [('draw-arrow-wrapper', 0xb45388, 0xb45728),
              ('draw-arrow-native', 0xc93d28, 0xc940d4),
              ('draw-arrow-geometry', 0xc93740, 0xc93d28),
              ('draw-arrow-vertices', 0xc9343c, 0xc936c8),
              ('draw-arrow-normalize', 0xd0a250, 0xd0a2cc)]
    exports = []
    for name, start, end in ranges:
        command = [str(OBJDUMP), '-d', '--triple=thumbv7-linux-androideabi',
                   f'--start-address={start:#x}', f'--stop-address={end:#x}', str(SOURCE)]
        result = subprocess.run(command, check=True, capture_output=True)
        path = OUT/(name+'.thumb.txt')
        path.write_bytes(result.stdout)
        exports.append(dict(path=str(path), start=hex(start), end_exclusive=hex(end),
                            sha256=hashlib.sha256(result.stdout).hexdigest(), command=command))
    # The verified ELF's .rel.plt/.dynsym/.dynstr; fixed offsets are guarded by source hash.
    imports = []
    for plt, displacement in [(0x69e758, 0x1ac), (0x69e0f8, 0x5ec), (0x69e008, 0x68c), (0x69dffc, 0x694)]:
        if struct.unpack_from('<III', data, plt) != (0xe28fc623, 0xe28ccaf3, 0xe5bcf000 | displacement):
            raise ValueError('PLT instruction sequence mismatch')
        got = plt + 8 + 36700160 + 995328 + displacement
        relocations = [struct.unpack_from('<II', data, p) for p in range(0x663508, 0x69d178, 8)]
        matches = [info for address, info in relocations if address == got]
        if len(matches) != 1:
            raise ValueError('PLT relocation ambiguity')
        info = matches[0]
        symbol_offset = struct.unpack_from('<I', data, 0x1f0 + (info >> 8)*16)[0] + 0xb5b80
        symbol = data[symbol_offset:data.index(b'\0', symbol_offset)].decode('ascii')
        imports.append(dict(plt=hex(plt), got=hex(got), symbol=symbol, relocation_type=info & 255))
    if [r['symbol'] for r in imports] != ['atan2', 'atan2f', 'sinf', 'cosf']:
        raise ValueError('Unexpected angle imports')
    report = dict(source=str(SOURCE), sha256=EXPECTED,
        evidence_kind='Local offline LLVM disassembly; no target execution or REA runtime observation',
        tool_sha256=hashlib.sha256(OBJDUMP.read_bytes()).hexdigest(), exports=exports,
        anchor=dict(instruction='0xb45428', literal='0xb45720', address=hex(error_address), text=error),
        angle_imports=imports,
        observations=[
            'Wrapper at b4554c calls c93d28 after converting two Vec2, two integers, two strings, integer and string.',
            'c93dca..c93e0a halves argument 3 with signed integer truncation, then offsets start X in both directions.',
            'c93e32..c93ec6 halves argument 4 and offsets target along a trigonometric direction.',
            'c93ed4..c93ef4 calls c93740 twice, passing argument 7 as sample count, float 4 and integer 0.',
            'c93740 allocates N Vec2 samples, computes endpoint distance and normalized direction; sample loop starts at 1 and ends at N.',
            'c938a8 computes horizontal endpoint difference divided by supplied float 4.',
            'c93964..c9398c adds perpendicular displacement h - 4*h*(distanceFromStart-L/2)^2/L^2.',
            'c93f22..c93f3a interleaves the two sampled sides.',
            'c93a30 computes two tangent angles with h=(end.x-start.x)/4 and slope=4*h/L-8*h*s/L^2.',
            'c93c62 calls atan2(slope,1); c93c72 calls atan2f(direction.y,direction.x); their degree values are added.',
            'The angle loop evaluates i=1..N+1. Output pointer 1 gets i=N; output pointer 2 gets i=N+1.',
            'c93daa passes N=20; output 1 at sp+4c orients the end width, output 2 at sp+48 is negated for the head virtual call.',
            'c93496..c93502 sets paired UVs (0,j/(V-1)),(1,j/(V-1)) for j=0..V/2-1 and V=2*N.',
        ],
        interpretation=dict(argument_3='start width (script 160)', argument_4='end width (script 20)',
            argument_7='samples per side (script 60)',
            curve='Parabolic perpendicular displacement; not a guessed cubic Bezier.'),
        constants=dict(degrees_divisor=struct.unpack_from('<f',data,0xc940cc)[0],
                       radians_multiplier=struct.unpack_from('<f',data,0xc940d0)[0]),
        limitations=['Nearest objdump symbol headings are unrelated stripped-code labels, not recovered function names.',
            'Head virtual call identity and rendering still require verification; negation and argument storage are observed.',
            'Mathematical interpretation has not been compared with execution of the original client.'])
    (OUT/'native-target-arrow-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(anchor=error, exports=len(exports), evidence=str(OUT/'native-target-arrow-evidence.json'))))


if __name__ == '__main__':
    main()
