"""Offline bootstrap clues from APK DEX and ELF. Does not execute target code."""
import argparse, hashlib, json, re, struct, zipfile
from pathlib import Path

KEYWORDS = re.compile(r'(?i)(https?://|server.?list|gate.?way|gserver|login|logon|protobuf|msgpack|packmsg|rpc|handshake|patch.?url|update.?url|base.?url|heichao|hczs|projectx|neox|server.?ip|server.?port|serialize|socket|packeter|network)')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def uleb(data, off):
    val = 0
    for i in range(5):
        b = data[off]; off += 1
        val |= (b & 127) << (i * 7)
        if not b & 128:
            return val, off
    raise ValueError('oversized uleb')

def dex_inventory(data):
    if data[:4] != b'dex\n':
        return {'error': 'not standard DEX'}
    n, tab = struct.unpack_from('<II', data, 56)
    strings = []
    for i in range(n):
        pos, = struct.unpack_from('<I', data, tab + i*4)
        length, p = uleb(data, pos)
        end = data.index(0, p)
        strings.append({'index': i, 'offset': pos, 'offset_hex': hex(pos),
                        'utf16_length': length, 'text': data[p:end].decode('utf-8', 'replace')})
    nt, ot = struct.unpack_from('<II', data, 64)
    types = [strings[struct.unpack_from('<I', data, ot+i*4)[0]]['text'] for i in range(nt)]
    nm, om = struct.unpack_from('<II', data, 88)
    methods = []
    for i in range(nm):
        cls, proto, name = struct.unpack_from('<HHI', data, om+i*8)
        cname, mname = types[cls], strings[name]['text']
        if KEYWORDS.search(cname + '.' + mname):
            methods.append({'index': i, 'offset': om+i*8, 'offset_hex': hex(om+i*8),
                            'class': cname, 'name': mname, 'proto_index': proto})
    nc, oc = struct.unpack_from('<II', data, 96)
    classes = []
    for i in range(nc):
        row = struct.unpack_from('<8I', data, oc+i*32)
        classes.append({'index': i, 'offset': oc+i*32, 'class': types[row[0]],
                        'access_flags': row[1], 'class_data_offset': row[6]})
    return {'magic': data[:8].hex(), 'string_count': n, 'method_count': nm,
            'class_count': nc, 'matching_strings': [s for s in strings if KEYWORDS.search(s['text'])],
            'matching_methods': methods, 'classes': classes}

def elf_inventory(data):
    if data[:6] != b'\x7fELF\x01\x01':
        return {'error': 'expected little endian ELF32'}
    vals = struct.unpack_from('<16sHHIIIIIHHHHHH', data, 0)
    shoff, shentsize, shnum, shstrndx = vals[6], vals[11], vals[12], vals[13]
    rawsecs = [struct.unpack_from('<10I', data, shoff+i*shentsize) for i in range(shnum)]
    strsec = rawsecs[shstrndx]
    names = data[strsec[4]:strsec[4]+strsec[5]]
    cstr = lambda s, p: s[p:s.find(b'\0', p)].decode('utf-8', 'replace')
    sections = [{'name': cstr(names, s[0]), 'type':s[1], 'address':s[3], 'offset':s[4],
                 'size':s[5], 'link':s[6], 'entry_size':s[9]} for s in rawsecs]
    symbols = []
    for s in sections:
        if s['type'] not in (2,11) or not s['entry_size']:
            continue
        st = sections[s['link']]; strings = data[st['offset']:st['offset']+st['size']]
        for pos in range(s['offset'], s['offset']+s['size'], s['entry_size']):
            name, value, size, info, other, section = struct.unpack_from('<IIIBBH', data, pos)
            text = cstr(strings, name)
            if KEYWORDS.search(text):
                symbols.append({'symbol_offset':pos, 'symbol_offset_hex':hex(pos), 'name':text,
                                'value':value, 'value_hex':hex(value), 'size':size, 'section_index':section})
    matches=[]
    for m in re.finditer(rb'[\x20-\x7e]{5,}', data):
        text=m.group().decode('ascii')
        if KEYWORDS.search(text):
            matches.append({'offset':m.start(), 'offset_hex':hex(m.start()), 'text':text,
                            'section': next((s['name'] for s in sections if s['offset'] <= m.start() < s['offset']+s['size']),None)})
    return {'machine':vals[2], 'entry':hex(vals[4]), 'sections':sections,
            'matching_symbols':symbols, 'matching_strings':matches}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('apk',type=Path); ap.add_argument('--out',type=Path,default=Path('analysis/bootstrap'))
    args=ap.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    manifest=[]
    with zipfile.ZipFile(args.apk) as z:
        for zi in z.infolist():
            if not (re.fullmatch(r'classes\d*\.dex',zi.filename) or zi.filename=='lib/armeabi-v7a/libclient.so'):
                continue
            data=z.read(zi)
            out=args.out/'extracted'/zi.filename; out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(data)
            result = dex_inventory(data) if zi.filename.endswith('.dex') else elf_inventory(data)
            result.update({'apk':str(args.apk.resolve()), 'member':zi.filename, 'member_sha256':sha(data),
                           'zip_header_offset':zi.header_offset, 'size':len(data),
                           'evidence':'static parsing only; offsets are in decompressed member unless explicitly prefixed zip'})
            result_path=args.out/(Path(zi.filename).name+'.json')
            result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            manifest.append({'member':zi.filename,'sha256':sha(data),'size':len(data),'result':str(result_path),
                             'matching_strings':len(result.get('matching_strings',[])), 'matching_symbols':len(result.get('matching_symbols',[]))})
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__': main()
