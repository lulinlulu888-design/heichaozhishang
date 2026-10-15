"""Import validated source FX geometry; never attach placeholder shading to a level."""
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_recovered_assets import make_pipeline
BASE = ROOT / 'analysis/battle-visual/elsa-ultimate/effects'
DEST = '/Game/Recovered/Battle/ElsaUltimateEffects'


def main():
    import unreal as u
    report = json.loads((BASE / 'mesh-export.json').read_text('utf8'))
    apply = '-HczsUltimateEffectsApply' in u.SystemLibrary.get_command_line()
    if apply and u.EditorAssetLibrary.list_assets(DEST, recursive=True, include_folder=False):
        raise ValueError('Destination exists; use read-only verification')
    for model in report['models']:
        if hashlib.sha256(Path(model['glb']).read_bytes()).hexdigest() != model['sha256']:
            raise ValueError('Converted source geometry changed')
    results = []
    for model in report['models']:
        destination = DEST + '/' + Path(model['glb']).stem.replace('-', '_')
        if apply:
            pipeline, overrides = make_pipeline(u, {'import_operation': 'asset'})
            params = u.ImportAssetParameters()
            params.set_editor_property('is_automated', True)
            params.set_editor_property('replace_existing', False)
            params.set_editor_property('override_pipelines', overrides)
            success = u.InterchangeManager.get_interchange_manager_scripted().import_asset(
                destination, u.InterchangeManager.create_source_data(model['glb']), params)
            if not (success[0] if isinstance(success, tuple) else success):
                raise RuntimeError('Import rejected: ' + model['gim'])
        paths = u.EditorAssetLibrary.list_assets(destination, recursive=True, include_folder=False)
        objects = [u.load_asset(p) for p in paths]
        meshes = [o for o in objects if isinstance(o, u.StaticMesh)]
        if len(meshes) != 1 or len(meshes[0].get_editor_property('static_materials')) != len(model['materials']):
            raise ValueError('Imported mesh or material slot count differs from source')
        if apply:
            for obj in objects:
                if not u.EditorAssetLibrary.save_loaded_asset(obj, only_if_is_dirty=False):
                    raise RuntimeError('Save failed: ' + obj.get_path_name())
        results.append({'source': model['gim'], 'sourceSha256': model['sha256'],
                        'mesh': meshes[0].get_path_name(), 'materialSlots': len(model['materials'])})
    return {'passed': True, 'applied': apply, 'models': results,
            'materialShadersImplemented': False, 'attachedToBattle': False}


if __name__ == '__main__':
    import unreal
    apply = '-HczsUltimateEffectsApply' in unreal.SystemLibrary.get_command_line()
    path = BASE / ('ue-import.json' if apply else 'ue-readback.json')
    try:
        result = main()
    except Exception:
        path.write_text(json.dumps({'passed': False, 'error': traceback.format_exc()}, indent=2), 'utf8')
        raise
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({'passed': True, 'models': len(result['models']), 'applied': apply}))
