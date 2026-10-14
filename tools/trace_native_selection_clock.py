"""Hash-bound native timing evidence; offline analysis, not original execution."""
import hashlib
import json
import struct
import subprocess
from trace_native_target_arrow import SOURCE, EXPECTED, OBJDUMP, OUT


def main():
    data = SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Native source changed')
    def u32(offset):
        return struct.unpack_from('<I', data, offset)[0]
    def address_to_offset(address):
        ph = u32(28)
        size, count = struct.unpack_from('<HH', data, 42)
        for i in range(count):
            kind, offset, va, _, length, *_ = struct.unpack_from('<8I', data, ph+i*size)
            if kind == 1 and va <= address < va+length:
                return offset+address-va
        raise ValueError('Address outside file-backed LOAD segment')
    anchor = 0xbc250a+u32(0xbc2558)
    text = data[anchor:data.index(b'\0', anchor)].decode('ascii')
    if text != 'self == NULL in pycocos_cocos2dx_studio_ActionTimeline_setTimeSpeed':
        raise ValueError('setTimeSpeed anchor mismatch')
    vtable = 0xe10e52+u32(0xe10ee0)+8
    setter = u32(address_to_offset(vtable+0x5c)) & ~1
    step = u32(address_to_offset(vtable+0x2c)) & ~1
    if (vtable, setter, step) != (0x29b4f94, 0xe12f76, 0xe11858):
        raise ValueError('ActionTimeline vtable changed')
    if data[setter:setter+4] != bytes.fromhex('01657047'):
        raise ValueError('Speed setter does not write object+0x50')
    ranges = [('selection-clock-wrapper',0xbc249c,0xbc2560),
              ('selection-clock-create-wrapper',0xbc2700,0xbc2768),
              ('selection-clock-create',0xe10e10,0xe10ee4),
              ('selection-clock-step',step,0xe119c8),
              ('selection-clock-restart',0xe113ae,0xe11446),
              ('selection-clock-accessors',setter,0xe12f8e)]
    exports = []
    for name, start, end in ranges:
        command = [str(OBJDUMP), '-d', '--triple=thumbv7-linux-androideabi',
                   f'--start-address={start:#x}', f'--stop-address={end:#x}', str(SOURCE)]
        result = subprocess.run(command, check=True, capture_output=True)
        path = OUT/(name+'.thumb.txt')
        path.write_bytes(result.stdout)
        exports.append(dict(path=str(path), start=hex(start), end_exclusive=hex(end),
                            sha256=hashlib.sha256(result.stdout).hexdigest(), command=command))
    interval = struct.unpack('<f', struct.pack('<I',0x3c888889))[0]
    report = dict(source=str(SOURCE), sha256=EXPECTED,
        evidence_kind='Local offline LLVM disassembly; not REA or original runtime observation',
        tool_sha256=hashlib.sha256(OBJDUMP.read_bytes()).hexdigest(), exports=exports,
        anchor=dict(address=hex(anchor), text=text, add_pc='0xbc2506', literal='0xbc2558'),
        vtable=dict(va=hex(vtable), file_offset=hex(address_to_offset(vtable)),
                    speed_setter=hex(setter), step_candidate=hex(step)),
        frame_interval_float32=interval, selected_action_speed=0.5,
        derived_frames_per_second=0.5/interval,
        observations=[
            'create wrapper bc2712 calls e10e10; e10e4e/e10e80/e10e8a install vtable address.',
            'create e10e30/e10e40 assemble float bits 0x3c888889; e10e50 stores them at object+0x54, alongside speed=1 at +0x50.',
            'setTimeSpeed wrapper bc24ec selects vtable+0x5c; e12f76 writes object+0x50.',
            'vtable+0x2c points to e11858; e1187c..e118a2 multiplies input delta by speed and accumulates double time at +0x48.',
            'e1189e loads frame interval from +0x54; e118dc..e118f2 divides accumulated time by it and truncates to frame integer.',
            'e118ae..e118be skips frame update when absolute distance from current frame time is below one interval.',
            'e1190a..e11936 takes loop branch and delegates to vtable+0x44 with start/end frames.',
            'e113ae forwards to vtable+0x48; e113c6..e113f2 resets accumulated time to float32(startFrame*interval), discarding excess elapsed time.'
        ], limitations=[
            'Static field/control-flow interpretation; no original-client execution.',
            'Effective rate assumes loader applies source CSB speed 0.5 and no later override.',
            'Loop-boundary, exact rounding and render scheduling equivalence not validated.'
        ])
    (OUT/'native-selection-clock.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(frame_interval=interval, derived_fps=report['derived_frames_per_second'], exports=len(exports))))


if __name__ == '__main__':
    main()
