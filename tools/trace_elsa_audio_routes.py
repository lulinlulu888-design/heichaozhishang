"""Verify wwiser's direct event/play/sound routes against bank bytes and media.

Run wwiser v20260808 XML export first. Container traversal and playback are not
implemented here; unresolved objects are retained explicitly.
"""
import json
import struct
import subprocess
import xml.etree.ElementTree as ET

from extract_npk import ROOT
from inspect_enemy_audio import sha


def main():
    out = ROOT/'analysis/battle-visual/elsa-audio'
    bank = (out/'ailisha_skill.bnk').read_bytes()
    if sha(bank) != '109253cf1afd44f9aeb40a3eec3fd937d9b4878378cb866cdfbbc1f467602e42':
        raise ValueError('bank identity changed')
    commit = subprocess.check_output(['git','-C',str(ROOT/'.tools/wwiser'),'rev-parse','HEAD'],text=True).strip()
    if commit != '94580dd3de3280933d69c435e96d4e2c3b443207':
        raise ValueError('wwiser version changed')
    xml = out/'wwiser-bank.xml'
    root = ET.parse(xml).getroot()
    records = {}
    for node in root.iter('object'):
        ident = node.find("field[@name='ulID']")
        if ident is not None:
            key = int(ident.get('value'))
            if key in records:
                raise ValueError('duplicate object ID')
            records[key] = node
    extracted = json.loads((out/'report.json').read_text('utf8'))
    media = {r['id']:r for r in extracted['media']}

    def field(node, name):
        found = node.findall(".//field[@name='"+name+"']")
        if len(found) != 1:
            raise ValueError('field not unique: '+name)
        f = found[0]
        offset, value = int(f.get('offset')), int(f.get('value'))
        code = {'u8':'B','u16':'H','u32':'I','sid':'I','tid':'I'}[f.get('type')]
        if struct.unpack_from('<'+code,bank,offset)[0] != value:
            raise ValueError('XML field disagrees with bytes')
        return dict(name=name,offset=offset,value=value,type=f.get('type'))

    routes = []
    for event in extracted['events']:
        node = records[int(event['Id'])]
        if node.get('name') != 'CAkEvent':
            raise ValueError('metadata event is not parsed as event')
        row = dict(event=event, event_id_field=field(node,'ulID'), actions=[])
        action_fields = node.findall(".//field[@name='ulActionID']")
        if field(node,'ulActionListSize')['value'] != len(action_fields):
            raise ValueError('action count mismatch')
        for f in action_fields:
            action_id = int(f.get('value'))
            offset = int(f.get('offset'))
            if struct.unpack_from('<I',bank,offset)[0] != action_id:
                raise ValueError('action reference mismatch')
            action = records[action_id]
            route = dict(action_id=action_id, action_reference_offset=offset,
                         action_class=action.get('name'), fields=[])
            row['actions'].append(route)
            if action.get('name') != 'CAkActionPlay':
                route['unresolved'] = 'Non-play action retained without interpretation'
                continue
            route['fields'] = [field(action,n) for n in ('ulActionType','idExt','fileID')]
            target = records[route['fields'][1]['value']]
            route['target_class'] = target.get('name')
            if target.get('name') != 'CAkSound':
                route['unresolved'] = 'Container traversal not implemented'
                continue
            route['fields'] += [field(target,n) for n in ('ulPluginID','StreamType','sourceID','uInMemoryMediaSize')]
            source_id = route['fields'][-2]['value']
            item = media[source_id]
            payload = (out/f'{source_id}.wem').read_bytes()
            if len(payload) != route['fields'][-1]['value'] or sha(payload) != item['sha256']:
                raise ValueError('source media identity/size mismatch')
            route['media'] = item
        routes.append(row)
    report = dict(bank_sha256=sha(bank), wwiser_commit=commit, xml_sha256=sha(xml.read_bytes()),
                  routes=routes, limitations=['Static parser interpretation independently checked against byte offsets.',
                  'Routing only; volume, pitch, buses, effects and action properties not reproduced.',
                  'Animation ObjectFileID mapping, codecs and actual playback remain unverified.',
                  'Ordinary local tool evidence, not REA or original-client runtime evidence.'])
    (out/'event-routes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(events=len(routes), direct_media_actions=sum('media' in a for r in routes for a in r['actions']),
                          unresolved_actions=sum('unresolved' in a for r in routes for a in r['actions']))))


if __name__ == '__main__':
    main()
