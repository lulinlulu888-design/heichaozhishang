"""Pin scene file-service identities and export their path-processing boundary.

Offline bytes/LLVM only. RTTI candidates are not observed runtime instances.
"""
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from trace_native_target_arrow import SOURCE, EXPECTED, OBJDUMP

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/scene-inventory'


def main():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Native image changed')
    def u32(off): return struct.unpack_from('<I', raw, off)[0]
    def string(off): return raw[off:].split(b'\0', 1)[0].decode('ascii')
    services = []
    for name, adr, offset, literal, add, destination in [
        ('IAsyncLoader_1.2', 0x7c9406, 0x7c9510, 0x7c9524, 0x7c9412, 0x3034954),
        ('IResFileSystem_1.3', 0x7c9420, 0x7c9538, 0x7c954c, 0x7c9434, 0x303495c),
    ]:
        if string(offset) != name or (u32(literal) + add + 4) & 0xffffffff != destination:
            raise ValueError('Service registration changed')
        instruction = struct.unpack_from('<H', raw, adr)[0]
        if instruction & 0xff00 != 0xa100 or ((adr + 4) & ~3) + (instruction & 255) * 4 != offset:
            raise ValueError('Service ADR mismatch')
        services.append(dict(name=name, nameOffset=hex(offset), requestAdr=hex(adr),
                             storeDestination=hex(destination)))
    if string(0x7adc54) != 'IFileSystem_1.8':
        raise ValueError('Underlying file interface changed')
    candidates = []
    for name, name_offset, typeinfo, vtable, slot, function in [
        ('N4neox4game13ResFileSystemE', 0x2653140, 0x29733dc, 0x2973384, 0x38, 0x7ae76d),
        ('N4neox4game10FileSystemE', 0x2653230, 0x29736bc, 0x2973664, 0, 0x7b2469),
        ('N4neox10filesystem19NXPackageFileLoaderE', 0x27022e0, 0x29c893c, 0x29c88e4, 0x10, 0x10ce275),
    ]:
        # These addresses are in the pinned data PT_LOAD, whose VA is file + 0x1000.
        if (string(name_offset) != name or u32(typeinfo - 0x1000 + 4) != name_offset
                or u32(vtable - 0x1000 - 4) != typeinfo
                or u32(vtable - 0x1000 - 8) != 0
                or u32(vtable - 0x1000 + slot) != function):
            raise ValueError('RTTI candidate mismatch')
        candidates.append(dict(name=name, typeinfo=hex(typeinfo), vtable=hex(vtable),
                               slot=hex(slot), function=hex(function)))
    exports = []
    OUT.mkdir(parents=True, exist_ok=True)
    for name, start, end in [
        ('scene-service-registration', 0x7c9404, 0x7c9550),
        ('res-filesystem-dependency', 0x7adb7e, 0x7adc68),
        ('res-filesystem-read-thunk', 0x7ae76c, 0x7ae77a),
        ('filesystem-read', 0x7b2468, 0x7b2688),
        ('filesystem-path-build', 0x10c86bc, 0x10c89f0),
        ('filesystem-path-parts', 0x10c89f0, 0x10c8fa0),
        ('filesystem-loader-dispatch', 0x10c679c, 0x10c6904),
        ('package-loader-read', 0x10ce274, 0x10ce718),
        ('package-loader-mount-lookup', 0x10d06a8, 0x10d0800),
    ]:
        command = [str(OBJDUMP), '-d', '--triple=thumbv7-linux-androideabi',
                   f'--start-address={start:#x}', f'--stop-address={end:#x}', str(SOURCE)]
        content = subprocess.run(command, capture_output=True, check=True).stdout
        path = OUT / (name + '.thumb.txt')
        path.write_bytes(content)
        exports.append(dict(path=str(path.relative_to(ROOT)), command=command,
                            sha256=hashlib.sha256(content).hexdigest()))
    report = dict(evidence='Pinned offline ELF and LLVM; no target execution', nativeSha256=EXPECTED,
        services=services, vtableCandidates=candidates, exports=exports,
        observations=[
            'Scene file singleton is requested as IResFileSystem_1.3 via service registry vtable+0x10.',
            'ResFileSystem setup requests IFileSystem_1.8 and stores it at self+0x108 at 0x7adb8a.',
            'Candidate ResFileSystem slot+0x38 at 0x7ae76c replaces r0 with self+0x108 and tail-calls its vtable+0; r1/r2/r3 are unchanged.',
            'Candidate FileSystem slot+0 at 0x7b2468 copies the incoming path, calls 0x10c86bc at 0x7b24e8, and passes its output+4 to 0x10c679c at 0x7b2510 when output status is nonzero.',
            '0x10c86bc calls 0x10c89f0 for path parts and emits byte 0x5c between components at 0x10c8800. Raw path is therefore processed before the lower read boundary.',
            '0x10c679c traverses loader entries at self+4..self+8 in steps of 8; calls loader vtable+0x10 with path in r2 at 0x10c686a and stops at a non-null result.',
            'Package loader candidate 0x10ce274 starts with empty mount prefix and full remaining path. It looks up the prefix via 0x10d06a8 and calls matched entry+0x14 vtable+8 with the remaining path at 0x10ce38c.',
            'On no successful read, package loader searches byte 0x5c at 0x10ce42c, moves one component into the prefix, keeps the suffix as remaining path and loops at 0x10ce60e within its configured bound.',
        ],
        limitations=[
            'Service names and RTTI do not by themselves prove concrete runtime registry bindings.',
            'Complete path grammar, runtime mount registrations, selected package backend and its vtable+8 remain untraced.',
            'No claim of tutorial resource presence/absence, download behavior, or successful original scene load.',
        ])
    (OUT / 'native-scene-filesystem.json').write_text(json.dumps(report, indent=2), 'utf8')
    print(json.dumps(dict(services=services, candidates=candidates, exports=len(exports))))


if __name__ == '__main__':
    main()
