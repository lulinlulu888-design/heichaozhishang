"""Verify recovered APK battle sprites and prepare a UE-only presentation manifest.

This does not execute APK scripts, infer hero ownership, or calculate game rules.
Original pixel data and static provenance stay untouched. All references are
relative to the workspace so the preparation step can be reproduced elsewhere.
"""
import hashlib
import json
import math
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/unreal/battle-ui'
APK_SHA = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
PINS = {
    'analysis/battle-ui/sprites.json': '239e2c12dd39600eae71a3b95eaad41c21412a4bcad46b8271d76125deda08fd',
    'analysis/battle-ui/card-frames/provenance.json': '01feab44ca6878e786212262936205f4fe0e7881a75c5eae9dd3716e1b9b6eb9',
    'analysis/card-art/tile-probe/manifest.json': '6394e45af076ca454cf7aa190461401551676d24906901ba1afac7cdc49cebae',
    'analysis/battle-ui/result/sprites/report.json': 'd0813e8ff20669cfbb49fd87131867c97e3fdc86320340eb20478c1514605d46',
    'analysis/battle-ui/health/player-portrait/report.json': 'dcbd75cbba1d3d96eedb83e434e7bff413b571d23afd64f9b809e0d3b19c29cd',
    'analysis/battle-ui/health/monster-portrait/report.json': '59c554541d488c984513f226e72760d4919b9b4e1de158babe5f5843a04bd654',
    'analysis/unreal/hall-ui/layout.json': '815367f3f73b4580d88d94e24ec36ea9128b2110f7a8eb4054a54f01f30e643d',
    'analysis/battle-ui/round-bg/report.json': '0b2aef0e17fa8807d309b3f10b227b4b20c565968812a259d7995de6cd48a9d5',
}


def verified(relative, expected):
    path = (ROOT / relative.replace('\\', '/')).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Source escapes workspace')
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('Recovered source identity changed: ' + relative)
    return path


def main():
    sources = {p: json.loads(verified(p, h).read_text('utf8')) for p, h in PINS.items()}
    sprites = []

    def sprite(key, path, digest, provenance, source_frame=None):
        image_path = verified(path, digest)
        with Image.open(image_path) as image:
            if image.mode != 'RGBA':
                raise ValueError('Recovered UI sprite must retain alpha')
            size = list(image.size)
        if key in {r['id'] for r in sprites}:
            raise ValueError('Duplicate sprite key')
        sprites.append({'id': key, 'png': image_path.relative_to(ROOT).as_posix(),
                        'pngSha256': digest, 'size': size,
                        'provenance': provenance, 'sourceFrame': source_frame})

    base = sources['analysis/battle-ui/sprites.json']
    if base['apk_sha256'] != APK_SHA:
        raise ValueError('Battle HUD source APK changed')
    for row in base['frames']:
        sprite(row['name'], row['png'], row['png_sha256'],
               'analysis/battle-ui/sprites.json', row['logical_frame'])
    round_bg = sources['analysis/battle-ui/round-bg/report.json']
    if round_bg['apk_sha256'] != APK_SHA or round_bg['size'] != [125, 28]:
        raise ValueError('Round background provenance changed')
    sprite('round-bg', round_bg['png'], round_bg['png_sha256'],
           'analysis/battle-ui/round-bg/report.json', round_bg['logical'])
    frames = sources['analysis/battle-ui/card-frames/provenance.json']
    for row in frames['frames']:
        if row['key'] in ('card/bg_atk_s.png', 'card/cost_s1.png'):
            key = 'card-frame-attack' if row['key'] == 'card/bg_atk_s.png' else 'card-cost'
            sprite(key, row['png'], row['sha256'],
                   'analysis/battle-ui/card-frames/provenance.json', row['key'])
    cards = sources['analysis/card-art/tile-probe/manifest.json']['cards']
    if {r['card_id'] for r in cards} != {110001, 110009, 210003, 410101, 410102}:
        raise ValueError('Unexpected recovered card-art mapping')
    for row in cards:
        sprite('card-' + str(row['card_id']), row['sprite'], row['sprite_sha256'],
               'analysis/card-art/tile-probe/manifest.json', row['mapping']['key'])
    for actor, relative in [('player-1', 'analysis/battle-ui/health/player-portrait/report.json'),
                            ('monster-991', 'analysis/battle-ui/health/monster-portrait/report.json')]:
        row = sources[relative]
        if row['apk_sha256'] != APK_SHA:
            raise ValueError('Portrait source APK changed')
        sprite(actor, row['output'], row['output_sha256'], relative, row['logical'])
    result_source = 'analysis/battle-ui/result/sprites/report.json'
    for row in sources[result_source]['frames']:
        if row['name'] in ('victory-title', 'victory-glow'):
            sprite(row['name'], row['png'], row['sha256'], result_source, row['source_frame'])

    # Display arrangement uses the recovered single-owner CardTools arc.
    geometry_path = 'analysis/battle-ui/card-geometry.json'
    geometry_sha = '315c282ad751105297aa23e1b9279b66bf40bf563448058df4afcf7a5d39edc2'
    geometry = json.loads(verified(geometry_path, geometry_sha).read_text('utf8'))
    if geometry['constants'] != {'_getR': 2800.0, '_getThetaMax': 3, '_getAlpha': 3.6,
                                 '_getDBeta': 1, 'getCardWidth': 126, 'getCardHeight': 166}:
        raise ValueError('Reviewed CardTools constants changed')
    by_count = {}
    # The ten-card source maximum arc is the limit recovered in examples.
    beta = geometry['examples'][-1]['step_degrees'] * 9
    for count in range(1, 11):
        width = min((count - 1) * 3, beta)
        step = width / (count - 1) if count > 1 else 0
        placements = []
        for index in range(count):
            omega = 90 - width / 2 + index * step
            angle = math.radians(omega)
            placements.append({'x': -2800 * math.cos(angle), 'y': 2800 * math.sin(angle) - 2710,
                               'rotation': -(omega - 90)})
        by_count[str(count)] = placements
    for example in geometry['examples']:
        for actual, original in zip(by_count[str(example['count'])], example['cards'], strict=True):
            if any(abs(actual[key] - original[source_key]) > 1e-7 for key, source_key in
                   [('x', 'x'), ('y', 'y'), ('rotation', 'creator_rotation')]):
                raise ValueError('CardTools presentation arc differs from recovered examples')

    font_rows = sources['analysis/unreal/hall-ui/layout.json']['fonts']
    font = next(r for r in font_rows if r['logicalPath'] == 'uires/CommonRes/droidsansfallback.ttf')
    font_path = verified(font['ttf'], font['sha256'])
    font = {'id': font['id'], 'ttf': font_path.relative_to(ROOT).as_posix(),
            'sha256': font['sha256'], 'logicalPath': font['logicalPath']}
    report = {'schemaVersion': 1, 'sourceApkSha256': APK_SHA,
              'evidenceKind': 'ordinary tools: verified static extraction and UE presentation inputs',
              'sourcePins': {**PINS, geometry_path: geometry_sha}, 'sprites': sprites, 'font': font,
              'runtime': {'canvas': [1280, 720], 'cardPlacements': by_count},
              'limitations': ['Original runtime colour profile is unverified.',
                             'HUD screen translations are reconstructed around the UE battle camera.',
                             'Only the five source-linked attack card illustrations are available.',
                             'Unknown illustrations remain absent; no card effects are calculated by this UI.',
                             'No original defeat-title image is yet recovered.']}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'manifest.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    icon_uses = {
        'energy-icon': '战斗左下能量图标；绘制 47×47 设计像素',
        'end-icon-normal': '右下回合结束按钮在请求/动画等待时的禁用状态；绘制 58×58 设计像素',
        'end-icon-active': '右下回合结束按钮；绘制 58×58 设计像素',
        'shield-icon': '角色和敌方头部 HUD 的护盾图标；绘制 21×22 设计像素',
        'deck-icon': '左下抽牌/弃牌计数旁图标；绘制 39×43 设计像素',
        'card-cost': '每张手牌左上费用宝石；绘制 32×38 设计像素',
    }
    inventory = {'schemaVersion': 1, 'scope': 'all 27 source assets imported by the new UE playable session HUD',
                 'consumer': 'clients/unreal5 5.8/Source/Hczs/Private/HczsSessionWidget.cpp',
                 'sourceAsset': '/Game/Recovered/Battle/UI/BattlePresentation.BattlePresentation',
                 'variantAsset': '/Game/Recovered/Battle/UI/AI/BattlePresentationHD.BattlePresentationHD',
                 'variantFlag': '-HczsHDIcons',
                 'variantPolicy': 'only the six explicitly listed icon keys are overridable; no card illustration, portrait, HP data or material channel redraw',
                 'style': '浅蓝/紫/白色轻渐变、白描边、无黑边；保持透明背景和功能轮廓',
                 'icons': [{**row, 'usage': icon_uses[row['id']], 'aiVariantAllowed': True,
                            'currentlyPainted': True}
                           for row in sprites if row['id'] in icon_uses],
                 'excludedAssets': [{**row, 'category': 'card-illustration' if row['id'].startswith('card-') and row['id'] not in ('card-frame-attack', 'card-cost')
                                     else 'character-portrait' if row['id'] in ('player-1', 'monster-991')
                                     else 'title-art' if row['id'].startswith('victory-') else 'hud-bar-or-frame',
                                     'aiVariantAllowed': False}
                                    for row in sprites if row['id'] not in icon_uses]}
    (OUT / 'icon-inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': True, 'sprites': len(sprites), 'font_faces': 1,
                      'manifest': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
