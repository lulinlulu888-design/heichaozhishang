"""Evaluate only the flat zero segments covering the authored default speed."""
import json
import struct
import xml.etree.ElementTree as ET
import zipfile

from extract_npk import APK, ROOT
from inspect_enemy_audio import sha
from inspect_neox_model import extract_npk_entry


def main():
    out = ROOT/'analysis/battle-visual/elsa-audio'
    with zipfile.ZipFile(APK) as archive:
        init = archive.read('assets/res/wwise/init.bnk')
        bank = archive.read('assets/res/wwise/ailisha_skill.bnk')
    if init != (out/'init.bnk').read_bytes() or sha(bank) != '109253cf1afd44f9aeb40a3eec3fd937d9b4878378cb866cdfbbc1f467602e42':
        raise ValueError('bank identity mismatch')
    source = extract_npk_entry(APK,'assets/res/wwise.npk',6,out/'wwise-names.txt')
    names = (out/'wwise-names.txt').read_text('utf8')
    matches = [line for line in names.splitlines() if '\t54353430\tdouble_speed\t' in line]
    if len(matches) != 1:
        raise ValueError('parameter name not uniquely bound')

    def read(f, data):
        fmt = {'sid':'I','tid':'I','u32':'I','u16':'H','u8':'B','var':'B','f32':'f'}[f.get('type')]
        value = float(f.get('value')) if fmt=='f' else int(f.get('value'))
        if struct.unpack_from('<'+fmt,data,int(f.get('offset')))[0] != value:
            raise ValueError('field disagrees with original bytes')
        return value

    init_xml = ET.parse(out/'wwiser-init.xml')
    defaults = [n for n in init_xml.findall(".//object[@name='RTPCRamping']")
                if n.find("field[@name='RTPC_ID']").get('value')=='54353430']
    if len(defaults) != 1:
        raise ValueError('default not unique')
    default_fields = {f.get('name'):read(f,init) for f in defaults[0].findall('field')}
    default = default_fields['fValue']
    mix = json.loads((out/'mix-ancestry.json').read_text('utf8'))
    curves, unresolved = {}, {}
    for chain in mix['chains'].values():
        for node in chain:
            for raw in node['rtpc_objects']:
                xml = ET.fromstring(raw)
                fields = {f.get('name'):read(f,bank) for f in xml.findall('field')}
                if fields['RTPCID'] != 54353430:
                    unresolved[str(fields['rtpcCurveID'])] = dict(node_id=node['id'],fields=fields,
                                                                 reason='Other parameter; not evaluated')
                    continue
                points = [{f.get('name'):read(f,bank) for f in p.findall('field')}
                          for p in xml.findall(".//object[@name='AkRTPCGraphPoint']")]
                if len(points) != fields['ulSize'] or any(b['From']<=a['From'] for a,b in zip(points,points[1:])):
                    raise ValueError('curve bounds/order mismatch')
                spans = [(a,b) for a,b in zip(points,points[1:]) if a['From']<=default<b['From']]
                if len(spans)!=1 or any(p['To']!=0 for p in spans[0]) or spans[0][0]['Interp']!=9:
                    raise ValueError('default not inside a proven constant-zero interval')
                curves[str(fields['rtpcCurveID'])] = dict(node_id=node['id'],fields=fields,points=points,
                                                         default_input=default,raw_default_output=0)
    report = dict(init_sha256=sha(init), bank_sha256=sha(bank),name_source=source,name_line=matches[0],
                  parameter_defaults=default_fields,curves=curves,unresolved_curves=unresolved,
                  limitations=['Authored defaults only; game code can override double_speed.',
                               'Only constant-zero spans evaluated; not a general Wwise curve/scaling implementation.',
                               'Bus/effect/state mixing and runtime playback remain incomplete.'])
    (out/'dynamic-defaults.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(parameter='double_speed',default=default,zero_default_curves=len(curves),
                          unresolved_curves=len(unresolved))))


if __name__ == '__main__':
    main()
