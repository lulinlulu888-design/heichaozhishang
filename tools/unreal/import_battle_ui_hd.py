"""Validate or import six independent AI icons into BattlePresentationHD.

Ordinary Python: --validate-only verifies pinned provenance and PNG identities.
Full Editor: -ExecutePythonScript imports without rewriting either original or
generated PNG pixels, then saves a distinct DataAsset with 20 shared non-icon
references and the original Chinese FontFace. No level is changed.
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = ROOT / 'analysis/unreal/battle-ui/ai-icons/provenance.json'
PINNED_PROVENANCE = 'aa43b92e918aac82de16b6b3c4176d2a52264d13a9b5c4f285db8bfae5f87009'
SOURCE_ASSET = '/Game/Recovered/Battle/UI/BattlePresentation'
DEST = '/Game/Recovered/Battle/UI/AI'
HD_ASSET = DEST + '/BattlePresentationHD'
REPORT = ROOT / 'analysis/unreal/battle-ui/ai-icons/ue-import-result.json'
EXPECTED_KEYS = {'energy-icon', 'end-icon-normal', 'end-icon-active', 'shield-icon', 'deck-icon', 'card-cost'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_file(relative, expected):
    path = (ROOT / relative.replace('\\', '/')).resolve()
    if not path.is_relative_to(ROOT) or sha(path) != expected:
        raise ValueError('Pinned source/variant file changed: ' + relative)
    return path


def png_size(path):
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR' or data[24:26] != b'\x08\x06':
        raise ValueError('Expected original RGBA8 PNG with preserved alpha')
    return list(struct.unpack('>II', data[16:24]))


def validate():
    if sha(PROVENANCE) != PINNED_PROVENANCE:
        raise ValueError('Reviewed AI-icon provenance identity changed')
    provenance = json.loads(PROVENANCE.read_text('utf8'))
    if provenance['schemaVersion'] != 1 or provenance['generatedPixelsModified'] or provenance['sourceAssetsModified']:
        raise ValueError('AI icon preservation policy changed')
    verify_file('analysis/unreal/battle-ui/manifest.json', provenance['sourceManifestSha256'])
    if {row['id'] for row in provenance['icons']} != EXPECTED_KEYS or len(provenance['icons']) != 6:
        raise ValueError('Variant may only replace the six reviewed UI icons')
    for row in provenance['icons']:
        if not row['reviewed'] or row['variantAudit']['opaqueNearBlackPixels'] != 0:
            raise ValueError('Icon style review did not pass')
        for filename, digest, audit in [(row['source'], row['sourceSha256'], row['sourceAudit']),
                                       (row['variant'], row['variantSha256'], row['variantAudit'])]:
            if png_size(verify_file(filename, digest)) != audit['size']:
                raise ValueError('PNG dimensions changed after audit')
        request = row['request']
        verify_file(request['requestFile'], request['requestFileSha256'])
        adjustment = row['drawAdjustment']
        if len(adjustment) != 4 or not all(math.isfinite(n) for n in adjustment) or not all(0 < n <= 8 for n in adjustment[:2]):
            raise ValueError('Unsafe geometry transform')
        # Verify the exact content footprint mapping without changing PNG pixels.
        sx, sy, sr, sb = row['sourceAudit']['alignmentBounds']
        nx, ny, nr, nb = row['variantAudit']['alignmentBounds']
        sw, sh = row['sourceAudit']['size']
        nw, nh = row['variantAudit']['size']
        ax, ay, ox, oy = adjustment
        mapped = [ox + nx / nw * ax, oy + ny / nh * ay, ox + nr / nw * ax, oy + nb / nh * ay]
        expected = [sx / sw, sy / sh, sr / sw, sb / sh]
        if max(abs(a - b) for a, b in zip(mapped, expected, strict=True)) > 1e-12:
            raise ValueError('Icon footprint does not match original source bounds')
    return provenance


def import_to_editor(provenance):
    import unreal
    if '-run=' in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Use the full Editor -ExecutePythonScript for the HD presentation import')
    original = unreal.load_asset(SOURCE_ASSET)
    if not original or original.get_class().get_name() != 'HczsBattlePresentationAsset':
        raise RuntimeError('Import original battle presentation first')
    if original.get_editor_property('SourceManifestSha256') != provenance['sourceManifestSha256']:
        raise RuntimeError('Original source DataAsset identity differs')
    original_sprites = dict(original.get_editor_property('Sprites'))
    original_font = original.get_editor_property('ChineseFont')
    original_json = original.get_editor_property('LayoutJson')
    if len(original_sprites) != 26 or not original_font:
        raise RuntimeError('Original asset dependencies incomplete')
    replacements = {}
    for row in provenance['icons']:
        source_texture = original_sprites[row['id']]
        if unreal.EditorAssetLibrary.get_metadata_tag(source_texture, 'HczsSourceSHA256') != row['sourceSha256']:
            raise RuntimeError('Original sprite identity differs')
        name = 'T_AI_' + row['id'].replace('-', '_') + '_' + row['version']
        folder = DEST + '/Sprites'
        path = folder + '/' + name
        texture = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
        if texture:
            if texture.get_class().get_name() != 'Texture2D' or unreal.EditorAssetLibrary.get_metadata_tag(texture, 'HczsSourceSHA256') != row['variantSha256']:
                raise RuntimeError('Existing AI texture retained because identity differs')
        else:
            task = unreal.AssetImportTask()
            for key, value in [('filename', str(verify_file(row['variant'], row['variantSha256']))),
                               ('destination_path', folder), ('destination_name', name),
                               ('automated', True), ('replace_existing', False), ('save', False)]:
                task.set_editor_property(key, value)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            objects = [obj for obj in task.get_objects() if obj.get_class().get_name() == 'Texture2D']
            if len(objects) != 1:
                raise RuntimeError('Expected one imported AI Texture2D')
            texture = objects[0]
            for key, value in [('lod_group', unreal.TextureGroup.TEXTUREGROUP_UI),
                               ('compression_settings', unreal.TextureCompressionSettings.TC_EDITOR_ICON),
                               ('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS),
                               ('lod_bias', 0), ('max_texture_size', 0), ('srgb', True),
                               ('filter', unreal.TextureFilter.TF_BILINEAR)]:
                texture.set_editor_property(key, value)
            unreal.EditorAssetLibrary.set_metadata_tag(texture, 'HczsSourceSHA256', row['variantSha256'])
            if not unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False):
                raise RuntimeError('Cannot save AI texture')
        if [texture.blueprint_get_size_x(), texture.blueprint_get_size_y()] != row['variantAudit']['size']:
            raise RuntimeError('Imported HD icon dimensions changed')
        replacements[row['id']] = texture
    hd = unreal.load_asset(HD_ASSET) if unreal.EditorAssetLibrary.does_asset_exist(HD_ASSET) else None
    if hd:
        if hd.get_editor_property('SourceManifestSha256') != PINNED_PROVENANCE:
            raise RuntimeError('Existing HD DataAsset retained because source identity differs')
    else:
        hd = unreal.EditorAssetLibrary.duplicate_asset(SOURCE_ASSET, HD_ASSET)
    if not hd:
        raise RuntimeError('Cannot create independent HD DataAsset')
    sprites = {**original_sprites, **replacements}
    layout = json.loads(original_json)
    layout['iconAlignment'] = {row['id']: row['drawAdjustment'] for row in provenance['icons']}
    hd.set_editor_property('SourceManifestSha256', PINNED_PROVENANCE)
    hd.set_editor_property('Sprites', sprites)
    hd.set_editor_property('LayoutJson', json.dumps(layout, ensure_ascii=False))
    hd.set_editor_property('ChineseFont', original_font)
    if not unreal.EditorAssetLibrary.save_loaded_asset(hd, only_if_is_dirty=False):
        raise RuntimeError('Cannot save independent HD DataAsset')
    saved = unreal.load_asset(HD_ASSET)
    actual = dict(saved.get_editor_property('Sprites'))
    unchanged = {key for key in original_sprites if key not in EXPECTED_KEYS}
    if len(actual) != 26 or any(actual[key].get_path_name() != original_sprites[key].get_path_name() for key in unchanged):
        raise RuntimeError('Non-icon reference changed')
    if saved.get_editor_property('ChineseFont').get_path_name() != original_font.get_path_name():
        raise RuntimeError('Original Chinese FontFace reference changed')
    if original.get_editor_property('LayoutJson') != original_json or original.get_editor_property('SourceManifestSha256') != provenance['sourceManifestSha256']:
        raise RuntimeError('Original DataAsset changed during HD import')
    report = {'passed': True, 'engine': unreal.SystemLibrary.get_engine_version(),
              'asset': saved.get_path_name(), 'provenanceSha256': PINNED_PROVENANCE,
              'changedIconReferences': 6, 'retainedNonIconReferences': len(unchanged), 'fontRetained': True,
              'originalDataAssetRetained': True, 'sourceAndGeneratedPNGPixelsModified': False,
              'iconAlignment': layout['iconAlignment'],
              'sprites': {key: obj.get_path_name() for key, obj in actual.items()},
              'usage': '-HczsHDIcons enables only reviewed icon-key overrides and original-footprint draw adjustments',
              'inGameRenderVerified': False}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    unreal.log('HCZS independent battle HD import passed: ' + str(REPORT))


def main():
    provenance = validate()
    parser = argparse.ArgumentParser()
    parser.add_argument('--validate-only', action='store_true')
    args, _ = parser.parse_known_args()
    if args.validate_only:
        print(json.dumps({'passed': True, 'icons': len(provenance['icons']),
                          'provenance_sha256': PINNED_PROVENANCE, 'geometry_alignment': True,
                          'ue_import_or_render_claimed': False}, ensure_ascii=False))
        return
    import_to_editor(provenance)


if __name__ == '__main__':
    main()
