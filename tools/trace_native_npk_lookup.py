"""Bind scene package read to NpkReader symbols and header-selected name hashing."""
import hashlib
import json
import struct
import subprocess
import zipfile
from pathlib import Path
from extract_texture_samples import APK_SHA256
from trace_native_target_arrow import SOURCE, EXPECTED, OBJDUMP

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/scene-inventory'


def main():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Native image changed')
    def u32(p): return struct.unpack_from('<I', raw, p)[0]
    def symbol(info):
        name, value = struct.unpack_from('<II', raw, 0x1f0 + (info >> 8) * 16)
        start = 0xb5b80 + name
        return raw[start:raw.index(b'\0', start)].decode('ascii'), value
    def arm_imm(w):
        value, shift = w & 255, ((w >> 8) & 15) * 2
        return ((value >> shift) | (value << (32-shift))) & 0xffffffff if shift else value
    relplt = dict(struct.unpack_from('<II', raw, p) for p in range(0x663508, 0x69d178, 8))
    imports = []
    for plt, expected in [
        (0x69ee30, '_ZNK4neox9NpkReader8GetIndexEPKc'),
        (0x69d270, '_ZN4neox15GetStringIDFuncENS_12StringIDTypeE'),
        (0x6a5b08, '_ZN4neox23GetStringIDTypeByHeaderERKNS_10NeoXHeaderE'),
        (0x6a042c, '_ZN4neox9NpkReader4OpenEPNS_2io5InputE'),
        (0x6a5afc, '_ZN4neox9NpkReader6DoOpenEv'),
        (0x69d6f0, 'memcmp'),
    ]:
        a, b, c = struct.unpack_from('<III', raw, plt)
        if a & 0xfffff000 != 0xe28fc000 or b & 0xfffff000 != 0xe28cc000 or c & 0xfffff000 != 0xe5bcf000:
            raise ValueError('PLT instructions changed')
        got = (plt + 8 + arm_imm(a) + arm_imm(b) + (c & 4095)) & 0xffffffff
        info = relplt[got]
        name, value = symbol(info)
        if name != expected or info & 255 != 22:
            raise ValueError('PLT symbol changed')
        imports.append(dict(plt=hex(plt), got=hex(got), symbol=name, value=hex(value)))
    reldyn = dict(struct.unpack_from('<II', raw, p) for p in range(0x4ee5b8, 0x663508, 8))
    hashes = []
    for kind, literal, pc, expected in [
        (0, 0x18eb5bc, 0x18eb5a6, '_ZN4neox14StringIDLegacyEPKc'),
        (1, 0x18eb5c0, 0x18eb5aa, '_ZN4neox14StringIDVS2012EPKc'),
        (2, 0x18eb5c4, 0x18eb5ae, '_ZN4neox15StringIDMurmur3EPKc'),
    ]:
        got = (u32(literal) + pc) & 0xffffffff
        info = reldyn[got]
        name, value = symbol(info)
        if name != expected or info & 255 != 21:
            raise ValueError('Hash callback binding changed')
        hashes.append(dict(kind=kind, got=hex(got), symbol=name, value=hex(value)))
    marker_address = (u32(0x138db04) + 0x138dafa) & 0xffffffff
    marker = raw[marker_address:marker_address+12]
    if marker != struct.pack('<3I', 0, 0, 1):
        raise ValueError('Legacy header marker changed')
    if u32(0x29c8758-0x1000+8) != 0x10cc849:
        raise ValueError('NXNpk read slot changed')
    if (u32(0x16c55a4) + 0x16c55a8) & 0xffffffff != 0x6a5afc:
        raise ValueError('Open interworking veneer changed')
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    headers = []
    with zipfile.ZipFile(apk) as archive:
        for item in archive.infolist():
            if not item.filename.endswith('.npk'):
                continue
            with archive.open(item) as stream:
                header = stream.read(24)
            if len(header) != 24 or header[:4] != b'NXPK':
                raise ValueError('NPK header invalid')
            headers.append(dict(member=item.filename, headerHex=header.hex(),
                                selectedHashKind=0 if header[8:20] == marker else 2))
    exports = []
    OUT.mkdir(parents=True, exist_ok=True)
    for name, start, end in [
        ('npk-package-open', 0x10cc4f0, 0x10cc570),
        ('npk-package-read', 0x10cc848, 0x10cc8be),
        ('npk-reader-get-index', 0x138d730, 0x138d78e),
        ('npk-reader-do-open', 0x138d500, 0x138d6b4),
        ('npk-header-hash-kind', 0x138daec, 0x138db08),
        ('npk-hash-selector', 0x18eb59c, 0x18eb5c8),
    ]:
        command = [str(OBJDUMP), '-d', '--triple=thumbv7-linux-androideabi',
                   f'--start-address={start:#x}', f'--stop-address={end:#x}', str(SOURCE)]
        content = subprocess.run(command, capture_output=True, check=True).stdout
        target = OUT / (name + '.thumb.txt')
        target.write_bytes(content)
        exports.append(dict(path=str(target.relative_to(ROOT)), sha256=hashlib.sha256(content).hexdigest(), command=command))
    report = dict(evidence='Static hash-pinned ELF and APK headers; no target execution',
        nativeSha256=EXPECTED, apkSha256=APK_SHA256, imports=imports, hashCallbacks=hashes,
        headerMarker=dict(address=hex(marker_address), bytes=marker.hex()), headers=headers, exports=exports,
        observations=[
            'NXNpk candidate vtable 0x29c8758 slot+8 targets 0x10cc848, which passes remaining path bytes to NpkReader::GetIndex via PLT 0x69ee30.',
            'GetIndex invokes callback at self+0x28 with path pointer, then lower-bound searches 28-byte records and returns only on equal name hash.',
            'DoOpen selects callback from header+8 length 12 and stores it at self+0x28 at 0x138d540.',
            'Header bytes 000000000000000001000000 select kind0/StringIDLegacy; other bytes select kind2/StringIDMurmur3.',
        ], limitations=[
            'No original runtime mount bindings, external patches or whole-engine alternate loading routes verified.',
            'No path suffix alias found in these read/GetIndex functions; this is not proof against aliases in untraced callers.',
            'Static name-hash lookup cannot establish complete scene dependency availability.',
        ])
    (OUT / 'native-npk-lookup.json').write_text(json.dumps(report, indent=2), 'utf8')
    print(json.dumps(dict(packCount=len(headers), legacyCount=sum(x['selectedHashKind']==0 for x in headers),
                          imports=imports, hashCallbacks=hashes)))


if __name__ == '__main__':
    main()
