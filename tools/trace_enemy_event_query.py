"""Trace source event-time cache and native method entries without running the APK."""
import hashlib,json,struct,subprocess
from pathlib import Path
import inspect_battle_rules as static
from trace_native_target_arrow import SOURCE,EXPECTED,OBJDUMP
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-visual/enemy-timing'
def main():
    data=SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Native source changed')
    index=json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    exports=[]
    for number,methods,name in [
        (8905,('getAnimationEventTime',),'component-event-query'),
        (4254,('_initModelInfo','getAnimationEventTimeMilliseconds'),'model-event-cache')]:
        report=static.export(next(r for r in index if r['index']==number),methods)
        if set(methods)!={c['name'] for c in report['code_objects']}:raise ValueError('Missing source method')
        path=OUT/(name+'.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
        exports.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    entries=[]
    for name,offset,expected in [('get_anim_event_count',0x2ab7108,0x9d8655),
        ('get_anim_event_name',0x2ab7118,0x9d86ed),('get_anim_event_time',0x2ab7128,0x9d87a1)]:
        string,pointer,flags,doc=struct.unpack_from('<4I',data,offset)
        # Pinned image's string LOAD segment has identical VA and file offset.
        if data[string:data.index(b'\0',string)].decode()!=name or pointer!=expected or flags!=1:
            raise ValueError('Method table anchor changed')
        entries.append(dict(name=name,table_offset=hex(offset),string_address=hex(string),
            thumb_pointer=hex(pointer),flags=flags))
    for name,start,end in [('event-method-wrappers',0x9d8654,0x9d87cc),('event-time-wrapper-body',0x9d13b0,0x9d14c0)]:
        command=[str(OBJDUMP),'-d','--triple=thumbv7-linux-androideabi',f'--start-address={start:#x}',f'--stop-address={end:#x}',str(SOURCE)]
        output=subprocess.run(command,check=True,capture_output=True).stdout
        path=OUT/(name+'.thumb.txt');path.write_bytes(output)
        exports.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(output).hexdigest(),command=command))
    report=dict(evidence_kind='Hash-bound static Python extraction and local LLVM disassembly; not REA/runtime execution',
        native_source=str(SOURCE),native_sha256=EXPECTED,method_entries=entries,exports=exports,
        observations=[
            'CompAnimation.getAnimationEventTime resolves the real animation name and divides the model cache result by 1000.0.',
            'Model._initModelInfo enumerates RawModel animation names, lengths, event counts, event names and event times; stores dictionary values keyed by animation and event name.',
            'getAnimationEventTimeMilliseconds reads this dictionary and returns None for missing keys.',
            'Native get_anim_event_time method pointer 0x9d87a1 reaches 0x9d13b0 when the wrapper raw-model pointer at +0x18 is nonzero.',
            'The wrapper at 0x9d1470 reads raw-model vtable+0x738; 0x9d147a calls it with animation ID and a 16-bit event index.',
            '0x9d147c..0x9d1488 converts the returned float32 bit pattern to double for the Python result.'
        ],limitations=[
            'Raw-model concrete vtable, event storage implementation and loader source remain unresolved.',
            'No actual cube event count/time was observed; no new hit ratio is established.',
            'The milliseconds interpretation is established by Python consumer naming and conversion, not native implementation units alone.'
        ])
    (OUT/'query-chain.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(methods=len(entries),exports=len(exports),event_time_vtable_slot='0x738',runtime_verified=False)))
if __name__=='__main__':main()
