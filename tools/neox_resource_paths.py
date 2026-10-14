"""Resolve NeoX NPK names from static libclient.so evidence; never execute game code.

StringIDLegacy is transcribed from ARM Thumb 0x18eaf6e..0x18eb180 in the
provided APK's libclient.so (SHA256 recorded in docs/resource-path-mapping.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path

MASK32 = 0xffffffff


def string_id_legacy(data: bytes) -> int:
    """Exact C-string variant: case and separators are significant; stop at NUL."""
    if not isinstance(data, bytes):
        raise TypeError('StringIDLegacy accepts bytes')
    data = data.split(b'\0', 1)[0]
    a, b, c = 0x37a8470e, 0x7758b42b, 0xf4fa8928
    words = [int.from_bytes(data[p:p+4], 'little') for p in range(0, len(data), 4)]
    for word in words + [0x9be74448, 0x66f42c48]:
        c = ((c << 1) | (c >> 31)) & MASK32
        t = c ^ 0x267b0b11
        a ^= word
        b ^= word
        ma = (((b + t) & MASK32) & 0xbdeb77de) | 0x02040801
        mb = (((a + t) & MASK32) & 0x7d7ebbde) | 0x00804021
        pa, pb = ma * a, mb * b
        lo, hi = pa & MASK32, pa >> 32
        folded = lo + hi + int(hi != 0)
        a = ((folded & MASK32) + (folded >> 32)) & MASK32
        lo, hi = pb & MASK32, pb >> 32
        folded = lo + ((hi << 1) & MASK32)
        b = ((folded & MASK32) + 2 * (folded >> 32)) & MASK32
    return a ^ b


def resource_hash(path: str) -> int:
    """Canonical pack paths use backslashes, with original case retained.

    This does not guess extensions, lowercase paths, or strip directories.
    NUL is rejected here even though the native raw C-string hash stops at NUL.
    """
    if not isinstance(path, str) or not path or '\0' in path:
        raise ValueError('expected nonempty resource path without NUL')
    return string_id_legacy(path.replace('/', '\\').encode('utf-8'))


def script_path(filename: str) -> str:
    """APK-observed importer roots; verified against all 9698 decoded rows."""
    normalized = filename.replace('/', '\\')
    path = normalized
    if not path.endswith('.py'):
        raise ValueError('expected .py code filename')
    path = path[:-3] + '.nxs'
    if path.startswith(('lib\\', 'engine\\')):
        path = path.split('\\', 1)[1]
    if normalized == 'engine\\common\\rpc.py':
        path = 'rpc.nxs'
    return path


def verify_scripts(index_path: Path) -> dict:
    rows = json.loads(index_path.read_text('utf-8'))
    results = []
    for row in rows:
        path = script_path(row['filename'])
        actual = resource_hash(path)
        results.append({'index': row['index'], 'filename': row['filename'],
                        'archive_path': path, 'expected_hash': f'{row["name_hash"]:08x}',
                        'computed_hash': f'{actual:08x}', 'match': actual == row['name_hash']})
    return {'source': str(index_path), 'source_sha256': hashlib.sha256(index_path.read_bytes()).hexdigest(),
            'count': len(results), 'matched': sum(r['match'] for r in results),
            'unique_filenames': len({r['filename'] for r in results}), 'rows': results}


def read_catalogue(apk: Path) -> list[dict]:
    """Read only headers and index tables; no entry payloads are unpacked."""
    keys = ('name_hash','offset','stored_size','original_size','digest1','digest2','compression','encryption')
    result = []
    with zipfile.ZipFile(apk) as z:
        for zi in z.infolist():
            if not zi.filename.endswith('.npk'):
                continue
            with z.open(zi) as f:
                header = f.read(24)
                magic, count, r1, r2, version, offset = struct.unpack('<4s5I', header)
                if magic != b'NXPK' or (r1, r2, version) != (0, 0, 1):
                    raise ValueError(f'unsupported header {zi.filename}')
                if count > 100000 or offset < 24 or offset + count * 28 != zi.file_size:
                    raise ValueError(f'invalid table bounds {zi.filename}')
                f.seek(offset)
                table = f.read(count * 28)
            if len(table) != count * 28:
                raise ValueError('truncated index')
            entries = []
            for index, values in enumerate(struct.iter_unpack('<6I2H', table)):
                row = dict(zip(keys, values))
                if row['offset'] < 24 or row['offset'] + row['stored_size'] > offset:
                    raise ValueError('entry range outside data')
                entries.append({'index': index, **row})
            result.append({'member': zi.filename, 'file_size': zi.file_size,
                           'header_hex': header.hex(), 'index_offset': offset,
                           'index_sha256': hashlib.sha256(table).hexdigest(), 'entries': entries})
    return result


def lookup(catalogue: list[dict], path: str) -> list[dict]:
    value = resource_hash(path)
    return [{'member': pack['member'], **entry} for pack in catalogue for entry in pack['entries']
            if entry['name_hash'] == value]


def lookup_logical(catalogue: list[dict], path: str) -> list[dict]:
    """Resolve root/path inside root.npk. Hashes are relative to mount root."""
    root, relative = path.replace('\\', '/').split('/', 1)
    member = f'assets/res/{root}.npk'
    return [r for r in lookup(catalogue, relative) if r['member'] == member]


def parse_vt_config(data: bytes) -> dict:
    """Data-only version-1 format from helper/cocosvt.py saveConfigJson2BinData."""
    pos = 0
    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError('VT config range out of bounds')
        raw = data[pos:pos+n]
        pos += n
        return raw
    def u32():
        return struct.unpack('<I', take(4))[0]
    def string():
        start = pos
        length = u32()
        if length > 65536 or length % 4:
            raise ValueError('invalid aligned string size')
        raw = take(length)
        value = raw.rstrip(b'\0')
        if b'\0' in value:
            raise ValueError('interior NUL')
        return value.decode('ascii'), start
    if u32() != 1:
        raise ValueError('unsupported VT config version')
    result = {}
    for key in ('plistToPageID', 'pngsToPageID', 'fullPathToPng'):
        count = u32()
        if count > 100000:
            raise ValueError('VT count exceeds budget')
        rows = []
        for i in range(count):
            name, offset = string()
            value = string()[0] if key == 'fullPathToPng' else list(struct.unpack('<4I', take(16)))
            rows.append({'key': name, 'value': value, 'offset': offset})
        if len({r['key'] for r in rows}) != count:
            raise ValueError('duplicate VT keys')
        result[key] = rows
    if pos != len(data):
        raise ValueError('VT trailing bytes')
    return {'version': 1, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*')
    parser.add_argument('--verify-scripts', type=Path)
    parser.add_argument('--apk', type=Path)
    parser.add_argument('--catalogue', type=Path)
    parser.add_argument('--out', type=Path, default=Path('analysis/resource-mapping'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.verify_scripts:
        report = verify_scripts(args.verify_scripts)
        (args.out/'script-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k != 'rows'}))
    catalogue = None
    if args.apk:
        catalogue = read_catalogue(args.apk)
        (args.out/'npk-indices.json').write_text(json.dumps(catalogue, indent=2), encoding='utf-8')
        print('NPK packs:', len(catalogue), 'entries:', sum(len(p['entries']) for p in catalogue))
    elif args.catalogue:
        catalogue = json.loads(args.catalogue.read_text('utf-8'))
    for path in args.paths:
        print(json.dumps({'path': path, 'name_hash': f'{resource_hash(path):08x}',
                          'matches': lookup(catalogue, path) if catalogue else None}, ensure_ascii=False))


if __name__ == '__main__':
    main()
