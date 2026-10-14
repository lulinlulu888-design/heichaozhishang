"""Locate audio method-table candidates from a pinned ELF, without target execution."""
import hashlib,json,struct,subprocess
from pathlib import Path
from trace_native_target_arrow import SOURCE,EXPECTED,OBJDUMP
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui/result'
def main():
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:raise ValueError('Native image changed')
    phoff=struct.unpack_from('<I',raw,28)[0];size,count=struct.unpack_from('<HH',raw,42)
    segments=[struct.unpack_from('<8I',raw,phoff+i*size) for i in range(count)]
    segments=[s for s in segments if s[0]==1]
    def file_offset(va):
        return next((s[1]+va-s[2] for s in segments if s[2]<=va<s[2]+s[4]),None)
    def text_at(va):
        at=file_offset(va)
        if at is None:return None
        end=raw.find(b'\0',at,min(len(raw),at+100))
        if end<0:return None
        try:return raw[at:end].decode('ascii')
        except UnicodeDecodeError:return None
    anchors=[];cursor=0
    while True:
        at=raw.find(b'\0load_events\0',cursor)
        if at<0:break
        at+=1;cursor=at+1
        va=next(s[2]+at-s[1] for s in segments if s[1]<=at<s[1]+s[4])
        pointer=struct.pack('<I',va);off=0
        while True:
            off=raw.find(pointer,off)
            if off<0:break
            if off%4==0 and off+16<=len(raw):
                name,fn,flags,doc=struct.unpack_from('<4I',raw,off)
                executable=any(s[6]&1 and s[2]<=fn&~1<s[2]+s[4] for s in segments)
                if executable and flags in (1,3,4,8):
                    entries=[]
                    for pos in range(max(0,off-16*10),min(len(raw)-16,off+16*11),16):
                        n,f,fl,d=struct.unpack_from('<4I',raw,pos)
                        label=text_at(n)
                        if label and fl in (1,3,4,8):entries.append(dict(name=label,table_offset=hex(pos),function=hex(f),flags=fl))
                    anchors.append(dict(table_offset=hex(off),entries=entries))
            off+=1
    alias=[e for a in anchors for e in a['entries'] if e['name']=='set_alias']
    exports=[]
    if len(alias)==1 and alias[0]['function']=='0xec218d':
        if text_at(0xec21ec)!='ss':raise ValueError('Alias argument format changed')
        command=[str(OBJDUMP),'-d','--triple=thumbv7-linux-androideabi','--start-address=0xec218c',
                 '--stop-address=0xec21fc',str(SOURCE)]
        output=subprocess.run(command,check=True,capture_output=True).stdout
        path=OUT/'audio-set-alias.thumb.txt';path.write_bytes(output)
        exports.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(output).hexdigest(),command=command))
    scripts=json.loads((ROOT/'analysis/assets/decoded/script/index.json').read_text('utf8'))
    refs=[]
    for row in scripts:
        content=(ROOT/row['output']).read_bytes()
        expected=row.get('decoded_sha256')
        if expected is None and row.get('kind')=='python2_marshal' and row.get('encryption')==0:
            expected=row['payload_sha256']
        if hashlib.sha256(content).hexdigest()!=expected:raise ValueError('Decoded script changed')
        if b'set_alias' in content:refs.append(dict(index=row['index'],filename=row['filename']))
    report=dict(native_sha256=EXPECTED,evidence_kind='Local ELF method table candidates, not execution',anchors=anchors,
        disassembly=exports,decoded_scripts_scanned=len(scripts),set_alias_literal_references=refs,
        observations=['set_alias wrapper at 0xec218c parses two strings (ss) and calls an indirect method at vtable+0x2c.',
                      'No literal set_alias reference in decoded scripts; dynamic/native callers remain possible.'],
        limitations=['PyMethodDef-shaped entries around load_events; module registration still needs correlation.',
                     'No native alias conversion inferred from table shape.'])
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'native-audio-entry.json').write_text(json.dumps(report,indent=2),'utf8')
    print(json.dumps(dict(anchors=len(anchors),alias_entries=alias,scripts=len(scripts),alias_references=refs)))
if __name__=='__main__':main()
