"""Read the observed NXPK variant, without loading or executing game code.

Writes only beneath analysis/assets. Offsets refer to uncompressed APK members.
The two 32-bit digest fields are deliberately unnamed: their algorithm is unknown.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, re, struct, zipfile, zlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis'/'assets'
APK=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'

class Marshal2:
    """Bounded Python 2 marshal data parser; never constructs executable code."""
    def __init__(self,data): self.data=data;self.pos=0;self.refs=[]
    def take(self,n):
        if n<0 or self.pos+n>len(self.data):raise ValueError('marshal bounds')
        b=self.data[self.pos:self.pos+n];self.pos+=n;return b
    def i(self):return struct.unpack('<i',self.take(4))[0]
    def obj(self,depth=0):
        if depth>100:raise ValueError('marshal depth')
        tag=self.take(1)
        if tag in (b'N',b'0'):return None
        if tag==b'T':return True
        if tag==b'F':return False
        if tag in (b'.',b'S'):return {'type':tag.decode()}
        if tag==b'i':return self.i()
        if tag==b'I':return struct.unpack('<q',self.take(8))[0]
        if tag==b'g':return struct.unpack('<d',self.take(8))[0]
        if tag==b'f':return float(self.take(self.take(1)[0]))
        if tag==b'y':return {'type':'complex','real':struct.unpack('<d',self.take(8))[0],'imag':struct.unpack('<d',self.take(8))[0]}
        if tag==b'x':return {'type':'complex','real':float(self.take(self.take(1)[0])),'imag':float(self.take(self.take(1)[0]))}
        if tag==b'l':
            n=self.i();v=0
            if abs(n)>10000:raise ValueError('marshal long bounds')
            for j in range(abs(n)):v|=struct.unpack('<H',self.take(2))[0]<<(15*j)
            return v if n>=0 else -v
        if tag in (b's',b't',b'u'):
            b=self.take(self.i())
            if tag==b'u':return b.decode('utf-8')
            if tag==b't':self.refs.append(b)
            return b
        if tag==b'R':
            ix=self.i()
            if ix<0 or ix>=len(self.refs):raise ValueError('marshal reference bounds')
            return self.refs[ix]
        if tag in (b'(',b'[',b'<',b'>'):
            n=self.i()
            if n<0 or n>1000000:raise ValueError('marshal collection bounds')
            return [self.obj(depth+1) for _ in range(n)]
        if tag==b'{':
            a=[]
            while True:
                if self.data[self.pos:self.pos+1]==b'0':self.pos+=1;break
                a.append([self.obj(depth+1),self.obj(depth+1)])
            return {'type':'dict','items':a}
        if tag==b'c':
            d={'type':'code'}
            for k in ('argcount','nlocals','stacksize','flags'):d[k]=self.i()
            for k in ('bytecode','consts','names','varnames','freevars','cellvars','filename','name'):d[k]=self.obj(depth+1)
            d['firstlineno']=self.i();d['lnotab']=self.obj(depth+1)
            return d
        raise ValueError(f'unknown marshal tag {tag!r} at {self.pos-1}')

def jsonable(v):
    if isinstance(v,bytes):
        try:
            s=v.decode('utf-8')
            if all(ord(c)>=32 or c in '\r\n\t' for c in s):return s
        except UnicodeDecodeError:pass
        return {'bytes_hex':v.hex()}
    if isinstance(v,list):return [jsonable(x) for x in v]
    if isinstance(v,dict):return {k:jsonable(x) for k,x in v.items()}
    return v

def code_symbols(obj):
    names=set();functions=[];strings=set()
    def walk(v):
        if isinstance(v,bytes):
            if len(v)>512:return
            try:s=v.decode('utf-8')
            except UnicodeDecodeError:return
            if s and all(ord(c)>=32 or c in '\r\n\t' for c in s):strings.add(s)
        elif isinstance(v,list):
            for x in v:walk(x)
        elif isinstance(v,dict):
            if v.get('type')=='code':
                functions.append(v.get('name',b'').decode('utf-8','replace'))
                for n in v.get('names',[]):
                    if isinstance(n,bytes):names.add(n.decode('utf-8','replace'))
            for k,x in v.items():
                if k not in ('bytecode','lnotab'):walk(x)
    walk(obj)
    return dict(functions=functions,names=sorted(names),strings=sorted(strings))

def parse_npk(data):
    if len(data)<24:raise ValueError('short NPK')
    magic,count,reserved1,reserved2,version,index_offset=struct.unpack_from('<4s5I',data)
    if magic!=b'NXPK':raise ValueError('not observed NXPK magic')
    if index_offset<24 or count>1000000 or index_offset+count*28!=len(data):raise ValueError('invalid index bounds')
    entries=[]
    keys=('name_hash','offset','stored_size','original_size','digest1','digest2','compression','encryption')
    for i in range(count):
        v=struct.unpack_from('<6I2H',data,index_offset+28*i);r=dict(zip(keys,v));r['index']=i
        if r['offset']<24 or r['offset']+r['stored_size']>index_offset:raise ValueError(f'entry {i} bounds')
        entries.append(r)
    return dict(magic='NXPK',count=count,reserved1=reserved1,reserved2=reserved2,version=version,index_offset=index_offset,sha256=hashlib.sha256(data).hexdigest(),size=len(data)),entries

def decode_entry(data,r,max_decoded_bytes=256*1024*1024):
    if not 0<=r['original_size']<=max_decoded_bytes:raise ValueError('decoded size exceeds configured maximum')
    b=data[r['offset']:r['offset']+r['stored_size']]
    if r['encryption']!=0:raise ValueError('unsupported NPK encryption')
    if r['compression']==1:
        dec=zlib.decompressobj();b=dec.decompress(b,r['original_size']+1)
        if not dec.eof or dec.unconsumed_tail or dec.unused_data:raise ValueError('zlib incomplete/overflow/trailing data')
    elif r['compression']!=0:raise ValueError('unsupported NPK compression')
    if len(b)!=r['original_size']:raise ValueError('decoded size mismatch')
    return b

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--member',action='append',default=[]);ap.add_argument('--write-payloads',action='store_true');ap.add_argument('--decode-scripts',action='store_true');ap.add_argument('--max-decoded-bytes',type=int,default=256*1024*1024);ap.add_argument('--json-pattern',default=r'(?i)(login|protocol|rpc|serverlist|server_list|netclient|network|launcher|patch|update|redirect|main\.py|init\.py)');args=ap.parse_args()
    for member in args.member or ['assets/script.npk','assets/assets.npk']:
        if member not in ('assets/script.npk','assets/assets.npk') and not (member.startswith('assets/res/') and member.endswith('.npk')):raise ValueError('member outside NPK allowlist')
        with zipfile.ZipFile(APK) as z:data=z.read(member)
        header,entries=parse_npk(data);dest=OUT/('decoded' if args.decode_scripts else 'npk')/pathlib.PurePosixPath(member).stem;dest.mkdir(parents=True,exist_ok=True)
        header['apk_member']=member;summary=collections.Counter();plain=[];symbols=[]
        for r in entries:
            try:
                b=decode_entry(data,r,args.max_decoded_bytes);r['payload_sha256']=hashlib.sha256(b).hexdigest();r['prefix_hex']=b[:16].hex()
                if args.decode_scripts and member=='assets/script.npk' and b[:2]==b'$\xb9':
                    from neox_rotor import decrypt,KEY
                    rotor_output=decrypt(b,KEY);dec=zlib.decompressobj();s=dec.decompress(rotor_output,64*1024*1024)
                    if not dec.eof or dec.unconsumed_tail or dec.unused_data:raise ValueError('script decompression bounds/trailing data')
                    b=(bytes(x^154 for x in s[:128])+s[128:])[::-1]
                    r['decoded_sha256']=hashlib.sha256(b).hexdigest();r['decoded_size']=len(b)
                r['kind']='opaque'
                if b.startswith(b'c'):
                    try:
                        m=Marshal2(b);obj=m.obj()
                        if m.pos!=len(b):raise ValueError('trailing marshal data')
                        r['kind']='python2_marshal';r['filename']=obj.get('filename',b'').decode('utf-8','replace');r['code_name']=obj.get('name',b'').decode('utf-8','replace')
                        if not args.decode_scripts or re.search(args.json_pattern,r['filename']):
                            (dest/f'{r["index"]:05d}_{r["name_hash"]:08x}.marshal.json').write_text(json.dumps(jsonable(obj),ensure_ascii=False,indent=2),encoding='utf-8')
                        if args.decode_scripts:symbols.append(dict(index=r['index'],filename=r['filename'],**code_symbols(obj)))
                        if not args.decode_scripts:plain.append(r)
                    except (ValueError,IndexError,KeyError) as e:r['marshal_error']=str(e)
                elif b.lstrip().startswith(b'<'):r['kind']='xml'
                elif b.lstrip().startswith((b'{',b'[')):
                    try:json.loads(b);r['kind']='json'
                    except (ValueError,UnicodeDecodeError):pass
                elif b[:2]==b'$\xb9':r['kind']='opaque_24b9'
                if args.write_payloads or r['kind']!='opaque_24b9':
                    suffix={'xml':'xml','json':'json','python2_marshal':'marshal'}.get(r['kind'],'bin')
                    f=dest/f'{r["index"]:05d}_{r["name_hash"]:08x}.{suffix}';f.write_bytes(b);r['output']=str(f.relative_to(ROOT))
                summary[r['kind']]+=1
            except (ValueError,zlib.error) as e:r['error']=str(e);summary['error']+=1
            if args.decode_scripts and r['index']%1000==0:print(f'{member}: {r["index"]}/{len(entries)}',flush=True)
        header['kinds']=dict(summary);header['plain_python_entries']=plain
        (dest/'index.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
        (dest/'summary.json').write_text(json.dumps(header,ensure_ascii=False,indent=2),encoding='utf-8')
        if args.decode_scripts:
            with (dest/'symbols.jsonl').open('w',encoding='utf-8') as f:
                for r in symbols:f.write(json.dumps(r,ensure_ascii=False)+'\n')
        print(json.dumps(header,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
