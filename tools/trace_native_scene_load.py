"""Resolve scene.load registration and RTTI candidates from a pinned native image."""
import hashlib,json,struct,subprocess
from pathlib import Path
from trace_native_target_arrow import SOURCE,EXPECTED,OBJDUMP
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-visual/scene-inventory'

def main():
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:raise ValueError('Native image changed')
    bindings=[]
    for label,literal,add,expected in [
        ('methods',0x71dac4,0x71de00,0x30ee228),
        ('function',0x71dacc,0x71de26,0x9e8c3d),
        ('name',0x71dad0,0x71de2c,0x249bef9),
        ('doc',0x71dad4,0x71de30,0x2ac31c4)]:
        value=(struct.unpack_from('<I',raw,literal)[0]+add+4)&0xffffffff
        if value!=expected:raise ValueError('Registration literal changed')
        bindings.append(dict(field=label,literal=hex(literal),addPc=hex(add),value=hex(value)))
    if raw[0x249bef9:0x249befe]!=b'load\0':raise ValueError('Name mismatch')
    init=struct.unpack_from('<921I',raw,0x2a86a4c)
    if 0x71d971 not in init:raise ValueError('Initializer not in init_array')
    ph=struct.unpack_from('<I',raw,28)[0];stride,count=struct.unpack_from('<HH',raw,42)
    segments=[struct.unpack_from('<8I',raw,ph+i*stride) for i in range(count)]
    segments=[s for s in segments if s[0]==1]
    def va(off):return next((s[2]+off-s[1] for s in segments if s[1]<=off<s[1]+s[4]),None)
    def refs(value):
        p=0
        while True:
            p=raw.find(struct.pack('<I',value),p)
            if p<0:return
            if p%4==0:yield p
            p+=1
    name=raw.index(b'N4neox5world5SceneE\0')
    candidates=[]
    for ref in refs(va(name)):
        ti=ref-4
        for slot in refs(va(ti)):
            if struct.unpack_from('<i',raw,slot-4)[0]!=0:continue
            pointers=struct.unpack_from('<12I',raw,slot+4)
            if not all(any(s[6]&1 and s[2]<=(p&~1)<s[2]+s[4] for s in segments) for p in pointers):continue
            candidates.append(dict(typeinfo=hex(va(ti)),vtable=hex(va(slot+4)),
                functions=[dict(slot=hex(i*4),pointer=hex(p)) for i,p in enumerate(pointers)]))
    ranges=[('scene-method-initializer',0x71ddf6,0x71de80),('scene-type-register',0x9ec154,0x9ec2ac),
            ('scene-load-wrapper',0x9e8c3c,0x9e8c68),('scene-load-dispatch',0x9e2c30,0x9e2ff8),
            ('scene-load-string-slot24',0x7e56d4,0x7e5800),
            ('scene-load-string-slot2c',0x7f2228,0x7f2368),
            ('scene-load-file-boundary',0x8379d0,0x8383d4)]
    def file_offset(address):
        return next(s[1]+address-s[2] for s in segments if s[2]<=address<s[2]+s[4])
    boundary=[]
    for label,literal,add,expected_address,expected_pointer in [
        ('slot24 singleton',0x7e57d4,0x7e56ee,0x2a88bdc,0x3034954),
        ('slot2c file singleton',0x838304,0x837a0c,0x2a88c60,0x303495c)]:
        address=(struct.unpack_from('<I',raw,literal)[0]+add+4)&0xffffffff
        pointer=struct.unpack_from('<I',raw,file_offset(address))[0]
        if (address,pointer)!=(expected_address,expected_pointer):
            raise ValueError('Scene resource boundary changed')
        rels=[hex(p) for p in range(0x4ee5b8,0x4ee5b8+0x174f50,8)
              if struct.unpack_from('<II',raw,p)==(address,0x17)]
        if len(rels)!=1:raise ValueError('Expected one R_ARM_RELATIVE relocation')
        boundary.append(dict(label=label,literal=hex(literal),addPc=hex(add),
            got=hex(address),pointer=hex(pointer),relocations=rels))
    strings=[]
    for literal,add,expected_text in [(0x838308,0x837a84,b'SceneHeader'),
                                     (0x8383cc,0x837abe,b'Unable to open file %s')]:
        address=(struct.unpack_from('<I',raw,literal)[0]+add+4)&0xffffffff
        actual=raw[file_offset(address):].split(b'\0',1)[0]
        if actual!=expected_text:raise ValueError('Scene loader string mismatch')
        strings.append(dict(literal=hex(literal),addPc=hex(add),address=hex(address),text=actual.decode()))
    exports=[]
    OUT.mkdir(parents=True,exist_ok=True)
    for name,start,end in ranges:
        cmd=[str(OBJDUMP),'-d','--triple=thumbv7-linux-androideabi',f'--start-address={start:#x}',f'--stop-address={end:#x}',str(SOURCE)]
        content=subprocess.run(cmd,check=True,capture_output=True).stdout
        path=OUT/(name+'.thumb.txt');path.write_bytes(content)
        exports.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(content).hexdigest(),command=cmd))
    report=dict(evidence='Pinned offline ELF bytes and LLVM disassembly, no target execution',nativeSha256=EXPECTED,
        initializer='0x71d970',bindings=bindings,exports=exports,sceneVtableCandidates=candidates,
        resourceBoundaries=boundary,loaderStrings=strings,
        observations=['Initializer stores load name/function/doc into method record at 0x30ee228.',
            'Registered wrapper at 0x9e8c3c dispatches valid self+0x10 to 0x9e2c30.',
            'String branch at 0x9e2e78 calls 0x11df27c then forwards returned pointer to vtable+0x24 or +0x2c.',
            'Non-string shared-object branch uses vtable+0x28.',
            'RTTI candidate slot+0x24 (0x7e56d4) forwards input path as r2 to singleton vtable+0x40 at 0x7e5702; successful handle goes to scene vtable+0x28.',
            'RTTI candidate slot+0x2c (0x7f2228) forwards unchanged input path in r1 to 0x8379d0 at 0x7f2270.',
            '0x8379d0 preserves path in r5, forwards it in r1 to file singleton vtable+0x38 at 0x837a18; later checks SceneHeader and logs Unable to open file %s on failure.'],
        limitations=['Inner singleton implementations and path processing remain to be followed.',
            'No inference that slot+0x2c is asynchronous solely from its object allocation.',
            'RTTI table identity does not establish every active runtime object type.',
            'No scene-loading success or resource absence proven.'])
    (OUT/'native-scene-load.json').write_text(json.dumps(report,indent=2),'utf8')
    print(json.dumps(dict(bindings=bindings,candidates=candidates)))

if __name__=='__main__':main()
