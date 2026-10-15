"""Copy native image_gen results byte-for-byte; audit common HD icon variants.

No PNG raster editing. Uses only the source files already inspected by the agent
and persisted complete generation requests. Writes versioned independent files,
provenance, a reviewed selection manifest, and an appended project audit status.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/assets/ai-icons/common'
PINNED_LAYOUT = '815367f3f73b4580d88d94e24ec36ea9128b2110f7a8eb4054a54f01f30e643d'
REVIEW = {
    'chat': 'Three dots and original balloon tail retained; candidate for hall chat sprite.',
    'harvest': 'Clipboard, circular hourglass and orange lower paper rule retained; candidate for hall quick harvest.',
    'notification': 'Red lozenge and one white exclamation retained; library only, no inferred notification state.',
    'new': 'v1 invented circular decorations; v3 has a dark lower smudge and was rejected. v2 keeps exact NEW and coral rectangle. Subject proportions differ and need runtime geometry review.',
    'dance': 'Source is a raised-arm dancer silhouette. AI introduces hair/finger refinements; silhouette variant only, not original high-resolution evidence.',
    'battery': 'Empty horizontal battery with right terminal and transparent hole; no fabricated charge state.',
    'battery-fill': 'v1 capsule/shadow rejected, v2 is too thin. v3 retains flat teal rectangle but visible aspect still differs; source 20:8 ratio must be retained by later UI geometry. Library only.',
    'charge': 'Single cyan lightning bolt; no case, number or percentage.',
    'network': 'Left down arrow / right up arrow retained. This is data transfer, not Wi-Fi.',
    'change-view': 'v1 halo rejected; v2 restores the two-arrow rounded diamond opening without broad glow. Low-alpha scatter remains.',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', 'utf8')


def inspect_png(path, require_transparent=False):
    payload = path.read_bytes()
    with Image.open(path) as image:
        if image.mode != 'RGBA':
            raise ValueError('AI/source PNG is not RGBA: ' + str(path))
        pixels = np.asarray(image)
        alpha = pixels[:, :, 3]
        result = dict(sha256=sha(payload), bytes=len(payload), size=list(image.size), mode=image.mode,
                      alphaRange=[int(alpha.min()), int(alpha.max())], transparentPixelFraction=float(np.mean(alpha == 0)),
                      partialAlphaFraction=float(np.mean((alpha > 0) & (alpha < 255))),
                      opaqueDarkPixelFraction=float(np.mean((alpha >= 128) & np.all(pixels[:, :, :3] < 48, axis=2))))
        for threshold, label in ((1, 'alphaAny'), (128, 'alpha128'), (250, 'alpha250')):
            ys, xs = np.nonzero(alpha >= threshold)
            if not len(xs):
                box = None
            else:
                box = [int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1]
            result[label+'BBox'] = box
            result[label+'BBoxNormalized'] = ([box[0]/image.width, box[1]/image.height,
                box[2]/image.width, box[3]/image.height] if box else None)
        if result['alpha128BBox'] is None or (require_transparent and result['alphaRange'][0] != 0):
            raise ValueError('Image lacks genuine transparent background or visible subject')
        return result


def main():
    requests = json.loads((BASE/'generation-records-final.json').read_text('utf8'))
    layout_path = ROOT / 'analysis/unreal/hall-ui/layout.json'
    layout_raw = layout_path.read_bytes()
    if sha(layout_raw) != PINNED_LAYOUT:
        raise ValueError('Original hall layout changed')
    layout = json.loads(layout_raw)
    source_audit_path = ROOT / 'analysis/assets/icon-audit.json'
    source_audit_bytes = source_audit_path.read_bytes()
    source_audit = json.loads(source_audit_bytes)
    original_by_path = {str((ROOT/f).resolve()): row for row in source_audit['recovered_original_images'] for f in row['files']}
    items = {}
    for request in requests['jobs']:
        match = re.fullmatch(r'(.+?)(?:-v(\d+))?', request['name'])
        key, version = match[1], int(match[2] or 1)
        source_path = Path(request['source']).resolve()
        generated_path = Path(request['generated_path']).resolve()
        codex_generated = (Path.home()/'.codex/generated_images').resolve()
        if not source_path.is_relative_to(ROOT) or not generated_path.is_relative_to(codex_generated):
            raise ValueError('Unexpected source/generation output directory')
        if str(source_path) not in original_by_path:
            raise ValueError('Source is not in retained icon audit')
        original = original_by_path[str(source_path)]
        source_info = inspect_png(source_path)
        if source_info['sha256'] != original['encoded_sha256']:
            raise ValueError('Original icon PNG changed')
        output = BASE / f'{key}-ai-v{version}.png'
        generated_payload = generated_path.read_bytes()
        if output.exists() and output.read_bytes() != generated_payload:
            raise ValueError('Versioned output exists with different pixels; choose a new version')
        if not output.exists():
            shutil.copyfile(generated_path, output)
        output_info = inspect_png(output, require_transparent=True)
        if output_info['sha256'] != sha(generated_payload):
            raise ValueError('Generated output copy differs')
        row = items.setdefault(key, dict(name=key, source=dict(png=source_path.relative_to(ROOT).as_posix(),
            sourceFrame=original['logical_path'], metadata=source_info,
            provenanceReports=original['reports'], consumers=original['consumers'], apkSha256=layout['apkSha256']), variants=[]))
        row['variants'].append(dict(version=version, png=output.relative_to(ROOT).as_posix(), generatedFile=str(generated_path),
            tool='built-in image_gen.imagegen', transparentBackground=True, prompt=request['prompt'],
            referencedImages=request['referenced_image_paths'], selected=request['selected'],
            metadata=output_info, rasterPixelMutation=False))
    manifest_icons = []
    for name, row in sorted(items.items()):
        selections = [variant for variant in row['variants'] if variant['selected']]
        if len(selections) != 1:
            raise ValueError('Each icon must have exactly one selected reviewed candidate')
        source = row['source']
        source_sprite = next((sprite for sprite in layout['sprites'] if sprite['pngSha256'] == source['metadata']['sha256']), None)
        bindings = [dict(id=item['id'], instancePath=item['instancePath'], size=item['size'], geometry=item['geometry'])
                    for item in layout['previewDrawItems'] if source_sprite and item['kind']=='sprite' and item['spriteId']==source_sprite['id']]
        variant = selections[0]
        manifest_icons.append(dict(name=name, sourceSpriteId=source_sprite['id'] if source_sprite else None,
            sourceLibraryId=name if not source_sprite else None,
            sourceFrame=source['sourceFrame'], sourcePNG=source['png'], sourcePNG_SHA256=source['metadata']['sha256'],
            sourceSize=source['metadata']['size'], sourceAlpha128BBoxNormalized=source['metadata']['alpha128BBoxNormalized'],
            aiPNG=variant['png'], aiPNG_SHA256=variant['metadata']['sha256'], aiVersion=variant['version'],
            aiSize=variant['metadata']['size'], aiAlpha128BBoxNormalized=variant['metadata']['alpha128BBoxNormalized'],
            hallPreviewBindings=bindings, hallImportCandidate=name in ('chat','harvest'),
            libraryOnly=name not in ('chat','harvest'), currentClientImported=False,
            review=REVIEW[name], sourceSemanticsVerifiedBy='retained source frame + direct visual inspection; no original runtime',
            generatedDetailsOriginalEvidence=False))
    provenance = dict(schema='hczs-common-ai-icon-provenance-v1', sourceLayoutSHA256=PINNED_LAYOUT,
        historicalIconAuditSHA256=sha(source_audit_bytes), generatedIcons=10,
        generatedVariants=sum(len(row['variants']) for row in items.values()),
        imageEditingTool='built-in image_gen.imagegen', sourcePNGMutation=False, generatedPNGMutation=False,
        imagegenSkill='C:/Users/5090B/.codex/skills/.system/imagegen/SKILL.md',
        icons=list(items.values()), limitations=['AI-generated high-definition variants, not recovered original high-resolution assets.',
            'Low-alpha edge scatter may remain. Alpha128 is a display-alignment reference, not a permission to crop/erase pixels.',
            'Image geometry and some invented silhouette refinements require in-client visual acceptance.',
            'Only chat/harvest have active hall-preview bindings; no fake system battery/network or notification status is introduced.',
            'Normal/mix/depth/data maps are not processed.'])
    write(BASE/'provenance.json', provenance)
    manifest = dict(schema='hczs-common-ai-icon-selection-v1', sourceLayoutSHA256=PINNED_LAYOUT,
                    provenanceSHA256=sha((BASE/'provenance.json').read_bytes()), icons=manifest_icons,
                    PNGMutation=False, runtimeMutation=False,
                    displayPolicy='Use original widget geometry and source aspect, align alpha128 subject in UI; never edit generated PNG pixels.')
    write(BASE/'manifest.json', manifest)
    status_path = ROOT / 'analysis/assets/icon-audit-status-common-ai.json'
    write(status_path, dict(schema='hczs-project-icon-status-append-v1', historicalIconAuditSHA256=sha(source_audit_bytes),
        batch='common-ai-icons', originalIconSources=10, aiVariantFiles=provenance['generatedVariants'], selectedCandidateIcons=10,
        currentClientImported=0, activeHallCandidates=2, libraryOnlyIcons=8,
        manifest=manifest_path(ROOT, BASE/'manifest.json'), manifestSHA256=sha((BASE/'manifest.json').read_bytes()),
        sourcePNGMutation=False, sourceLayoutMutation=False, historicalAuditRewritten=False,
        generatedOriginalHighResolutionRecovery=False, followup='UE import plus actual small-scale original/AI comparison remains separate'))
    if source_audit_path.read_bytes() != source_audit_bytes or layout_path.read_bytes() != layout_raw:
        raise ValueError('Historical source audit/layout changed during generation audit')
    print(json.dumps(dict(passed=True, sources=10, variants=provenance['generatedVariants'], selected=10,
                         hall_candidates=[icon['name'] for icon in manifest_icons if icon['hallImportCandidate']],
                         manifest=str(BASE/'manifest.json')), ensure_ascii=False))


def manifest_path(root, path):
    return path.relative_to(root).as_posix()


if __name__ == '__main__':
    main()
