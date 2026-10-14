"""Bounded APK scene inventory and script loading evidence; no game execution."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import zlib
import inspect_battle_rules as static
from extract_game_data import export_table
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue, lookup_logical

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/scene-inventory'

def main():
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    OUT.mkdir(parents=True, exist_ok=True)
    catalogue = read_catalogue(apk)
    table = export_table(9650)
    paths = sorted({r['fields']['ScenePath'] for r in table['rows'] if r['fields'].get('ScenePath')})
    mappings = [dict(path=p, matches=lookup_logical(catalogue, p)) for p in paths]
    pack, = [p for p in catalogue if p['member'] == 'assets/res/scene.npk']
    entries = []
    scenes = []
    with zipfile.ZipFile(apk) as archive, archive.open(pack['member']) as stream:
        loose = [n for n in archive.namelist() if 'city_battle_3' in n.lower() or n.lower().endswith('.scn')]
        for row in sorted(pack['entries'], key=lambda r:r['offset']):
            if row['encryption'] or row['compression'] not in (0,1) or row['original_size'] > 64*1024*1024:
                raise ValueError('Unsupported or oversized scene entry')
            stream.seek(row['offset']); raw = stream.read(row['stored_size'])
            if len(raw) != row['stored_size']: raise ValueError('Truncated entry')
            if row['compression']:
                decoder = zlib.decompressobj()
                data = decoder.decompress(raw, row['original_size']+1)
                if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError('Invalid compressed entry')
            else: data = raw
            if len(data) != row['original_size']: raise ValueError('Decoded size mismatch')
            record = dict(index=row['index'], sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                          xmlRoot=None, containsCityBattle3=b'city_battle_3' in data.lower())
            try: root = ET.fromstring(data)
            except ET.ParseError: root = None
            if root is not None:
                record['xmlRoot'] = root.tag
                if root.tag == 'NeoX' and root.find('Scene') is not None:
                    global_node = root.find('Scene/Global')
                    record['contentPath'] = global_node.get('ContentPath') if global_node is not None else None
                    record['modelCount'] = sum(1 for _ in root.iter('model'))
                    record['cameraCount'] = sum(1 for _ in root.iter('Camera'))
                    record['tablePaths'] = [m['path'] for m in mappings if any(
                        hit['member']==pack['member'] and hit['index']==row['index'] for hit in m['matches'])]
                    if any(p.startswith('scene/city_battle_') for p in record['tablePaths']):
                        (OUT/f"scene-{row['index']}.xml").write_bytes(data)
                        all_files = root.find('.//AllFiles')
                        files = [dict(id=e.tag,path=e.attrib['Path'],matches=lookup_logical(catalogue,e.attrib['Path']))
                                 for e in all_files] if all_files is not None else []
                        record['directDependencies'] = files
                        record['cameras'] = [e.attrib for e in root.iter('Camera')]
                        record['sceneTableRows'] = [r for r in table['rows'] if r['fields'].get('ScenePath') in record['tablePaths']]
                    scenes.append(record)
            entries.append(record)
    rows = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    scripts = []
    for number, names in [(1451, ('__init__','beginLoad')), (9638, ('__init__','beginLoad'))]:
        result = static.export(next(r for r in rows if r['index']==number), names)
        target = OUT/f'loader-{number}.json'
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
        scripts.append(dict(path=str(target.relative_to(ROOT)),sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    report = dict(evidence='Local hash-verified static extraction, not REA or original runtime',apkSha256=APK_SHA256,
        tableSource=table['source'], paths=mappings, scenePackIndexSha256=pack['index_sha256'],
        entries=entries, scenes=scenes, looseMembers=loose, loaderEvidence=scripts,
        limits=['XML structural classification covers scene.npk only.',
                'Exact table path hashes are searched across every NPK; collisions do not establish content identity.',
                'Native remapping, binary scene formats and downloaded resources remain outside this evidence.'])
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(entries=len(entries),xmlSceneCount=len(scenes),tablePaths=len(paths),
        matchedPaths=sum(bool(m['matches']) for m in mappings),looseMembers=loose,
        cityScenes=[dict(index=s['index'],path=s['tablePaths'],models=s['modelCount'],
            dependencies=len(s['directDependencies']),unmatched=[f['path'] for f in s['directDependencies'] if not f['matches']])
            for s in scenes if 'directDependencies' in s]),ensure_ascii=False))

if __name__ == '__main__':main()
