"""Recover embedded FileDescriptorProto data without loading libclient.so.

Schema reference: https://raw.githubusercontent.com/protocolbuffers/protobuf/v3.5.1/src/google/protobuf/descriptor.proto
Only wire schema, message, enum and service declarations are rendered. Raw
descriptors and field-number JSON retain all options and unknown fields.
"""
from pathlib import Path
import hashlib,json,re

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'analysis/bootstrap/extracted/lib/armeabi-v7a/libclient.so'
OUT=ROOT/'analysis/bootstrap/proto'
TYPES={1:'double',2:'float',3:'int64',4:'uint64',5:'int32',6:'fixed64',7:'fixed32',8:'bool',9:'string',10:'group',11:'message',12:'bytes',13:'uint32',14:'enum',15:'sfixed32',16:'sfixed64',17:'sint32',18:'sint64'}
LABELS={1:'optional',2:'required',3:'repeated'}

def varint(b,p):
    v=0
    for i in range(10):
        x=b[p];p+=1;v|=(x&127)<<(7*i)
        if not x&128:return v,p
    raise ValueError('overlong varint')

def wire(b,p=0,stop=False):
    result=[]
    while p<len(b):
        if stop and b[p]==0:break
        start=p;tag,p=varint(b,p);field,kind=tag>>3,tag&7
        if field==0:raise ValueError('field zero')
        if kind==0:v,p=varint(b,p)
        elif kind==2:
            n,p=varint(b,p)
            if p+n>len(b):raise ValueError('length beyond buffer')
            v=b[p:p+n];p+=n
        elif kind in (1,5):
            n=8 if kind==1 else 4;v=b[p:p+n];p+=n
        else:raise ValueError('unsupported wire type')
        result.append((field,kind,v,start))
    return result,p

def fields(b):return wire(b)[0]
def get(rows,n,default=None):return next((v for f,k,v,p in rows if f==n),default)
def many(rows,n):return [v for f,k,v,p in rows if f==n]
def txt(b):return b.decode('utf8')
def decl_enum(b,indent=''):
    rows=fields(b);out=[indent+'enum '+txt(get(rows,1))+' {']
    for item in many(rows,2):
        r=fields(item);n=get(r,2);n=n-(1<<64) if n&(1<<63) else n
        out.append(indent+'  '+txt(get(r,1))+' = '+str(n)+';')
    return out+[indent+'}']

def decl_msg(b,indent=''):
    rows=fields(b);out=[indent+'message '+txt(get(rows,1))+' {']
    for e in many(rows,4):out+=decl_enum(e,indent+'  ')
    for m in many(rows,3):out+=decl_msg(m,indent+'  ')
    for item in many(rows,2):
        r=fields(item);kind=get(r,5);typename=txt(get(r,6)) if get(r,6) else TYPES[kind]
        default=get(r,7);opt=''
        if default is not None:
            value=json.dumps(txt(default),ensure_ascii=False) if kind in (9,12) else txt(default)
            opt=' [default = '+value+']'
        out.append(indent+'  '+LABELS[get(r,4)]+' '+typename+' '+txt(get(r,1))+' = '+str(get(r,3))+opt+';')
    return out+[indent+'}']

def render(rows):
    out=['// Recovered from an embedded FileDescriptorProto; options are preserved in .bin/.json.',
         'syntax = '+json.dumps(txt(get(rows,12,b'proto2')))+';', 'package '+txt(get(rows,2))+';']
    out += ['import '+json.dumps(txt(d))+';' for d in many(rows,3)]
    for e in many(rows,5):out+=['']+decl_enum(e)
    for m in many(rows,4):out+=['']+decl_msg(m)
    for s in many(rows,6):
        r=fields(s);out+=['','service '+txt(get(r,1))+' {']
        for method in many(r,2):
            m=fields(method);out+=['  rpc '+txt(get(m,1))+' ('+txt(get(m,2))+') returns ('+txt(get(m,3))+');']
        out+=['}']
    return '\n'.join(out)+'\n'

def jsonable(rows):
    return [{'field':f,'wire_type':k,'value':v.hex() if isinstance(v,bytes) else v,'offset':p} for f,k,v,p in rows]

def main():
    data=SRC.read_bytes();OUT.mkdir(exist_ok=True);inventory=[]
    for match in re.finditer(rb'\x0a[\x01-\x7f][a-zA-Z_0-9/.]+\.proto\x12',data):
        pos=match.start(); rows,end=wire(data,pos,stop=True)
        name=txt(get(rows,1));package=txt(get(rows,2))
        if not re.fullmatch(r'[a-zA-Z0-9_.]+',package):continue
        raw=data[pos:end];safe=name.replace('/','_');(OUT/(safe+'.bin')).write_bytes(raw)
        record={'source':str(SRC),'source_sha256':hashlib.sha256(data).hexdigest(),
                'offset':pos,'offset_hex':hex(pos),'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'name':name,'package':package,'dependencies':[txt(d) for d in many(rows,3)],
                'messages':[txt(get(fields(m),1)) for m in many(rows,4)],
                'services':[{'name':txt(get(fields(s),1)),'methods':[txt(get(fields(m),1)) for m in many(fields(s),2)]} for s in many(rows,6)],
                'evidence':'Embedded protobuf descriptor parsed statically. No runtime packet observation.',
                'raw_fields':jsonable(rows)}
        (OUT/(safe+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
        try:(OUT/safe).write_text(render(rows),encoding='utf8')
        except (KeyError,TypeError) as exc:record['render_error']=str(exc)
        inventory.append({k:v for k,v in record.items() if k!='raw_fields'})
    (OUT/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(inventory,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
