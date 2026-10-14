"""Render selected recovered marshal objects as evidence, never execute them.

The opcode names below are a PARTIAL map inferred from the redirect importer and
consistent Python 2 code objects. Unknown opcodes are retained numerically.
This is not a full decompiler and is not evidence that branches execute.
"""
from pathlib import Path
import argparse,json,struct
from extract_npk import Marshal2,jsonable

OP={0x99:'LOAD_CONST',0x91:'STORE_NAME',0x86:'IMPORT_NAME',0x65:'LOAD_NAME',0x60:'LOAD_ATTR',
    0x83:'CALL_FUNCTION',0x72:'COMPARE_OP',0x61:'LOAD_FAST',0x68:'STORE_FAST',0x9b:'LOAD_GLOBAL',
    0x9c:'JUMP_FORWARD',0x88:'MAKE_FUNCTION',0x87:'BUILD_TUPLE',0x5a:'BUILD_LIST',
    0x94:'POP_JUMP_IF_FALSE',0x9e:'SETUP_LOOP',0x89:'JUMP_ABSOLUTE',0x48:'POP_BLOCK',
    0x21:'BUILD_CLASS',0x26:'POP_TOP',0x53:'RETURN_VALUE',0x27:'BINARY_ADD',0x46:'BINARY_MULTIPLY',
    0x1e:'BINARY_XOR',0x0a:'BINARY_SUBSCR',0x59:'SLICE_3',0x57:'SLICE_1',0x84:'STORE_ATTR',
    0x35:'PRINT_ITEM',0x2a:'PRINT_NEWLINE'}
NAMES={0x91,0x86,0x65,0x60,0x9b,0x84}

def short(v):
    if isinstance(v,dict) and v.get('type')=='code':return '<code '+repr(v['name'])+'>'
    s=repr(v)
    return s if len(s)<=400 else s[:400]+'...'

def listing(obj,path=''):
    lines=[];name=obj['name'].decode('utf8','replace');path=path+'.'+name
    lines+=['\n### '+path+' at '+str(obj['firstlineno']), 'args/locals: '+repr(obj['varnames']),
            'names: '+repr(obj['names']), 'constants: '+repr([short(x) for x in obj['consts']])]
    code=obj['bytecode'];p=0
    while p<len(code):
        offset=p;op=code[p];p+=1;arg=None;hint=''
        if op>=90:
            if p+2>len(code):break
            arg=struct.unpack_from('<H',code,p)[0];p+=2
            try:
                if op==0x99:hint=short(obj['consts'][arg])
                elif op in NAMES:hint=short(obj['names'][arg])
                elif op in (0x61,0x68):hint=short(obj['varnames'][arg])
            except IndexError:hint='<INDEX OUT OF BOUNDS: map uncertain>'
        lines.append(f'{offset:04x} {op:02x} {OP.get(op,"UNKNOWN"):22} {str(arg) if arg is not None else "":6} {hint}')
    for c in obj['consts']:
        if isinstance(c,dict) and c.get('type')=='code':lines+=listing(c,path)
    return lines

def main():
    ap=argparse.ArgumentParser();ap.add_argument('index',nargs='+',type=int);args=ap.parse_args()
    root=Path(__file__).resolve().parents[1];dest=root/'analysis/bootstrap/scripts';dest.mkdir(exist_ok=True)
    index=json.loads((root/'analysis/assets/decoded/script/index.json').read_text('utf8'))
    for i in args.index:
        row=index[i];src=next((root/'analysis/assets/decoded/script').glob(f'{i:05d}_*.marshal'))
        obj=Marshal2(src.read_bytes()).obj();filename=obj['filename'].decode('utf8','replace').replace('\\','/')
        name=filename.replace('/','__')
        (dest/(name+'.json')).write_text(json.dumps(jsonable(obj),ensure_ascii=False,indent=2),encoding='utf8')
        (dest/(name+'.partial-dis.txt')).write_text('SOURCE '+str(src)+'\nNPK index '+str(i)+'\n'+str(row)+'\n'+'\n'.join(listing(obj)),encoding='utf8')
        print(i,filename)

if __name__=='__main__':main()
