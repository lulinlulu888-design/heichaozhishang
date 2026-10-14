"""Record source actor-mixer ancestry; do not flatten RTPCs into fixed gain."""
import json
import argparse
import struct
import xml.etree.ElementTree as ET

from extract_npk import ROOT
from inspect_enemy_audio import sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voice', action='store_true')
    parser.add_argument('--result-voice', action='store_true')
    args = parser.parse_args()
    if args.voice and args.result_voice: parser.error('Select one voice set')
    prefix = 'result-voice' if args.result_voice else 'voice'
    args.voice = args.voice or args.result_voice
    out = ROOT/'analysis/battle-visual/elsa-audio'
    bank = (out/('ailisha_voice.bnk' if args.voice else 'ailisha_skill.bnk')).read_bytes()
    expected = ('644199d04c71a5ff05d3d683623856abd6f14f0589ef96ae3631f39d3d7484ae' if args.voice
                else '109253cf1afd44f9aeb40a3eec3fd937d9b4878378cb866cdfbbc1f467602e42')
    if sha(bank) != expected:
        raise ValueError('bank identity changed')
    xml = out/('wwiser-voice.xml' if args.voice else 'wwiser-bank.xml')
    nodes = {}
    for node in ET.parse(xml).iter('object'):
        f = node.find("field[@name='ulID']")
        if f is not None:
            ident = int(f.get('value'))
            if ident in nodes:
                raise ValueError('duplicate object')
            nodes[ident] = node

    def integer(f):
        offset, value = int(f.get('offset')),int(f.get('value'))
        fmt = {'u8':'B','u16':'H','u32':'I','sid':'I','tid':'I'}[f.get('type')]
        if struct.unpack_from('<'+fmt,bank,offset)[0] != value:
            raise ValueError('field mismatch')
        return dict(f.attrib)

    if args.voice:
        voice = json.loads((out/(prefix+'-routes.json')).read_text('utf8'))
        def leaves(target):
            if 'media_id' in target:
                yield dict(media=target['media_id'], fields=[dict(name='idExt',value=target['id'])])
            for child in target.get('playlist', []):
                yield from leaves(child['target'])
        routes = dict(routes=[dict(actions=list(leaves(action['target'])))
                              for event in voice['events'] for action in event['actions']])
    else:
        routes = json.loads((out/'event-routes.json').read_text('utf8'))
    chains = {}
    for route in routes['routes']:
        for action in route['actions']:
            if 'media' not in action:
                continue
            ident = next(f['value'] for f in action['fields'] if f['name']=='idExt')
            key = str(ident)
            if key in chains:
                continue
            ancestry, seen = [], set()
            while ident:
                if ident in seen or ident not in nodes:
                    raise ValueError('cyclic/missing parent')
                seen.add(ident)
                node = nodes[ident]
                row = dict(id=ident, node_class=node.get('name'), properties=[], links=[], rtpc_objects=[])
                for bundle in node.findall('.//object'):
                    if bundle.get('name','').startswith('AkPropBundle'):
                        for prop in bundle.findall('./list/object'):
                            pid = prop.find("field[@name='pID']")
                            if pid is None:
                                continue
                            entry = dict(id=integer(pid),values=[])
                            for f in prop.findall('field'):
                                if f.get('name') not in ('pValue','min','max'):
                                    continue
                                offset = int(f.get('offset'))
                                value = dict(f.attrib,raw_hex=bank[offset:offset+4].hex())
                                # Known float-valued properties only; other unions stay opaque.
                                if int(pid.get('value')) in (0,2,19):
                                    if struct.unpack_from('<f',bank,offset)[0] != float(f.get('value')):
                                        raise ValueError('property float mismatch')
                                    value['float_verified'] = True
                                entry['values'].append(value)
                            row['properties'].append(entry)
                    if bundle.get('name') == 'RTPC':
                        row['rtpc_objects'].append(ET.tostring(bundle,encoding='unicode'))
                for name in ('OverrideBusId','DirectParentID','ulNumRTPC'):
                    fs = node.findall(".//field[@name='"+name+"']")
                    if len(fs) != 1:
                        raise ValueError('link/count not unique: '+name)
                    row['links'].append(integer(fs[0]))
                expected_rtpcs = int(next(f['value'] for f in row['links'] if f['name']=='ulNumRTPC'))
                if len(row['rtpc_objects']) != expected_rtpcs:
                    raise ValueError('RTPC preservation count mismatch')
                ancestry.append(row)
                ident = int(next(f['value'] for f in row['links'] if f['name']=='DirectParentID'))
            chains[key] = ancestry
    report = dict(bank_sha256=sha(bank),xml_sha256=sha(xml.read_bytes()),chains=chains,
                  limitations=['Actor-mixer ancestry only; bus graph and effects not flattened.',
                               'RTPC XML preserved without evaluating game-controlled parameters.',
                               'Local static values cannot be called final original playback gain.',
                               'Wwise mixing and original runtime remain unverified.'])
    (out/(prefix+'-mix-ancestry.json' if args.voice else 'mix-ancestry.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(sound_chains=len(chains),max_depth=max(map(len,chains.values())))))


if __name__ == '__main__':
    main()
