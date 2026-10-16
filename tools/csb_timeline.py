"""Original CSB node walk and timeline reader shared by battle UI preparers."""
from __future__ import annotations
import math

from inspect_battle_ui_layout import Reader
from inspect_selection_timeline import read_timeline


def walk(node, parents=()):
    yield node, parents
    for child in node['children']:
        yield from walk(child, (*parents, {'name': node['name'], 'actionTag': node.get('action_tag')}))


def timeline_with_inner(data):
    """Checked common schema plus bounded, explicit APK-fork frame payloads."""
    try:
        return read_timeline(data)
    except ValueError as exc:
        if str(exc) not in ('Inner-action frame is not implemented', 'Ambiguous frame variant'):
            raise
    r = Reader(data)
    root = r.scalar('I', 0)

    def scalar(table, index, fmt='i', default=0):
        field = r.field(table, index)
        return r.scalar(fmt, field) if field else default

    def vector(table, index):
        p = r.pointer(r.field(table, index))
        if not p:
            return []
        count = r.scalar('I', p)
        if count > 10000:
            raise ValueError('Timeline vector exceeds bounded reader')
        return [r.pointer(p + 4 + i * 4) for i in range(count)]

    action = r.pointer(r.field(root, 4))
    kinds = {0: 'point', 1: 'scale', 2: 'color', 3: 'texture', 4: 'event', 5: 'int',
             6: 'bool', 7: 'inner_action', 8: 'blend', 10: 'fork_float_vector', 11: 'fork_float'}
    timelines = []
    for timeline in vector(action, 2):
        frames = []
        for frame in vector(timeline, 2):
            vtable = frame - r.scalar('i', frame)
            field_count = (r.scalar('H', vtable) - 4) // 2
            if field_count > 32:
                raise ValueError('Frame union budget exceeded')
            variants = [(i, r.pointer(r.field(frame, i))) for i in range(field_count) if r.field(frame, i)]
            if len(variants) != 1:
                raise ValueError('Ambiguous frame variant')
            kind, table = variants[0]
            if kind not in kinds:
                raise ValueError('Unimplemented APK frame union field ' + str(kind))
            field = r.field(table, 2)
            if kind in (0, 1):
                value = r.pair(field)
            elif kind == 2:
                value = list(r.unpack('BBBB', field)) if field else None
            elif kind == 3:
                value = r.resource(r.pointer(field))
            elif kind == 4:
                value = r.string(field)
            elif kind == 5:
                value = scalar(table, 2)
            elif kind == 6:
                value = bool(scalar(table, 2, 'B', 1))
            elif kind == 7:
                value = {'innerActionType': scalar(table, 2),
                         'currentAnimationName': r.string(r.field(table, 3)),
                         'singleFrameIndex': scalar(table, 4)}
            elif kind == 8:
                value = list(r.unpack('ii', field)) if field else None
            elif kind == 10:
                p = r.pointer(field)
                count = r.scalar('I', p) if p else 0
                if count not in (1, 2, 3, 4):
                    raise ValueError('Unexpected shader parameter width: ' + str(count))
                value = list(r.unpack('f' * count, p + 4))
            elif kind == 11:
                value = scalar(table, 2, 'f')
            if kind in (10, 11) and not all(math.isfinite(v) for v in (value if isinstance(value, list) else [value])):
                raise ValueError('Nonfinite fork-frame value')
            easing = r.pointer(r.field(table, 5 if kind == 7 else 3))
            points = r.pointer(r.field(easing, 1)) if easing else 0
            count = r.scalar('I', points) if points else 0
            if count > 1000:
                raise ValueError('Easing point budget exceeded')
            frames.append({'index': scalar(table, 0), 'tween': bool(scalar(table, 1, 'B', 1)),
                           'kind': kinds[kind], 'value': value, 'sourceOffset': frame,
                           'unionField': kind, 'payloadOffset': table,
                           'easing_type': scalar(easing, 0, default=-1) if easing else -1,
                           'easing_points': [r.pair(points + 4 + i * 8) for i in range(count)]})
        timelines.append({'property': r.string(r.field(timeline, 0)),
                          'action_tag': scalar(timeline, 1), 'frames': frames})
    return {'duration': scalar(action, 0), 'speed': scalar(action, 1, 'f'),
            'animations': [{'name': r.string(r.field(t, 0)), 'start': scalar(t, 1), 'end': scalar(t, 2)} for t in vector(root, 5)],
            'timelines': timelines}
