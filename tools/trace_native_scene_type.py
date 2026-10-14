"""Preserve pinned ELF world.scene type/loader boundary evidence; no execution."""
import hashlib
import json
import struct
from pathlib import Path
from trace_native_target_arrow import SOURCE, EXPECTED

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/scene-inventory'

def main():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Native source changed')
    phoff = struct.unpack_from('<I',raw,28)[0]
    size,count = struct.unpack_from('<HH',raw,42)
    segments = [struct.unpack_from('<8I',raw,phoff+i*size) for i in range(count)]
    segments = [s for s in segments if s[0]==1]
    def offset(va):
        return next((s[1]+va-s[2] for s in segments if s[2]<=va<s[2]+s[4]),None)
    def string(va):
        start = offset(va)
        if start is None:raise ValueError('String not file-backed')
        return raw[start:raw.index(b'\0',start)].decode('utf8')
    # CPython 2 32-bit PyTypeObject field layout, correlated with name,
    # basicsize, init and adjacent zero fields. Native registration not executed.
    base = 0x2984978
    words = struct.unpack_from('<49I',raw,base)
    if words[3] != 0x24a2a84 or string(words[3]) != 'world.scene' or words[4] != 0x30:
        raise ValueError('Scene type anchor changed')
    methods = words[29]
    if methods != 0x30ee228:raise ValueError('Scene method table pointer changed')
    segment = next(s for s in segments if s[2]<=methods<s[2]+s[5])
    if methods < segment[2]+segment[4]:raise ValueError('Expected zero-filled method table')
    doc_offset = raw.index(b'load(source, args = None, auto_load = FALSE)')
    doc_end = raw.index(b'\0',doc_offset)
    doc = raw[doc_offset:doc_end].decode('utf8')
    if doc_offset != 0x2ac21c4:raise ValueError('Load documentation moved')
    result = dict(nativeSha256=EXPECTED,evidence='Local static ELF bytes; not REA provider analysis or runtime',
        typeCandidate=dict(fileOffset=hex(base),virtualAddress=hex(base+0x1000),name=string(words[3]),
            basicsize=words[4],initThumbPointer=hex(words[37]),
            fields=[dict(byteOffset=hex(i*4),value=hex(v)) for i,v in enumerate(words)]),
        methods=dict(pointer=hex(methods),fileBacked=False,
            loadSegment=dict(fileOffset=hex(segment[1]),virtualAddress=hex(segment[2]),
                fileSize=hex(segment[4]),memorySize=hex(segment[5]))),
        loadDocumentation=dict(fileOffset=hex(doc_offset),sha256=hashlib.sha256(raw[doc_offset:doc_end]).hexdigest(),text=doc),
        conclusions=['Candidate tp_methods points into a PT_LOAD zero-filled tail; no on-disk PyMethodDef array is present at that address.',
            'To resolve load, follow registration/initialization writes or obtain permitted native runtime evidence.',
            'Embedded documentation accepts a string or shared object and returns success/layer_id; it does not establish path remapping.'],
        limitations=['PyTypeObject interpretation is correlated static structure inference.',
            'No concrete load wrapper, native scene parser or path alias branch established.',
            'This result does not prove city_battle_3 missing, nor that native loading succeeds.'])
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'native-scene-type.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(type='world.scene',methods=hex(methods),fileBacked=False,init=hex(words[37]))))

if __name__=='__main__':main()
