"""Bounded read-only CSB node inspection against Cocos2d-x 3.17.2 field order.

Known root Node stores WidgetOptions directly; other observed classes wrap it.
Animation timelines and runtime layout adaptation are not evaluated.
"""
import hashlib
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-ui'
CLASSES = {'Node', 'SingleNode', 'Button', 'Panel', 'Sprite', 'Particle', 'ImageView', 'ProjectNode', 'Text', 'TextAtlas', 'TextBMFont', 'LoadingBar', 'ListView'}


class Reader:
    def __init__(self, data, *, preserve_unknown=False):
        if not 4 <= len(data) <= 16*1024*1024:
            raise ValueError('CSB size out of bounds')
        self.data = data
        self.seen = set()
        self.preserve_unknown = preserve_unknown

    def unpack(self, fmt, offset):
        size = struct.calcsize('<'+fmt)
        if not 0 <= offset <= len(self.data)-size:
            raise ValueError(f'Out of bounds at {offset}')
        return struct.unpack_from('<'+fmt, self.data, offset)

    def scalar(self, fmt, offset):
        return self.unpack(fmt, offset)[0]

    def pointer(self, offset):
        if not offset:
            return 0
        target = offset+self.scalar('I', offset)
        self.unpack('I', target)
        return target

    def field(self, table, index):
        if not table:
            return 0
        vtable = table-self.scalar('i', table)
        length, object_size = self.unpack('HH', vtable)
        if length < 4 or length % 2 or not 4 <= object_size <= len(self.data)-table:
            raise ValueError('Invalid vtable or object bounds')
        self.unpack(f'{length}s', vtable)
        relative = self.scalar('H', vtable+4+index*2) if 4+index*2 < length else 0
        if relative and not 4 <= relative < object_size:
            raise ValueError('Invalid field displacement')
        return table+relative if relative else 0

    def string(self, field):
        if not field:
            return None
        start = self.pointer(field)
        size = self.scalar('I', start)
        if size > 65536:
            raise ValueError('String too large')
        raw = self.unpack(f'{size+1}s', start+4)[0]
        if raw[-1] != 0:
            raise ValueError('Missing string terminator')
        return raw[:-1].decode('utf8')

    def pair(self, field):
        if not field:
            return None
        values = self.unpack('ff', field)
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Nonfinite geometry')
        return values

    def resource(self, table):
        if not table:
            return None
        return dict(path=self.string(self.field(table, 0)), plist=self.string(self.field(table, 1)))

    def node(self, table, depth=0):
        if table in self.seen or depth > 64 or len(self.seen) > 10000:
            raise ValueError('Node cycle or traversal budget exceeded')
        self.seen.add(table)
        classname = self.string(self.field(table, 0))
        if classname not in CLASSES:
            if not self.preserve_unknown:
                raise ValueError(f'Unimplemented class {classname}')
            # NodeTree's child vector is common; unknown Options must stay opaque.
            children = self.pointer(self.field(table, 1))
            count = self.scalar('I', children) if children else 0
            if count > 10000:
                raise ValueError('Too many children')
            return dict(offset=table, classname=classname, name=None,
                options_status='opaque-unimplemented',
                children=[self.node(self.pointer(children+4+i*4), depth+1) for i in range(count)])
        options = self.pointer(self.field(table, 2))
        data = self.pointer(self.field(options, 0))
        widget = data if classname == 'Node' else self.pointer(self.field(data, 0))
        def value(index, fmt, default):
            field = self.field(widget, index)
            return self.scalar(fmt, field) if field else default
        result = dict(offset=table, classname=classname, name=self.string(self.field(widget, 0)),
            action_tag=value(1, 'i', 0), rotation_skew=self.pair(self.field(widget, 2)),
            z_order=value(3, 'i', 0), visible=bool(value(4, 'B', 1)), alpha=value(5, 'B', 255),
            position=self.pair(self.field(widget, 7)), scale=self.pair(self.field(widget, 8)),
            anchor=self.pair(self.field(widget, 9)), size=self.pair(self.field(widget, 11)),
            flip_x=bool(value(12, 'B', 0)), flip_y=bool(value(13, 'B', 0)))
        color = self.field(widget, 10)
        result['color_argb'] = list(self.unpack('BBBB', color)) if color else None
        result['custom_property'] = self.string(self.field(widget, 17))
        if classname in ('Sprite', 'Particle', 'ImageView', 'Button', 'LoadingBar'):
            result['resource'] = self.resource(self.pointer(self.field(data, 1)))
        if classname == 'LoadingBar':
            # CSParseBinary.fbs LoadingBarOptions: preserve authored values,
            # including the schema default when a scalar is omitted.
            percent, direction = self.field(data, 2), self.field(data, 3)
            result['percent'] = self.scalar('i', percent) if percent else 80
            result['direction'] = self.scalar('i', direction) if direction else 0
            if result['direction'] not in (0, 1):
                raise ValueError('Unsupported LoadingBar direction')
        if classname == 'ListView':
            # Original standard ListViewOptions; no layout/scroll runtime execution.
            result['background_resource'] = self.resource(self.pointer(self.field(data, 1)))
            result['inner_size'] = self.pair(self.field(data, 12))
            for key,index,fmt,default in (('clip_enabled',2,'B',0), ('direction',13,'i',0),
                                         ('bounce_enabled',14,'B',0), ('item_margin',15,'i',0)):
                field=self.field(data,index)
                number=self.scalar(fmt,field) if field else default
                result[key]=bool(number) if fmt=='B' else number
            for key,index in (('direction_type',16),('horizontal_type',17),('vertical_type',18)):
                result[key]=self.string(self.field(data,index))
            if result['direction'] not in (0,1,2,3):
                raise ValueError('Unsupported ListView direction')
        if classname in ('Sprite', 'Particle'):
            blend = self.field(data, 2)
            result['blend_func'] = list(self.unpack('ii', blend)) if blend else None
        if classname == 'Button':
            result['pressed_resource'] = self.resource(self.pointer(self.field(data, 2)))
            result['disabled_resource'] = self.resource(self.pointer(self.field(data, 3)))
        if classname == 'ProjectNode':
            result['project_path'] = self.string(self.field(data, 1))
        layout = self.pointer(self.field(widget, 20))
        if layout:
            fields = [('position_x_percent_enabled','B'), ('position_y_percent_enabled','B'),
                ('position_x_percent','f'), ('position_y_percent','f'),
                ('size_x_percent_enabled','B'), ('size_y_percent_enabled','B'),
                ('size_x_percent','f'), ('size_y_percent','f'),
                ('stretch_horizontal_enabled','B'), ('stretch_vertical_enabled','B'),
                ('horizontal_edge','s'), ('vertical_edge','s'), ('left_margin','f'),
                ('right_margin','f'), ('top_margin','f'), ('bottom_margin','f')]
            result['layout'] = {}
            for index, (name, fmt) in enumerate(fields):
                field = self.field(layout, index)
                v = self.string(field) if fmt == 's' else self.scalar(fmt, field) if field else 0
                if fmt == 'f' and not math.isfinite(v):
                    raise ValueError('Nonfinite layout constraint')
                result['layout'][name] = bool(v) if fmt == 'B' else v
        if classname == 'Text':
            result['font_resource'] = self.resource(self.pointer(self.field(data, 1)))
            result['text'] = self.string(self.field(data, 4))
            result['font_name'] = self.string(self.field(data, 2))
            field = self.field(data, 3)
            result['font_size'] = self.scalar('i', field) if field else 0
            for key, index in (('area_width',6), ('area_height',7), ('h_alignment',8), ('v_alignment',9)):
                field = self.field(data, index)
                result[key] = self.scalar('i', field) if field else 0
            if result['h_alignment'] not in (0,1,2) or result['v_alignment'] not in (0,1,2):
                raise ValueError('Unsupported text alignment')
        if classname == 'TextBMFont':
            result['font_resource'] = self.resource(self.pointer(self.field(data, 1)))
            result['text'] = self.string(self.field(data, 2))
        children = self.pointer(self.field(table, 1))
        count = self.scalar('I', children) if children else 0
        if count > 10000:
            raise ValueError('Too many children')
        result['children'] = [self.node(self.pointer(children+4+i*4), depth+1) for i in range(count)]
        return result


def main():
    links = json.loads((OUT/'layout-links.json').read_text('utf8'))
    reports = []
    for layout in links['layouts']:
        path = OUT/(layout['name']+'.csb')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != layout['layout_source']['sha256']:
            raise ValueError('CSB differs from original extraction')
        reader = Reader(data)
        root = reader.scalar('I', 0)
        version = reader.string(reader.field(root, 0))
        if version != '2.1.0.0':
            raise ValueError('Unexpected source CSB version')
        tree = reader.node(reader.pointer(reader.field(root, 3)))
        reports.append(dict(name=layout['name'], source=layout['layout_source'], version=version,
            node_count=len(reader.seen), tree=tree))
    schema = ROOT/'tools/reference/cocos2dx/CSParseBinary.fbs'
    report = dict(schema_url='https://raw.githubusercontent.com/cocos2d/cocos2d-x/cocos2d-x-3.17.2/cocos/editor-support/cocostudio/fbs-files/CSParseBinary.fbs',
        schema_sha256=hashlib.sha256(schema.read_bytes()).hexdigest(), layouts=reports,
        limitations=['Partial field reader, not a full FlatBuffers verifier', 'No timeline playback or runtime layout adaptation',
            'No inference of global positions from unprocessed layout constraints', 'ImageView resource field follows standard schema; native fork extensions unverified'])
    (OUT/'layout-trees.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps([{k:r[k] for k in ('name','node_count')} for r in reports]))


if __name__ == '__main__':
    main()
