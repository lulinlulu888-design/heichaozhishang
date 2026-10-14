"""Recover shipped battle-success scripts and CSB layouts, without target execution."""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static
from inspect_battle_ui_layout import Reader
from inspect_selection_timeline import read_timeline
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/result'


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    rows = {row['index']: row for row in json.loads((static.SCRIPT / 'index.json').read_text('utf8'))}
    catalogue = read_catalogue(apk)
    OUT.mkdir(parents=True, exist_ok=True)
    layouts = {}
    for number in (3689, 4055, 5918, 9661, 6870, 999, 3559, 7690):
        row = rows[number]
        report = static.export(row)
        (OUT / f'{number}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
        print(number, row['filename'], 'code objects', len(report['code_objects']))
        if number in (3689, 9661, 6870, 999):
            continue
        module = static.read_module(row)
        paths = [value.decode() for value in module['consts'] if isinstance(value, bytes) and value.endswith(b'.csb')]
        if len(paths) != 1:
            raise ValueError('Ambiguous result CSB')
        path = OUT / f'{number}.csb'
        source = extract(apk, catalogue, paths[0], path, APK_SHA256)
        reader = Reader(path.read_bytes()); root = reader.scalar('I', 0)
        if reader.string(reader.field(root, 0)) != '2.1.0.0':
            raise ValueError('Unsupported CSB schema')
        layouts[str(number)] = dict(source=source, tree=reader.node(reader.pointer(reader.field(root, 3))))
        if number == 3559:
            timeline = read_timeline(path.read_bytes())
            (OUT / 'victory-timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2), 'utf8')
    (OUT / 'layouts.json').write_text(json.dumps(dict(apk_sha256=APK_SHA256, layouts=layouts,
        parser_sha256=hashlib.sha256((ROOT / 'tools/inspect_battle_ui_layout.py').read_bytes()).hexdigest(),
        limitations=['Static assets and partial bytecode, not original runtime or reward generation.']),
        ensure_ascii=False, indent=2), 'utf8')


if __name__ == '__main__':
    main()
