"""Recover hall SH inputs, the native packing formula and reusable shader.

The scene's 27 scalar coefficients are NOT the shader's seven float4 uniforms.
Packing is traced offline; runtime preprocessing and selection remain separate.
"""
import hashlib
import json
import math
import random
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'analysis/hall/lighting/source'
OUTPUT = ROOT / 'analysis/unreal/hall-lighting/environment'
EXPECTED = {
    'common.hlsl': '940ab1accbe9103717c9b00625a7295692e5bb12258c9bcd5c1129367e1be762',
    'hall.scn': '2eda711687e3461c1021be8bab3c339fc025fe5fc05ce8f0d0bc90932289c58b',
}


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def pack_complete_sh(values):
    """Native 0x941fec + complete branch 0x941f86, RGB-interleaved input."""
    if len(values) != 27 or not all(math.isfinite(v) for v in values):
        raise ValueError('Expected 27 finite RGB-interleaved coefficients')
    c = [list(map(f32, values[i:i+3])) for i in range(0, 27, 3)]
    rows = [[c[3][k], c[1][k], c[2][k], f32(c[0][k]-c[6][k])] for k in range(3)]
    rows += [[c[4][k], c[5][k], f32(3*c[6][k]), c[7][k]] for k in range(3)]
    return rows + [c[8] + [1.0]]


def verify_packing():
    # Independent nine-polynomial evaluation versus shader uniform layout.
    # Signed asymmetric coefficients expose channel/axis swaps and missing terms.
    rng = random.Random(941)
    normals = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    for _ in range(100):
        v = [rng.uniform(-1, 1) for _ in range(3)]
        length = math.sqrt(sum(n*n for n in v))
        normals.append(tuple(n/length for n in v))
    max_error = 0.0
    for _ in range(20):
        c = [f32(rng.uniform(-2, 2)) for _ in range(27)]
        p = pack_complete_sh(c)
        for x,y,z in normals:
            basis = [1,y,z,x,x*y,y*z,3*z*z-1,z*x,x*x-y*y]
            for k in range(3):
                direct = sum(c[i*3+k]*basis[i] for i in range(9))
                packed = sum(a*b for a,b in zip(p[k], [x,y,z,1]))
                packed += sum(a*b for a,b in zip(p[k+3], [x*y,y*z,z*z,z*x]))
                packed += p[6][k]*(x*x-y*y)
                max_error = max(max_error, abs(direct-packed))
    if max_error > 1e-6:
        raise ValueError('SH packing polynomial mismatch')
    return {'normalSamples': len(normals), 'coefficientSets': 20, 'maxAbsoluteError': max_error,
            'scope': 'Algebraic packing equivalence; not GPU/native runtime parity'}


def source(name):
    data = (SOURCE / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED[name]:
        raise ValueError('Recovered source identity changed: ' + name)
    return data.decode('utf8')


def function(text, name):
    start = re.search(r'\bfloat3\s+' + name + r'\s*\(', text)
    if not start:
        raise ValueError('Original SH function missing: ' + name)
    brace = text.index('{', start.start())
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start.start():end]


def build():
    shader = source('common.hlsl')
    scene = ET.fromstring(source('hall.scn'))
    probe = scene.find('./Scene/Global/LightProbe')
    coefficients = [float(n.text) for n in probe.findall('./SkyBoxSH/SHValue')]
    if len(coefficients) != 27:
        raise ValueError('Expected original nine RGB SH coefficients')
    # Preserve both original polynomial bodies byte-for-byte. Only pass their
    # global uniform explicitly and namespace the function names for UE use.
    functions = []
    for name in ('SHEvalLinearL0L1', 'SHEvalLinearL2'):
        body = function(shader, name)
        signature = re.compile(r'\b' + name + r'\s*\(float4 normal\)')
        body, count = signature.subn('Hczs' + name + '(float4 normal, float4 LightProbeSH[7])', body)
        if count != 1:
            raise ValueError('Original SH signature changed')
        functions.append(body)
    code = ('// Recovered common.hlsl SHA256: ' + EXPECTED['common.hlsl'] + '\n'
            '// Input is native packed LightProbeSH, NOT raw scene SkyBoxSH.\n'
            '// Normal must already be normalized in NeoX world coordinates.\n'
            '#ifndef HCZS_SOURCE_ENVIRONMENT_SH\n#define HCZS_SOURCE_ENVIRONMENT_SH\n'
            + '\n\n'.join(functions) + '\n\n'
            'float3 HczsSourceEnvironmentSH(float3 SourceWorldNormal, float4 PackedSH[7])\n'
            '{\n    float4 n = float4(SourceWorldNormal, 1.0);\n'
            '    return clamp(HczsSHEvalLinearL0L1(n, PackedSH) + HczsSHEvalLinearL2(n, PackedSH), 0.0, 10.0);\n}\n'
            '#endif\n')
    lights = []
    for light in scene.findall('.//light'):
        lights.append({'attributes': light.attrib,
                       'diffuseKeys': [node.attrib for node in light.findall('./Diffuse/*')]})
    report = {
        'sourceHashes': EXPECTED,
        'skyBoxSHRaw': coefficients,
        'packedCompleteSHCandidate': pack_complete_sh(coefficients),
        'packingEvidence': 'native/trace.json; functions 0x941f6c and 0x941fec',
        'packingVerification': verify_packing(),
        'skyLightColor': probe.find('SkyLightColor').attrib,
        'ambient': scene.find('./Scene/Global/AmbientLight').attrib,
        'lights': lights,
        'shaderBranch': 'LIGHT_PROBE_BLEND_COMPLETE; RGB only',
        'shaderUniformShape': [7, 4],
        'unresolved': ['runtime preprocessing of SkyBoxSH before the verified packing function',
                       'runtime probe selection and enabled shader macros',
                       'source world-normal mapping for the imported UE actor',
                       'skin transmission, hair and reflection contribution'],
        'appliedToRuntime': False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'HczsSourceEnvironmentSH.ush').write_text(code, encoding='utf8')
    (OUTPUT / 'source-inputs.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(f'Recovered {len(coefficients)} raw SH coefficients, native packing and {len(lights)} light definitions; runtime selection remains unverified.')


if __name__ == '__main__':
    build()
