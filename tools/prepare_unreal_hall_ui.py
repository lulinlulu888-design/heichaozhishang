"""Build source-bound UE hall UI inputs from the original CSB graph and cutouts.

This is a bounded static conversion, not execution of the old UI or a UE import.
All inputs are hash checked; source visibility and local preview policy are separate.
"""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from audit_hall_ui_dependencies import ENTRY, ui_path
from extract_texture_samples import APK_SHA256
from inspect_battle_ui_layout import Reader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/unreal/hall-ui'
DEP = ROOT / 'analysis/hall/ui-dependencies/report.json'
PIXELS = ROOT / 'analysis/hall/ui-sprites/report.json'
REA = ROOT / 'analysis/rea/initial-artifact-evidence.json'
SCHEMA = ROOT / 'tools/reference/cocos2dx/CSParseBinary.fbs'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verified(path, expected):
    path = Path(str(path).replace('\\', '/'))
    path = path if path.is_absolute() else ROOT / path
    path = path.resolve()
    if not path.is_relative_to(ROOT) or digest(path) != expected:
        raise ValueError('Input path/hash mismatch: ' + str(path))
    return path


def packed(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


class HallReader(Reader):
    """Extend only standard option fields; custom ClippingNode remains opaque."""
    def node(self, table, depth=0):
        result = super().node(table, depth)
        if result.get('options_status'):
            return result
        options = self.pointer(self.field(table, 2))
        data = self.pointer(self.field(options, 0))
        widget = data if result['classname'] == 'Node' else self.pointer(self.field(data, 0))

        def scalar(owner, index, fmt, default):
            field = self.field(owner, index)
            return self.scalar(fmt, field) if field else default

        def color(owner, index):
            field = self.field(owner, index)
            return list(self.unpack('BBBB', field)) if field else None

        def rect(owner, index):
            field = self.field(owner, index)
            return list(self.unpack('ffff', field)) if field else None

        result['ignore_size'] = bool(scalar(widget, 14, 'B', 0))
        result['touch_enabled'] = bool(scalar(widget, 15, 'B', 0))
        result['callback_type'] = self.string(self.field(widget, 18))
        result['callback_name'] = self.string(self.field(widget, 19))
        cls = result['classname']
        if cls in ('Panel', 'ScrollView'):
            result['background_resource'] = self.resource(self.pointer(self.field(data, 1)))
            result['clip_enabled'] = bool(scalar(data, 2, 'B', 0))
            result['background_color_argb'] = color(data, 3)
            result['background_start_color_argb'] = color(data, 4)
            result['background_end_color_argb'] = color(data, 5)
            result['background_color_type'] = scalar(data, 6, 'i', 0)
            result['background_opacity'] = scalar(data, 7, 'B', 255)
            result['cap_insets'] = rect(data, 9)
            result['scale9_size'] = self.pair(self.field(data, 10))
            result['scale9_enabled'] = bool(scalar(data, 11, 'B', 0))
        elif cls == 'ImageView':
            result['cap_insets'] = rect(data, 2)
            result['scale9_size'] = self.pair(self.field(data, 3))
            result['scale9_enabled'] = bool(scalar(data, 4, 'B', 0))
        elif cls == 'Button':
            result['font_resource'] = self.resource(self.pointer(self.field(data, 4)))
            result['text'] = self.string(self.field(data, 5))
            # Shipped 2.1.0.0 tables omit the later isLocalized field. Bound string
            # reads and font size/type checks reject silently shifted schemas.
            result['font_name'] = self.string(self.field(data, 6))
            result['font_size'] = scalar(data, 7, 'i', 0)
            result['text_color_argb'] = color(data, 8)
            result['cap_insets'] = rect(data, 9)
            result['scale9_size'] = self.pair(self.field(data, 10))
            result['scale9_enabled'] = bool(scalar(data, 11, 'B', 0))
            result['display_state'] = bool(scalar(data, 12, 'B', 1))
        if cls == 'Text':
            for key, index in (('area_width',5), ('area_height',6), ('h_alignment',7), ('v_alignment',8)):
                result[key] = scalar(data, index, 'i', 0)
            if result['h_alignment'] not in (0,1,2) or result['v_alignment'] not in (0,1,2):
                raise ValueError('Unexpected shipped Text alignment schema')
        if cls in ('Text', 'Button'):
            start = 11 if cls == 'Text' else 13
            result['outline_enabled'] = bool(scalar(data, start, 'B', 0))
            result['outline_color_argb'] = color(data, start + 1)
            result['outline_size'] = scalar(data, start + 2, 'i', 1)
            result['shadow_enabled'] = bool(scalar(data, start + 3, 'B', 0))
            result['shadow_color_argb'] = color(data, start + 4)
            result['shadow_offset'] = [scalar(data, start + 5, 'f', 2), scalar(data, start + 6, 'f', -2)]
            result['shadow_blur_radius'] = scalar(data, start + 7, 'i', 0)
            if not 0 <= result.get('font_size',0) <= 512:
                raise ValueError('Unexpected shipped font size/schema')
        if cls == 'TextAtlas':
            result['font_resource'] = self.resource(self.pointer(self.field(data, 1)))
            result['text'] = self.string(self.field(data, 2))
            result['start_char_map'] = self.string(self.field(data, 3))
            result['item_width'] = scalar(data, 4, 'i', 0)
            result['item_height'] = scalar(data, 5, 'i', 0)
        return result


def multiply(first, second):
    a, b, c, d, x, y = first
    e, f, g, h, u, v = second
    return [a*e+c*f, b*e+d*f, a*g+c*h, b*g+d*h, a*u+c*v+x, b*u+d*v+y]


def transform(node):
    x, y = node.get('position') or [0, 0]
    sx, sy = node.get('scale') or [1, 1]
    ax, ay = node.get('anchor') or [0, 0]
    w, h = node.get('size') or [0, 0]
    rx, ry = [math.radians(v) for v in node.get('rotation_skew') or [0, 0]]
    a, b, c, d = math.cos(ry)*sx, -math.sin(ry)*sx, math.sin(rx)*sy, math.cos(rx)*sy
    return [a, b, c, d, x-a*ax*w-c*ay*h, y-b*ax*w-d*ay*h]


def point(matrix, x, y):
    a, b, c, d, u, v = matrix
    return [round(a*x+c*y+u, 6), round(b*x+d*y+v, 6)]


def geometry(matrix, size):
    a, b, c, d, x, y = matrix
    w, h = size
    screen = [a, -b, -c, d, x+c*h, 720-y-d*h]
    corners = [point(screen, 0, 0), point(screen, w, 0), point(screen, w, h), point(screen, 0, h)]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    return dict(matrix=[round(v, 9) for v in screen], corners=corners,
                bounds=[min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)])


def rgba(argb):
    a, r, g, b = argb or [255, 255, 255, 255]
    return [r/255, g/255, b/255, a/255]


def preview_reason(layout, node, ancestry):
    """Local UI policy, explicitly not recovered original runtime visibility."""
    name, path = node.get('name') or '', '.'.join(ancestry)
    leaf = Path(layout).name
    if leaf in {'ExchangeCharacterNode_ext.csb', 'ExchangeCharacterDance_ext.csb',
                'BackgroundExchangeArea_ext.csb'}:
        return 'character-and-background-menu-closed'
    if leaf in {'BeginnerGiftArea_ext.csb', 'KizunaAiBtn_ext.csb', 'HomeTopNew_ext.csb',
                'ActivityBannerArea_ext.csb', 'RightActivityDoorArea_ext.csb', 'ActivityDoorArea_ext.csb'}:
        return 'online-activity-state-unrestored'
    if leaf == 'DownloadArea_ext.csb':
        return 'old-download-state-unrestored'
    if leaf == 'DeviceInfoNode_ext.csb':
        return 'authored-clock-and-device-state-placeholder'
    if leaf == 'ItemStatus_Reddot_ext.csb' or any(
            'reddot' in part.lower() or 'red_dot' in part.lower() or part.lower() == 'rednode'
            for part in ancestry):
        return 'notification-state-unrestored'
    if name in ('Lock', 'IconLock'):
        return 'original-feature-unlock-state-unrestored'
    if leaf == 'FloorYueDu_ext.csb':
        return 'monthly-online-activity-unrestored'
    if leaf == 'CharFightingArea_ext.csb':
        return 'authored-party-portraits-not-local-party-state'
    if leaf == 'New_Story_Area_ext.csb':
        return 'chapter-new-state-unrestored'
    if leaf == 'PlayerHeadArea_ext.csb' and any(p in ancestry for p in ('LvBg', 'BarBg', 'Panel_1')):
        return 'level-experience-account-avatar-unrestored'
    if node.get('text') == 'NULL':
        return 'runtime-text-placeholder'
    if leaf == 'HomeBattle_story_ext.csb' and name == 'TextCur':
        return 'original-chapter-progress-unrestored'
    if leaf == 'ChatNode_ext.csb' and node.get('text'):
        return 'online-chat-unrestored'
    return None


def build(entry=ENTRY, dependency_report=DEP, pixel_report=PIXELS, output_directory=OUT,
          root_matrix=None):
    entry = ui_path(entry)
    dependency_report, pixel_report, output_directory = map(Path,
        (dependency_report, pixel_report, output_directory))
    if not all(p.resolve().is_relative_to((ROOT/'analysis').resolve())
               for p in (dependency_report, pixel_report, output_directory)):
        raise ValueError('UI build inputs and output must stay in analysis')
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if digest(apk) != APK_SHA256:
        raise ValueError('Unexpected APK bytes')
    report = json.loads(dependency_report.read_text('utf8'))
    pictures = json.loads(pixel_report.read_text('utf8'))
    if report['apk_sha256'] != APK_SHA256 or pictures['apk_sha256'] != APK_SHA256:
        raise ValueError('Mixed APK reports')
    if digest(dependency_report) != pictures['dependency_report_sha256'] or report['entry'] != entry:
        raise ValueError('Dependency graph drift')
    evidence = json.loads(REA.read_text('utf8'))
    evidence_ids = [r['evidence_id'] for r in evidence['records']
                    if r.get('subject', {}).get('digest', {}).get('sha256') == APK_SHA256]
    if len(evidence_ids) != 2:
        raise ValueError('Expected retained APK REA inventory evidence')
    layouts, sources = {}, []
    for row in report['layouts']:
        path = verified(row['source']['sample_path'], row['source']['sha256'])
        reader = HallReader(path.read_bytes(), preserve_unknown=True)
        root = reader.scalar('I', 0)
        if reader.string(reader.field(root, 0)) != '2.1.0.0':
            raise ValueError('Unsupported CSB version')
        tree = reader.node(reader.pointer(reader.field(root, 3)))
        if len(reader.seen) != row['node_count']:
            raise ValueError('Node count drift')
        layouts[row['path']] = tree
        sources.append(dict(path=row['path'], csb=str(path), source=row['source'],
                            version='2.1.0.0', nodeCount=len(reader.seen)))
    sprites, sprite_map = [], {}
    atlas_sources = {s['plist']['logical_path']: s for s in pictures['sources']}
    for frame in pictures['frames']:
        png = verified(frame['png'], frame['sha256'])
        name = png.stem
        sprite = dict(id=name, plist=frame['plist'], sourceFrame=frame['source_frame'],
                      png=str(png), pngSha256=frame['sha256'], size=frame['size'],
                      atlasFrame=frame['frame'], source=atlas_sources[frame['plist']],
                      untrimmed=True)
        sprites.append(sprite)
        sprite_map[(frame['plist'], frame['source_frame'])] = sprite
    fonts, font_map = [], {}
    for font in pictures['fonts']:
        path = verified(font['path'], font['sha256'])
        item = dict(id=path.stem, logicalPath=font['logical_path'], ttf=str(path),
                    sha256=font['sha256'], source=font['source'])
        fonts.append(item)
        font_map[font['logical_path']] = item
    nodes, draw_items, unresolved, exclusions = [], [], [], []
    used_layouts = []

    def visit(node, layout, parent, world, opacity, visible, path, stack, clip_ids,
              excluded=None, project_chain=()):
        if len(nodes) >= 10000 or len(project_chain) > 64:
            raise ValueError('UI expansion budget exceeded')
        name = node.get('name') or '<opaque>'
        full_path = path + [name]
        node_id = 'n' + str(len(nodes)).zfill(4)
        excluded = excluded or preview_reason(layout, node, full_path)
        metadata = {k: v for k, v in node.items() if k != 'children'}
        metadata.update(id=node_id, parentId=parent, layout=layout, instancePath='/'.join(full_path),
                        projectChain=list(project_chain), paintStack=stack,
                        previewExcludedReason=excluded)
        nodes.append(metadata)
        if excluded:
            exclusions.append(dict(nodeId=node_id, reason=excluded))
        if node.get('options_status'):
            unresolved.append(dict(kind='opaque-options', nodeId=node_id, layout=layout,
                                   classname=node['classname'], descendantCount=count(node)-1,
                                   consequence='Subtree has no safe transform/clip geometry; omitted from drawItems'))
            return
        world = multiply(world, transform(node))
        visible = visible and node['visible']
        opacity *= node['alpha']/255
        metadata.update(worldMatrixBottomLeft=world, effectiveVisible=visible,
                        effectiveOpacity=opacity)
        size = list(node.get('size') or [0, 0])
        clips = list(clip_ids)
        if node.get('clip_enabled'):
            metadata['clipGeometry'] = geometry(world, size)
            clips.append(node_id)
        children = sorted(enumerate(node['children']), key=lambda p: (p[1].get('z_order', 0), p[0]))
        for index, child in children:
            if child.get('z_order', 0) < 0:
                visit(child, layout, node_id, world, opacity, visible, full_path,
                      stack+[[child.get('z_order', 0), index]], clips, excluded, project_chain)

        def item(kind):
            return dict(id=node_id+'-'+kind, nodeId=node_id, kind=kind, layout=layout,
                        instancePath='/'.join(full_path), size=size, opacity=opacity,
                        color=rgba(node.get('color_argb')), visible=visible,
                        geometry=geometry(world, size), clipNodeIds=clips,
                        previewExcludedReason=excluded, paintIndex=len(draw_items),
                        sourceOffset=node['offset'], sourceActionTag=node.get('action_tag', 0))

        resource = node.get('resource') or node.get('background_resource')
        if node['classname'] == 'Particle' and resource and resource.get('path'):
            unresolved.append(dict(kind='particle-system', nodeId=node_id, layout=layout,
                                   resource=resource, visible=visible, effectiveOpacity=opacity,
                                   consequence='Original emitter configuration requires a separate Niagara conversion'))
        elif resource and resource.get('path'):
            frame = sprite_map.get((ui_path(resource['plist']), resource['path'])) if resource.get('plist') else None
            if frame:
                size = [size[i] or frame['size'][i] for i in range(2)]
                draw = item('sprite')
                draw.update(spriteId=frame['id'], flipX=node.get('flip_x', False),
                            flipY=node.get('flip_y', False), scale9Enabled=node.get('scale9_enabled', False),
                            capInsets=node.get('cap_insets'), blendFunc=node.get('blend_func'))
                if node['classname'] == 'LoadingBar':
                    draw['progress'] = dict(percent=node['percent'], direction=node['direction'],
                                            authority='authored-static-scalar')
                draw_items.append(draw)
            else:
                unresolved.append(dict(kind='resource', nodeId=node_id, layout=layout, resource=resource,
                                       visible=visible, effectiveOpacity=opacity,
                                       consequence='No decoded original pixel; no substitute image'))
        if node.get('background_color_type', 0):
            draw = item('panel-color')
            draw.update(colorType=node['background_color_type'],
                        color=rgba(node.get('background_color_argb')),
                        startColor=rgba(node.get('background_start_color_argb')),
                        endColor=rgba(node.get('background_end_color_argb')),
                        backgroundOpacity=node['background_opacity']/255)
            draw_items.append(draw)
        if node.get('text'):
            if node['classname'] not in ('Text', 'Button'):
                unresolved.append(dict(kind='non-ttf-text', nodeId=node_id, classname=node['classname'],
                                       text=node['text'], fontResource=node.get('font_resource')))
            else:
                draw = item('text')
                ref = node.get('font_resource') or {}
                font = font_map.get(ui_path(ref['path'])) if ref.get('path') else None
                draw.update(text=node['text'], fontId=font['id'] if font else None,
                            fontSize=node.get('font_size', 0), fontName=node.get('font_name'),
                            color=rgba(node.get('text_color_argb') or node.get('color_argb')),
                            horizontalAlignment=1 if node['classname']=='Button' else node.get('h_alignment', 0),
                            verticalAlignment=1 if node['classname']=='Button' else node.get('v_alignment', 0),
                            areaSize=[node.get('area_width', 0), node.get('area_height', 0)],
                            outlineEnabled=node.get('outline_enabled', False),
                            outlineSize=node.get('outline_size', 1),
                            outlineColor=rgba(node.get('outline_color_argb')),
                            shadowEnabled=node.get('shadow_enabled', False),
                            shadowOffset=node.get('shadow_offset'),
                            shadowColor=rgba(node.get('shadow_color_argb')),
                            shadowBlurRadius=node.get('shadow_blur_radius', 0),
                            textAuthority='authored-static-string-not-account-state')
                if node['classname'] == 'Button' and node['text'] in ('Button', 'button'):
                    draw['previewExcludedReason'] = excluded or 'button-authoring-placeholder'
                draw_items.append(draw)
        target = node.get('project_path')
        if target:
            child_layout = ui_path(target)
            if child_layout in project_chain or child_layout == layout:
                raise ValueError('ProjectNode cycle')
            if child_layout not in layouts:
                unresolved.append(dict(kind='missing-project', nodeId=node_id, path=child_layout))
            else:
                used_layouts.append(child_layout)
                visit(layouts[child_layout], child_layout, node_id, world, opacity, visible,
                      full_path+['@'+Path(child_layout).stem], stack+[[0, -1]], clips,
                      excluded, project_chain+(layout,))
        for index, child in children:
            if child.get('z_order', 0) >= 0:
                visit(child, layout, node_id, world, opacity, visible, full_path,
                      stack+[[child.get('z_order', 0), index]], clips, excluded, project_chain)

    def count(node):
        return 1 + sum(count(child) for child in node['children'])

    used_layouts.append(entry)
    visit(layouts[entry], entry, None, root_matrix or [1, 0, 0, 1, 0, 0], 1, True, [], [], [])
    visible_items = [x for x in draw_items if x['visible'] and x['opacity'] > 0]
    preview_items = [x for x in visible_items if not x['previewExcludedReason']]
    output = dict(schemaVersion=1, canvas=dict(width=1280, height=720, sourceOrigin='bottom-left',
                   drawOrigin='top-left', matrixOrder=['a','b','c','d','tx','ty'],
                   cornerOrder=['top-left','top-right','bottom-right','bottom-left']), entry=entry,
                  apkSha256=APK_SHA256, nodes=nodes, drawItems=visible_items,
                  previewDrawItems=preview_items, sprites=sprites, fonts=fonts, sources=sources,
                  unresolved=unresolved, previewPolicy=dict(authority='local-reconstruction-design-policy',
                  reason='Close unsupported menus and hide account/online authoring placeholders',
                  exclusions=exclusions),
                  evidence=dict(reaArchiveEvidenceIds=evidence_ids, reaBundle=str(REA),
                  reaBundleSha256=digest(REA), dependencyReportSha256=digest(dependency_report),
                  spriteReportSha256=digest(pixel_report), schemaSha256=digest(SCHEMA),
                  layoutEvidenceKind='ordinary-tool-static-CSB-conversion'),
                  limitations=[
                      'No original UI runtime, responsive adaptation, timeline or button execution.',
                      'Custom ClippingNode options/subtrees omitted; no inferred clip or transform.',
                      'Authored position/size used at 1280x720; layout constraints retained in nodes but not evaluated.',
                      'Opacity is multiplied along ancestors as a preview interpretation; native cascade setup unverified.',
                      'Nine-slice metadata and normal/pressed/disabled resources retained; renderer must implement them.',
                      'Non-TTF text, panel gradients, particle rendering and nonstandard blend modes require separate support.',
                      'Text values are CSB authoring data, never proof of level, chapter, time or account state.',
                      'Only explicit atlas references have recovered pixels; unresolved standalone files omitted.'
                  ])
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory/'layout.json').write_text(packed(output), 'utf8')
    summary = dict(schemaVersion=1, sourceLayouts=len(layouts), expandedInstances=len(used_layouts),
                   nodes=len(nodes), sourceVisibleDrawItems=len(visible_items), previewDrawItems=len(preview_items),
                   drawKinds=dict(Counter(x['kind'] for x in preview_items)),
                   sprites=len(sprites), fonts=len(fonts), unresolvedKinds=dict(Counter(x['kind'] for x in unresolved)),
                   usedSpriteIds=sorted({x['spriteId'] for x in preview_items if x['kind']=='sprite'}),
                   layoutSha256=digest(output_directory/'layout.json'))
    (output_directory/'report.json').write_text(packed(summary), 'utf8')
    return summary


def render_reference(output_directory=OUT):
    """Software visual sanity check, not a screenshot from the original game/UE."""
    from PIL import Image, ImageChops, ImageDraw, ImageFont
    output_directory = Path(output_directory)
    payload = json.loads((output_directory/'layout.json').read_text('utf8'))
    pictures = {row['id']: Image.open(row['png']).convert('RGBA') for row in payload['sprites']}
    fonts = {row['id']: row['ttf'] for row in payload['fonts']}
    node_map = {row['id']: row for row in payload['nodes']}
    canvas = Image.new('RGBA', (1280, 720))
    for item in payload['previewDrawItems']:
        w, h = [max(1, round(v)) for v in item['size']]
        if item['kind'] == 'sprite':
            pixels = pictures[item['spriteId']].copy()
            if item['flipX']:
                pixels = pixels.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if item['flipY']:
                pixels = pixels.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            # Reference keeps simple resampling; UE must use scale9 metadata.
            pixels = pixels.resize((w, h), Image.Resampling.LANCZOS)
        elif item['kind'] == 'text':
            pixels = Image.new('RGBA', (w, h))
            draw = ImageDraw.Draw(pixels)
            font = ImageFont.truetype(fonts[item['fontId']], max(1,item['fontSize']))
            bbox = draw.multiline_textbbox((0, 0), item['text'], font=font, spacing=0)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
            x = [0, (w-tw)/2, w-tw][item['horizontalAlignment']] - bbox[0]
            y = [0, (h-th)/2, h-th][item['verticalAlignment']] - bbox[1]
            color = tuple(round(v*255) for v in item['color'])
            draw.multiline_text((x,y), item['text'], font=font, fill=color, spacing=0)
        else:
            continue
        if item['kind'] == 'sprite':
            channels = pixels.split()
            pixels = Image.merge('RGBA', [channels[i].point(lambda x, f=item['color'][i]: round(x*f)) for i in range(4)])
        pixels.putalpha(pixels.getchannel('A').point(lambda x: round(x*item['opacity'])))
        a,b,c,d,x,y = item['geometry']['matrix']
        determinant = a*d-b*c
        if abs(determinant) < 1e-12:
            continue
        inverse = [d/determinant, -c/determinant, (c*y-d*x)/determinant,
                   -b/determinant, a/determinant, (b*x-a*y)/determinant]
        layer = pixels.transform(canvas.size, Image.Transform.AFFINE, inverse,
                                 resample=Image.Resampling.BICUBIC)
        for clip_id in item['clipNodeIds']:
            clip = Image.new('L', canvas.size)
            ImageDraw.Draw(clip).polygon([tuple(p) for p in node_map[clip_id]['clipGeometry']['corners']], fill=255)
            layer.putalpha(ImageChops.multiply(layer.getchannel('A'), clip))
        canvas = Image.alpha_composite(canvas, layer)
    canvas.save(output_directory/'reference-transparent.png')
    dark = Image.new('RGBA', canvas.size, (35,40,48,255))
    Image.alpha_composite(dark, canvas).convert('RGB').save(output_directory/'reference-on-dark.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-reference', action='store_true', help='Render a software coordinate sanity check')
    args = parser.parse_args()
    print(json.dumps(build(), ensure_ascii=False))
    if args.render_reference:
        render_reference()
