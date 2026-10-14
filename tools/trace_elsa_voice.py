"""Bound three battle voice events to source playlists and streamed WEMs."""
import json
import struct
import xml.etree.ElementTree as ET
import zipfile

from extract_npk import APK, ROOT
from inspect_enemy_audio import sha, chunks
from scan_enemy_audio_banks import objects


def main(event_ids=(145566836,1341919569,485176467), report_name='voice-routes.json'):
    out = ROOT/'analysis/battle-visual/elsa-audio'
    member = 'assets/res/wwise/ailisha_voice.bnk'
    with zipfile.ZipFile(APK) as archive:
        bank = archive.read(member)
        if bank != (out/'ailisha_voice.bnk').read_bytes():
            raise ValueError('voice bank mismatch')
        root = ET.parse(out/'wwiser-voice.xml')
        nodes = {int(n.find("field[@name='ulID']").get('value')):n for n in root.iter('object')
                 if n.find("field[@name='ulID']") is not None}
        def field(node,name):
            fs = node.findall(".//field[@name='"+name+"']")
            if len(fs)!=1:
                raise ValueError('ambiguous field '+name)
            f=fs[0];fmt={'sid':'I','tid':'I','u32':'I','s32':'i','u16':'H','u8':'B','f32':'f'}[f.get('type')]
            value=float(f.get('value')) if fmt=='f' else int(f.get('value'))
            if struct.unpack_from('<'+fmt,bank,int(f.get('offset')))[0]!=value:
                raise ValueError('field byte mismatch')
            return dict(f.attrib)
        media={}; external=set()
        def target(ident):
            node=nodes.get(ident)
            if node is None:
                external.add(ident);return dict(id=ident,status='external-to-voice-bank')
            row=dict(id=ident,node_class=node.get('name'),fields=[])
            if node.get('name')=='CAkSound':
                row['fields']=[field(node,n) for n in ('sourceID','StreamType','ulPluginID')]
                media_id=int(row['fields'][0]['value'])
                name=f'assets/res/wwise/{media_id}.wem'
                if name not in archive.namelist():
                    row['unresolved']='loose WEM absent';return row
                payload=archive.read(name)
                destination=out/'voice-media'/f'{media_id}.wem'
                destination.parent.mkdir(exist_ok=True);destination.write_bytes(payload)
                media[media_id]=dict(member=name,bytes=len(payload),sha256=sha(payload))
                row['media_id']=media_id
            elif node.get('name')=='CAkRanSeqCntr':
                row['fields']=[field(node,n) for n in ('sLoopCount','sLoopModMin','sLoopModMax',
                              'wAvoidRepeatCount','eMode','eRandomMode','eTransitionMode',
                              'fTransitionTime','fTransitionTimeModMin','fTransitionTimeModMax')]
                settings=[n for n in node.iter() if n.find("field[@name='eMode']") is not None]
                if len(settings)!=1:
                    raise ValueError('ambiguous sequence settings')
                packed=settings[0].find("field[@name='byBitVector']")
                offset=int(packed.get('offset'));value=int(packed.get('value'))
                if bank[offset]!=value:
                    raise ValueError('sequence flags byte mismatch')
                flags=[]
                for bit in packed.findall('field'):
                    shift=int(bit.get('type').removeprefix('bit'))
                    if ((value>>shift)&1)!=int(bit.get('value')):
                        raise ValueError('sequence flag interpretation mismatch')
                    flags.append(dict(bit.attrib))
                row['sequence_flags']=dict(source=dict(packed.attrib),bits=flags,
                    limitation='Stored flags only; reset/global/stop runtime semantics are not implemented.')
                row['playlist']=[]
                for item in node.findall(".//object[@name='AkPlaylistItem']"):
                    play=field(item,'ulPlayID');weight=field(item,'weight')
                    row['playlist'].append(dict(play=play,weight=weight,target=target(int(play['value']))))
            return row
        events=[]
        for ident in event_ids:
            event=nodes[ident];row=dict(id=ident,actions=[])
            for f in event.findall(".//field[@name='ulActionID']"):
                action_id=int(f.get('value'));offset=int(f.get('offset'))
                if struct.unpack_from('<I',bank,offset)[0]!=action_id:
                    raise ValueError('event action reference mismatch')
                action=nodes[action_id];ref=field(action,'idExt')
                action_fields=[field(action,'ulActionType')]
                if action.get('name')=='CAkActionPlay':
                    action_fields.append(field(action,'fileID'))
                else:
                    action_fields.append(field(action,'ulExceptionListSize'))
                params=action.find(".//object[@name='"+('PlayActionParams' if action.get('name')=='CAkActionPlay' else 'ActiveActionParams')+"']")
                curve_byte=field(params,'byBitVector')
                curve=params.find("field[@name='byBitVector']/field[@name='eFadeCurve']")
                if int(curve.get('value'))!=(int(curve_byte['value'])&31):
                    raise ValueError('fade curve bits mismatch')
                action_fields.append(curve_byte)
                properties=[]
                for prop in action.findall(".//object[@name='AkPropBundle']"):
                    pid=field(prop,'pID');value=prop.find("field[@name='pValue']")
                    ident=int(pid['value'])
                    if ident not in (15,16):
                        raise ValueError('unhandled voice action property')
                    offset=int(value.get('offset'));number=int(value.get('value'))
                    if struct.unpack_from('<i',bank,offset)[0]!=number:
                        raise ValueError('voice action timing byte mismatch')
                    properties.append(dict(id=pid,value=dict(value.attrib),milliseconds=number))
                # Retain the whole action for flags and exceptions not interpreted here.
                row['actions'].append(dict(id=action_id,node_class=action.get('name'),reference=ref,
                                           fields=action_fields,fade_curve=dict(curve.attrib),timing_properties=properties,
                                           raw_action_xml=ET.tostring(action,encoding='unicode'),
                                           target=target(int(ref['value']))))
            events.append(row)
        matches=[]
        for name in sorted(n for n in archive.namelist() if n.endswith('.bnk')):
            raw=archive.read(name);parts=chunks(raw)
            found=[r for r in objects(parts[b'HIRC'][1]) if r['id'] in external] if b'HIRC' in parts else []
            if found:matches.append(dict(member=name,sha256=sha(raw),objects=found))
    report=dict(bank_member=member,bank_sha256=sha(bank),xml_sha256=sha((out/'wwiser-voice.xml').read_bytes()),
                events=events,media=media,external_object_ids=sorted(external),external_matches=matches,
                limitations=['Exact field and playlist references; sequence runtime reset/global behavior not implemented.',
                             'Stop/play actions preserved; external bank load/order remains unverified.',
                             'No voice playback or client integration; mixing and dynamic parameters incomplete.'])
    (out/report_name).write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(events=len(events),media=len(media),external_ids=sorted(external),external_banks=len(matches))))


if __name__=='__main__':
    main()
