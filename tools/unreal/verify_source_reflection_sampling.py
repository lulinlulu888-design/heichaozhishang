"""Render and read six cube face centers at every authored mip on the GPU.

The 48 samples validate those sample locations, not cube edge/orientation parity
or original NeoX runtime probe selection. No maps or source assets are modified.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from repair_battle_visual_materials import node, link, prop, create_material, save_material

BASE = ROOT / 'analysis/battle-visual/reflection/boss_theatre'
OUT = ROOT / 'analysis/unreal/battle-reference/reflection-gpu-sampling.json'
CODE = '''int face = min(5, (int)floor(UV.y * 6));
float mip = min(7.0, floor(UV.x * 8));
float3 direction = float3(1,0,0);
if(face==1) direction=float3(-1,0,0);
else if(face==2) direction=float3(0,1,0);
else if(face==3) direction=float3(0,-1,0);
else if(face==4) direction=float3(0,0,1);
else if(face==5) direction=float3(0,0,-1);
return Probe.SampleLevel(ProbeSampler, direction, mip).rgb;'''


def run():
    if 'NullRHI' in u.SystemLibrary.get_command_line():
        raise RuntimeError('GPU validation requires a real RHI')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    report = json.loads((BASE / 'dds.json').read_text('utf8'))
    readback = json.loads((ROOT / 'analysis/unreal/battle-reference/source-reflection-import.json').read_text('utf8'))
    if readback['sourceDdsSha256'] != report['ddsSha256'] or report['mipCount'] != 8 or report['size'] != 128:
        raise ValueError('Reviewed cube size or source identity changed')
    cube = u.load_asset(readback['asset'])
    if not isinstance(cube, u.TextureCube) or cube.get_editor_property('srgb') or u.EditorAssetLibrary.get_metadata_tag(cube, 'HczsSourceDDS') != report['ddsSha256']:
        raise RuntimeError('Actual cube metadata differs')
    recipe_sha = hashlib.sha256((report['ddsSha256'] + CODE).encode()).hexdigest()
    plan = dict(destination='/Game/Recovered/SourceStages/Reflection/Diagnostics/v_' + recipe_sha[:16], recipe_sha256=recipe_sha)
    material, build = create_material(u, plan, 'M_CubeMipCenters', 'OPAQUE')
    if build:
        custom = node(u, material, u.MaterialExpressionCustom, 0, 0, code=CODE,
            output_type=u.CustomMaterialOutputType.CMOT_FLOAT3)
        inputs = []
        for name in ('UV', 'Probe'):
            pin = u.CustomInput(); pin.set_editor_property('input_name', name); inputs.append(pin)
        custom.set_editor_property('inputs', inputs)
        uv = node(u, material, u.MaterialExpressionTextureCoordinate, -400, 0, coordinate_index=0)
        probe = node(u, material, u.MaterialExpressionTextureObject, -400, 200,
            texture=cube, sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(u, uv, '', custom, 'UV'); link(u, probe, '', custom, 'Probe')
        prop(u, custom, '', u.MaterialProperty.MP_EMISSIVE_COLOR)
        save_material(u, material, plan)
    target = u.RenderingLibrary.create_render_target2d(world, 8, 6,
        format=u.TextureRenderTargetFormat.RTF_RGBA16F, clear_color=u.LinearColor(0,0,0,0),
        auto_generate_mip_maps=False)
    if not target:
        raise RuntimeError('Float render target creation failed')
    u.RenderingLibrary.draw_material_to_render_target(world, target, material)
    samples = []
    for face in range(6):
        for mip in range(8):
            value = u.RenderingLibrary.read_render_target_raw_pixel(world, target, mip, face, normalize=False)
            samples.append(dict(face=face, mip=mip, rgb=[value.r, value.g, value.b], alpha=value.a))
    result = dict(sourceDdsSha256=report['ddsSha256'], material=material.get_path_name(),
        map=world.get_path_name(), format=str(target.get_editor_property('render_target_format')),
        engine=u.SystemLibrary.get_engine_version(), sampleLocations='six axis face centers at integer LOD 0..7',
        samples=samples, comparisonPassed=False,
        limitation='Actual GPU sample values only; independently compare against pinned decoded PNG center samples before claiming sample parity. Cube edges and basis orientation are not established.')
    OUT.write_text(json.dumps(result, indent=2), 'utf8')


try:
    previous_error = OUT.with_suffix('.error.txt')
    if previous_error.exists():
        previous_error.rename(OUT.with_name('reflection-gpu-sampling.error-' + str(time.time_ns()) + '.txt'))
    if OUT.exists():
        OUT.rename(OUT.with_name('reflection-gpu-sampling.previous-' + str(time.time_ns()) + '.json'))
    run()
except Exception:
    OUT.with_suffix('.error.txt').write_text(traceback.format_exc(), 'utf8')
finally:
    u.SystemLibrary.quit_editor()
