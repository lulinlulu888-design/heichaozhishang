"""Preserve the APK's sky-SH loader and RGB coefficient packing instructions."""
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from trace_native_target_arrow import SOURCE, EXPECTED, OBJDUMP

OUT = Path(__file__).resolve().parents[1] / 'analysis/unreal/hall-lighting/environment/native'


def main():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Native image identity changed')
    phoff = struct.unpack_from('<I', raw, 28)[0]
    stride, count = struct.unpack_from('<HH', raw, 42)
    segments = [struct.unpack_from('<8I', raw, phoff + i * stride) for i in range(count)]
    def offset(va):
        return next(s[1] + va - s[2] for s in segments if s[0] == 1 and s[2] <= va < s[2] + s[4])
    def word(va):
        return struct.unpack_from('<I', raw, offset(va))[0]
    anchors = [(0x2975e9c + 0x124, 0x7edde1),
               (0x29822b4 + 0x2c, 0x93fc71),
               (0x29821f4 + 0x30, 0x93f013),
               (0x29821f4 + 0x48, 0x941f6d),
               (0x29821f4 + 0x4c, 0x941fed)]
    if any(word(a) != v for a, v in anchors):
        raise ValueError('Native dispatch anchors changed')
    if raw[offset(0x7eb568):offset(0x7eb568)+9] != b'SkyBoxSH\0':
        raise ValueError('SkyBoxSH string anchor changed')
    OUT.mkdir(parents=True, exist_ok=True)
    ranges = [('sky-sh-loader', 0x7eb208, 0x7eb274),
              ('scene-probe-getter', 0x7edde0, 0x7ede14),
              ('probe-manager-constructor', 0x93fbf4, 0x93fc10),
              ('probe-constructor', 0x93fc70, 0x93fd54),
              ('sky-sh-copy', 0x93f012, 0x93f03c),
              ('pack-complete-sh', 0x941f6c, 0x941fec),
              ('pack-linear-sh', 0x941fec, 0x942042)]
    exports = []
    for name, start, end in ranges:
        cmd = [str(OBJDUMP), '-d', '--triple=thumbv7-linux-androideabi',
               f'--start-address={start:#x}', f'--stop-address={end:#x}', str(SOURCE)]
        data = subprocess.run(cmd, check=True, capture_output=True).stdout
        (OUT / (name + '.thumb.txt')).write_bytes(data)
        exports.append({'name': name, 'start': hex(start), 'end': hex(end),
                        'sha256': hashlib.sha256(data).hexdigest(), 'command': cmd})
    report = {
        'evidenceKind': 'Offline LLVM disassembly, not REA decompilation or runtime observation',
        'nativeSha256': EXPECTED, 'exports': exports,
        'dispatchAnchors': [{'slotAddress': hex(a), 'thumbPointer': hex(v)} for a, v in anchors],
        'observations': [
            '0x7eb242..0x7eb25e reads 27 sequential floats from SkyBoxSH.',
            '0x93f012 copies 0x6c bytes into object+0x10 and marks coefficients dirty.',
            '0x941fec packs each RGB channel as [C3, C1, C2, C0-C6].',
            '0x941f86..0x941fdc packs each quadratic row [C4,C5,3*C6,C7] and final RGB C8.',
            '0x941fe2 sets final alpha to 1. The quadratic block is conditional on a native global.',
        ],
        'limitations': ['Runtime selection, global branch and coefficient preprocessing before pack remain unobserved.',
                        'LLVM nearest exported symbol labels are not function identities.'],
    }
    (OUT / 'trace.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print('Verified native dispatch anchors and exported seven focused instruction ranges.')


if __name__ == '__main__':
    main()
