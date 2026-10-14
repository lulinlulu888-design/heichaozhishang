"""Find source RTTI/vtable candidates for Wwise audio, preserving VA/file mapping."""
import hashlib,json,struct,subprocess
from pathlib import Path
from trace_native_target_arrow import SOURCE,EXPECTED,OBJDUMP
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui/result'
def main():
    data=SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Native input changed')
    off=struct.unpack_from('<I',data,28)[0];stride,count=struct.unpack_from('<HH',data,42)
    seg=[struct.unpack_from('<8I',data,off+i*stride) for i in range(count)]
    seg=[s for s in seg if s[0]==1]
    def va(at):return next((s[2]+at-s[1] for s in seg if s[1]<=at<s[1]+s[4]),None)
    def refs(value):
        needle=struct.pack('<I',value);pos=0
        while True:
            pos=data.find(needle,pos)
            if pos<0:return
            if pos%4==0:yield pos
            pos+=1
    found=[]
    for name in ('N4neox5audio10WwiseAudioE','N4neox5audio15WwiseAudioEventE'):
        at=data.find(name.encode()+b'\0')
        if at<0 or data.find(name.encode()+b'\0',at+1)>=0:raise ValueError('RTTI name not unique')
        for name_ref in refs(va(at)):
            ti=name_ref-4;ti_va=va(ti)
            if ti_va is None:continue
            for ref in refs(ti_va):
                if struct.unpack_from('<i',data,ref-4)[0]!=0:continue
                functions=[]
                for slot in range(24):
                    ptr=struct.unpack_from('<I',data,ref+4+slot*4)[0]
                    if not any(s[6]&1 and s[2]<=(ptr&~1)<s[2]+s[4] for s in seg):break
                    functions.append(dict(slot=hex(slot*4),pointer=hex(ptr)))
                if len(functions)>=12:
                    found.append(dict(type=name,typeinfo_file=hex(ti),typeinfo_va=hex(ti_va),
                        vtable_file=hex(ref+4),vtable_va=hex(va(ref+4)),functions=functions))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'wwise-vtable-candidates.json').write_text(json.dumps(dict(native_sha256=EXPECTED,candidates=found,
        limitations=['RTTI-linked primary vtable candidates only; active singleton concrete type not observed.']),indent=2),'utf8')
    print(json.dumps(found))
if __name__=='__main__':main()
