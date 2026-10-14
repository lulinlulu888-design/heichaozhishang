"""Hash-bound ModelSkeletal event storage accessors; no target execution."""
import hashlib,json,struct,subprocess
from pathlib import Path
from trace_native_target_arrow import SOURCE,EXPECTED,OBJDUMP
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-visual/enemy-timing'
def main():
    d=SOURCE.read_bytes()
    if hashlib.sha256(d).hexdigest()!=EXPECTED:raise ValueError('Native image changed')
    u=lambda o:struct.unpack_from('<I',d,o)[0]
    ph=u(28);stride,count=struct.unpack_from('<HH',d,42)
    loads=[struct.unpack_from('<8I',d,ph+i*stride) for i in range(count)]
    def offset(va):
        for kind,at,start,_,length,*_ in loads:
            if kind==1 and start<=va<start+length:return at+va-start
        raise ValueError('Unmapped VA')
    def string(va):
        at=offset(va);return d[at:d.index(b'\0',at)].decode('ascii')
    tables=[]
    for va,typename,pointers in [
        (0x2982fe8,'N4neox5world5ModelE',[0x976f6f,0x976f73,0x976f77,0x976f7b]),
        (0x2984194,'N4neox5world13ModelSkeletalE',[0x97ee0f,0x97ee17,0x97ee1f,0x97ee27])]:
        at=offset(va);rtti=u(at-4)
        if u(at-8)!=0 or string(u(offset(rtti)+4))!=typename:raise ValueError('RTTI anchor changed')
        actual=[u(at+k) for k in [0x72c,0x730,0x734,0x738]]
        if actual!=pointers:raise ValueError('Vtable changed')
        tables.append(dict(vtable_va=hex(va),file_offset=hex(at),rtti_va=hex(rtti),type_name=typename,
            slots={hex(k):hex(p) for k,p in zip([0x72c,0x730,0x734,0x738],actual)}))
    if struct.unpack_from('<f',d,offset(0xa4c1b8))[0]!=0:raise ValueError('Time fallback changed')
    exports=[]
    for name,start,end in [('base-event-stubs',0x976f6e,0x976f7e),
        ('skeletal-event-delegates',0x97ee0e,0x97ee2e),
        ('event-storage-accessors',0xa4c078,0xa4c1bc),
        ('event-count-accessor',0x996fe8,0x997020)]:
        command=[str(OBJDUMP),'-d','--triple=thumbv7-linux-androideabi',f'--start-address={start:#x}',f'--stop-address={end:#x}',str(SOURCE)]
        output=subprocess.run(command,check=True,capture_output=True).stdout
        path=OUT/(name+'.thumb.txt');path.write_bytes(output)
        exports.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(output).hexdigest(),command=command))
    report=dict(evidence_kind='Local offline LLVM and ELF/RTTI reads; not REA/runtime observation',
        native_sha256=EXPECTED,tables=tables,exports=exports,time_default_float32=0.0,
        observations=[
            'RTTI identifies the concrete event-query table as neox::world::ModelSkeletal; its RTTI parent is Model.',
            'Four skeletal delegates load object+0x438 and tail-call count/name-index/name/time accessors.',
            'Time accessor 0xa4c160 reads owner at +8, checks vector begin/end at owner+0x948/+0x94c, and uses its first entry.',
            'It checks the requested event index against count, then selects animation from first-entry+0x94, event pointer from animation+8, and reads event+0 as float32.',
            'Empty container or out-of-range event returns float32 0.0; name lookup returns -1 when not found, name-by-index returns null.',
            'Count accessor 0x996fe8 bounds-checks animation ID and calls animation vtable+0x1c, truncating result to unsigned16.',
            'The native time accessor does not multiply by animation duration or convert units; the Python consumer later divides by 1000.'
        ],limitations=[
            'Concrete storage population/loader and event record construction remain unresolved.',
            'No runtime evidence establishes which container or events the cube actually uses.',
            'Zero on missing/out-of-range is not evidence that every valid cube event time is zero.'
        ])
    (OUT/'storage-chain.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(type='neox::world::ModelSkeletal',vtable='0x2984194',default_time=0,exports=len(exports))))
if __name__=='__main__':main()
